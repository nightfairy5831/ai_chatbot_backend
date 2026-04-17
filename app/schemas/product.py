from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    price: str | None = None
    type: str = "product"
    purchase_link: str | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: str | None = None
    type: str | None = None
    purchase_link: str | None = None


class ProductOut(BaseModel):
    id: int
    name: str
    description: str | None
    price: str | None
    type: str
    purchase_link: str | None
    agent_id: int

    class Config:
        from_attributes = True
