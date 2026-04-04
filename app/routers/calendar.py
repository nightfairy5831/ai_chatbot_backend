from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.core import calendar_service
from app.core.email_service import send_booking_confirmation
from app.models.calendar_connection import CalendarConnection
from app.models.agent import Agent
from app.models.user import User
from app.schemas.calendar import (
    CalendarConnectionOut, BookingRequest, BookingOut,
    AvailabilityRequest, TimeSlot,
)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


# --- OAuth2 Flow ---

@router.get("/connect/{agent_id}")
def connect_google(agent_id: int, current_user=Depends(get_current_user)):
    state = f"{current_user.id}:{agent_id}"
    url = calendar_service.get_auth_url(state)
    return {"auth_url": url}


@router.get("/callback")
def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        user_id, agent_id = state.split(":")
        user_id, agent_id = int(user_id), int(agent_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state")

    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == user_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    tokens = calendar_service.exchange_code(code)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh token received")

    existing = db.query(CalendarConnection).filter(
        CalendarConnection.agent_id == agent_id,
        CalendarConnection.user_id == user_id,
    ).first()

    if existing:
        existing.google_refresh_token = refresh_token
        existing.is_active = True
    else:
        conn = CalendarConnection(
            agent_id=agent_id,
            user_id=user_id,
            google_refresh_token=refresh_token,
        )
        db.add(conn)

    db.commit()
    return {"message": "Google Calendar connected"}


# --- Client Endpoints ---

@router.get("/agents/{agent_id}/connection", response_model=CalendarConnectionOut | None)
def get_connection(agent_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    conn = db.query(CalendarConnection).filter(
        CalendarConnection.agent_id == agent_id,
        CalendarConnection.user_id == current_user.id,
        CalendarConnection.is_active == True,
    ).first()
    return conn


@router.delete("/agents/{agent_id}/disconnect")
def disconnect_calendar(agent_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(CalendarConnection).filter(
        CalendarConnection.agent_id == agent_id,
        CalendarConnection.user_id == current_user.id,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")

    conn.is_active = False
    db.commit()
    return {"message": "Calendar disconnected"}


@router.post("/agents/{agent_id}/availability", response_model=list[TimeSlot])
def check_availability(agent_id: int, req: AvailabilityRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(CalendarConnection).filter(
        CalendarConnection.agent_id == agent_id,
        CalendarConnection.user_id == current_user.id,
        CalendarConnection.is_active == True,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Calendar not connected")

    slots = calendar_service.get_available_slots(conn.google_refresh_token, req.date, conn.calendar_id or "primary")
    return slots


@router.post("/agents/{agent_id}/book", response_model=BookingOut)
def book_appointment(agent_id: int, req: BookingRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(CalendarConnection).filter(
        CalendarConnection.agent_id == agent_id,
        CalendarConnection.user_id == current_user.id,
        CalendarConnection.is_active == True,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Calendar not connected")

    summary = f"Appointment: {req.customer_name}"
    description = f"Customer: {req.customer_name}"
    if req.customer_email:
        description += f"\nEmail: {req.customer_email}"
    if req.customer_phone:
        description += f"\nPhone: {req.customer_phone}"
    if req.notes:
        description += f"\nNotes: {req.notes}"

    event = calendar_service.create_event(
        conn.google_refresh_token, req.date, req.time, summary, description, conn.calendar_id or "primary"
    )

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    owner = db.query(User).filter(User.id == conn.user_id).first()
    if owner and owner.email:
        send_booking_confirmation(
            to_email=owner.email,
            agent_name=agent.name if agent else "Agent",
            customer_name=req.customer_name,
            customer_email=req.customer_email,
            customer_phone=req.customer_phone,
            date=req.date,
            time=req.time,
            notes=req.notes,
        )

    return BookingOut(
        event_id=event["id"],
        summary=event.get("summary", ""),
        start=event["start"].get("dateTime", ""),
        end=event["end"].get("dateTime", ""),
        status=event.get("status", "confirmed"),
    )


@router.get("/agents/{agent_id}/bookings", response_model=list[BookingOut])
def list_bookings(agent_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(CalendarConnection).filter(
        CalendarConnection.agent_id == agent_id,
        CalendarConnection.user_id == current_user.id,
        CalendarConnection.is_active == True,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Calendar not connected")

    events = calendar_service.list_events(conn.google_refresh_token, conn.calendar_id or "primary")
    return [
        BookingOut(
            event_id=e["id"],
            summary=e.get("summary", ""),
            start=e.get("start", {}).get("dateTime", ""),
            end=e.get("end", {}).get("dateTime", ""),
            status=e.get("status", ""),
        )
        for e in events
    ]


# --- Admin Endpoints ---

@router.get("/admin/connections", response_model=list[CalendarConnectionOut])
def admin_list_connections(current_user=Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(CalendarConnection).all()
