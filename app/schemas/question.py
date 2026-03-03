from pydantic import BaseModel
from datetime import datetime


class QuestionOut(BaseModel):
    id: int
    user_id: int
    agent_id: int
    question: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True
