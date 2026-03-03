from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.prompt_engine import generate_prompt
from app.core.openai_service import chat_completion
from app.models.user import User
from app.models.agent import Agent

router = APIRouter(prefix="/api/agents/{agent_id}", tags=["prompts"])


class ChatRequest(BaseModel):
    message: str


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
    prompt = generate_prompt(agent, agent.products)

    try:
        response = chat_completion(prompt, data.message)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get AI response")

    return ChatResponse(response=response, prompt_used=prompt)
