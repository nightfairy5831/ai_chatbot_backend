from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core import twilio_service
from app.core.prompt_engine import generate_prompt
from app.core.openai_service import chat_completion
from app.models.whatsapp_number import WhatsappNumber
from app.models.agent import Agent
from app.models.question import Question
from app.schemas.whatsapp import WhatsappNumberCreate, WhatsappNumberOut

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


# --- Client Endpoints ---

@router.get("/available-numbers")
def available_numbers(
    country: str = Query("US"),
    current_user=Depends(get_current_user),
):
    try:
        numbers = twilio_service.list_available_numbers(country)
        return numbers
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/agents/{agent_id}/connect", response_model=WhatsappNumberOut)
def connect_number(
    agent_id: int,
    data: WhatsappNumberCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    existing = db.query(WhatsappNumber).filter(WhatsappNumber.phone_number == data.phone_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="This number is already in use")

    try:
        twilio_sid = twilio_service.buy_number(data.phone_number)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to acquire number: {str(e)}")

    wn = WhatsappNumber(
        phone_number=data.phone_number,
        agent_id=agent_id,
        user_id=current_user.id,
        twilio_sid=twilio_sid,
    )
    db.add(wn)
    db.commit()
    db.refresh(wn)
    return wn


@router.get("/agents/{agent_id}/numbers", response_model=list[WhatsappNumberOut])
def list_agent_numbers(
    agent_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return db.query(WhatsappNumber).filter(
        WhatsappNumber.agent_id == agent_id,
        WhatsappNumber.user_id == current_user.id,
        WhatsappNumber.is_active == True,
    ).all()


@router.delete("/numbers/{number_id}")
def disconnect_number(
    number_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wn = db.query(WhatsappNumber).filter(
        WhatsappNumber.id == number_id,
        WhatsappNumber.user_id == current_user.id,
    ).first()
    if not wn:
        raise HTTPException(status_code=404, detail="Number not found")

    if wn.twilio_sid:
        twilio_service.release_number(wn.twilio_sid)

    wn.is_active = False
    db.commit()
    return {"message": "Number disconnected"}


# --- Inbound Webhook ---

@router.post("/webhook")
async def whatsapp_webhook(request: FastAPIRequest, db: Session = Depends(get_db)):
    form = await request.form()
    from_number = str(form.get("From", "")).replace("whatsapp:", "")
    to_number = str(form.get("To", "")).replace("whatsapp:", "")
    body = str(form.get("Body", ""))

    if not from_number or not body:
        return {"status": "ignored"}

    wn = db.query(WhatsappNumber).filter(
        WhatsappNumber.phone_number == to_number,
        WhatsappNumber.is_active == True,
    ).first()

    if not wn:
        return {"status": "number not registered"}

    agent = db.query(Agent).filter(Agent.id == wn.agent_id).first()
    if not agent:
        return {"status": "agent not found"}

    prompt = generate_prompt(agent, agent.products)

    try:
        result = chat_completion(prompt, body)
        reply = result["content"]
    except Exception:
        reply = "Sorry, I'm unable to respond right now. Please try again later."

    question = Question(
        user_id=wn.user_id,
        agent_id=wn.agent_id,
        question=body,
        token=result.get("token", 0) if 'result' in dir() else 0,
        source_channel="whatsapp",
    )
    db.add(question)
    db.commit()

    try:
        twilio_service.send_whatsapp_message(from_number, reply, to_number)
    except Exception:
        pass

    return {"status": "sent"}


# --- Admin Endpoints ---

@router.get("/admin/numbers", response_model=list[WhatsappNumberOut])
def admin_list_numbers(current_user=Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(WhatsappNumber).all()


@router.delete("/admin/numbers/{number_id}")
def admin_disconnect_number(
    number_id: int,
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    wn = db.query(WhatsappNumber).filter(WhatsappNumber.id == number_id).first()
    if not wn:
        raise HTTPException(status_code=404, detail="Number not found")

    if wn.twilio_sid:
        twilio_service.release_number(wn.twilio_sid)

    wn.is_active = False
    db.commit()
    return {"message": "Number disconnected"}
