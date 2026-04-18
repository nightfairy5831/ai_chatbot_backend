from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.prompt_engine import generate_prompt
from app.core.openai_service import chat_completion, chat_completion_with_tools
from app.core import calendar_service
from app.core.email_service import send_booking_confirmation
from app.core.rate_limiter import check_rate_limit
from app.models.user import User
from app.models.agent import Agent
from app.models.question import Question
from app.models.calendar_connection import CalendarConnection

router = APIRouter(prefix="/api/agents/{agent_id}", tags=["prompts"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    response: str
    prompt_used: str


def get_user_agent(agent_id: int, current_user: User, db: Session) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/generate-prompt")
def get_generated_prompt(agent_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = get_user_agent(agent_id, current_user, db)
    prompt = generate_prompt(agent, agent.products)
    agent.prompt_template = prompt
    db.commit()
    return {"prompt": prompt}


@router.post("/chat", response_model=ChatResponse)
def chat_with_agent(agent_id: int, data: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = get_user_agent(agent_id, current_user, db)

    allowed, usage, limit = check_rate_limit(current_user.id, current_user.plan, db)
    if not allowed:
        raise HTTPException(status_code=429, detail=f"Monthly message limit reached ({usage}/{limit}). Upgrade your plan.")

    prompt = generate_prompt(agent, agent.products)

    cal_conn = db.query(CalendarConnection).filter(
        CalendarConnection.agent_id == agent_id,
        CalendarConnection.user_id == current_user.id,
        CalendarConnection.is_active == True,
    ).first()

    try:
        if cal_conn:
            def tool_handler(fn_name: str, fn_args: dict) -> dict:
                calendar_id = cal_conn.calendar_id or "primary"
                if fn_name == "check_availability":
                    slots = calendar_service.get_available_slots(
                        cal_conn.google_refresh_token, fn_args["date"], calendar_id
                    )
                    return {"available_slots": slots, "date": fn_args["date"]}

                elif fn_name == "book_appointment":
                    event = calendar_service.create_event(
                        cal_conn.google_refresh_token,
                        fn_args["date"],
                        fn_args["time"],
                        f"Appointment: {fn_args['customer_name']}",
                        f"Customer: {fn_args['customer_name']}",
                        calendar_id,
                    )
                    send_booking_confirmation(
                        to_email=current_user.email,
                        agent_name=agent.name,
                        customer_name=fn_args["customer_name"],
                        customer_email=fn_args.get("customer_email"),
                        customer_phone=fn_args.get("customer_phone"),
                        date=fn_args["date"],
                        time=fn_args["time"],
                        notes=fn_args.get("notes"),
                    )
                    return {"status": "booked", "event_id": event["id"], "date": fn_args["date"], "time": fn_args["time"]}

                return {"error": "Unknown function"}

            history = [{"role": m.role, "content": m.content} for m in data.history]
            result = chat_completion_with_tools(prompt, data.message, tool_handler, history)
        else:
            history = [{"role": m.role, "content": m.content} for m in data.history]
            result = chat_completion(prompt, data.message, history)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get AI response")

    question = Question(user_id=current_user.id, agent_id=agent.id, question=data.message)
    db.add(question)
    db.flush()

    question.token = result["token"]
    db.commit()

    return ChatResponse(response=result["content"], prompt_used=prompt)
