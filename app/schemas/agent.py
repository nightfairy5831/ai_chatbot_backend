from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    description: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class AgentOut(BaseModel):
    id: int
    name: str
    description: str | None
    user_id: int

    class Config:
        from_attributes = True
