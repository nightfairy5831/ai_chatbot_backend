from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.agent import Agent
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate, ProductOut

router = APIRouter(prefix="/api/agents/{agent_id}/products", tags=["products"])


def get_user_agent(agent_id: int, current_user: User, db: Session) -> Agent:
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/", response_model=list[ProductOut])
def list_products(agent_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    get_user_agent(agent_id, current_user, db)
    return db.query(Product).filter(Product.agent_id == agent_id).all()


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(agent_id: int, data: ProductCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    get_user_agent(agent_id, current_user, db)
    product = Product(name=data.name, description=data.description, price=data.price, agent_id=agent_id)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(agent_id: int, product_id: int, data: ProductUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    get_user_agent(agent_id, current_user, db)
    product = db.query(Product).filter(Product.id == product_id, Product.agent_id == agent_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(agent_id: int, product_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    get_user_agent(agent_id, current_user, db)
    product = db.query(Product).filter(Product.id == product_id, Product.agent_id == agent_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
