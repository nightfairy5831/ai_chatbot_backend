from pydantic import BaseModel
from app.schemas.product import ProductOut


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    business_name: str | None = None
    industry: str | None = None
    tone: str | None = "professional"
    instructions: str | None = None
    sinstruction: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    business_name: str | None = None
    industry: str | None = None
    tone: str | None = None
    instructions: str | None = None
    sinstruction: str | None = None


class AgentOut(BaseModel):
    id: int
    name: str
    description: str | None
    user_id: int
    business_name: str | None = None
    industry: str | None = None
    tone: str | None = None
    instructions: str | None = None
    sinstruction: str | None = None
    prompt_template: str | None = None
    products: list[ProductOut] = []

    class Config:
        from_attributes = True
