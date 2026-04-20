from pydantic import BaseModel
from datetime import datetime


class WhatsappNumberCreate(BaseModel):
    phone_number: str
    agent_id: int


class WhatsappNumberOut(BaseModel):
    id: int
    phone_number: str
    agent_id: int
    user_id: int
    is_active: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True
