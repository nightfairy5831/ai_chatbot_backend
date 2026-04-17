from pydantic import BaseModel
from datetime import datetime


class CalendarConnectionOut(BaseModel):
    id: int
    agent_id: int
    user_id: int
    calendar_id: str | None
    is_active: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class BookingRequest(BaseModel):
    date: str
    time: str
    customer_name: str
    customer_email: str | None = None
    customer_phone: str | None = None
    notes: str | None = None


class BookingOut(BaseModel):
    event_id: str
    summary: str
    start: str
    end: str
    status: str


class AvailabilityRequest(BaseModel):
    date: str


class TimeSlot(BaseModel):
    start: str
    end: str
