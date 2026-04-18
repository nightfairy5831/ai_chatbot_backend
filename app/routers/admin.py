from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, cast, Date
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.security import require_admin
from app.core.prompt_engine import generate_prompt
from app.core.openai_service import chat_completion
from app.models.user import User
from app.models.agent import Agent
from app.models.product import Product
from app.models.question import Question

router = APIRouter(prefix="/api/admin", tags=["admin"])


# --- Schemas ---

class AdminUserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: str | None = None
    agent_count: int = 0

    class Config:
        from_attributes = True


class AdminAgentOut(BaseModel):
    id: int
    name: str
    description: str | None
    business_name: str | None
    industry: str | None
    tone: str | None
    owner_username: str
    owner_email: str
    product_count: int = 0
    question_count: int = 0
    created_at: str | None = None

    class Config:
        from_attributes = True


class ActivityLogOut(BaseModel):
    id: int
    question: str
    username: str
    agent_name: str
    agent_id: int
    created_at: str | None = None

    class Config:
        from_attributes = True


class UserRoleUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    plan: str | None = None


class AdminChatRequest(BaseModel):
    message: str


class AdminChatResponse(BaseModel):
    response: str
    prompt_used: str


# --- Platform Stats ---

@router.get("/stats")
def admin_stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    total_users = db.query(func.count(User.id)).scalar()
    total_agents = db.query(func.count(Agent.id)).scalar()
    total_products = db.query(func.count(Product.id)).scalar()
    total_questions = db.query(func.count(Question.id)).scalar()
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    return {
        "total_users": total_users,
        "total_agents": total_agents,
        "total_products": total_products,
        "total_questions": total_questions,
        "active_users": active_users,
    }


@router.get("/charts/questions")
def question_chart(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(cast(Question.created_at, Date).label("date"), func.count(Question.id).label("count"))
        .filter(Question.created_at >= since)
        .group_by(cast(Question.created_at, Date))
        .order_by(cast(Question.created_at, Date))
        .all()
    )
    date_map = {str(r.date): r.count for r in rows}
    result = []
    for i in range(30):
        d = (since + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        result.append({"date": d, "count": date_map.get(d, 0)})
    return result


@router.get("/charts/agents")
def agent_chart(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(cast(Agent.created_at, Date).label("date"), func.count(Agent.id).label("count"))
        .filter(Agent.created_at >= since)
        .group_by(cast(Agent.created_at, Date))
        .order_by(cast(Agent.created_at, Date))
        .all()
    )
    date_map = {str(r.date): r.count for r in rows}
    result = []
    for i in range(30):
        d = (since + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        result.append({"date": d, "count": date_map.get(d, 0)})
    return result


@router.get("/charts/registrations")
def registration_chart(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(cast(User.created_at, Date).label("date"), func.count(User.id).label("count"))
        .filter(User.created_at >= since)
        .group_by(cast(User.created_at, Date))
        .order_by(cast(User.created_at, Date))
        .all()
    )
    date_map = {str(r.date): r.count for r in rows}
    result = []
    for i in range(30):
        d = (since + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        result.append({"date": d, "count": date_map.get(d, 0)})
    return result


# --- Users ---

@router.get("/users")
def list_users(
    search: str = Query("", description="Search by username or email"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if search:
        q = q.filter(or_(User.username.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")))
    users = q.order_by(User.created_at.desc()).all()

    agent_counts = dict(
        db.query(Agent.user_id, func.count(Agent.id)).group_by(Agent.user_id).all()
    )

    return [
        AdminUserOut(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else None,
            agent_count=agent_counts.get(u.id, 0),
        )
        for u in users
    ]


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserRoleUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.role is not None:
        if data.role not in ("admin", "client"):
            raise HTTPException(status_code=400, detail="Role must be 'admin' or 'client'")
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.plan is not None:
        if data.plan not in ("free", "starter", "professional", "business"):
            raise HTTPException(status_code=400, detail="Invalid plan")
        user.plan = data.plan
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role, "is_active": user.is_active, "plan": user.plan}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.query(Question).filter(Question.user_id == user_id).delete()
    db.query(Agent).filter(Agent.user_id == user_id).delete()
    db.delete(user)
    db.commit()


# --- Agents ---

@router.get("/agents")
def list_agents(
    search: str = Query("", description="Search by agent name or owner"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(Agent).join(User, Agent.user_id == User.id)
    if search:
        q = q.filter(or_(Agent.name.ilike(f"%{search}%"), User.username.ilike(f"%{search}%")))
    agents = q.order_by(Agent.created_at.desc()).all()

    agent_ids = [a.id for a in agents]
    product_counts = dict(
        db.query(Product.agent_id, func.count(Product.id))
        .filter(Product.agent_id.in_(agent_ids))
        .group_by(Product.agent_id)
        .all()
    ) if agent_ids else {}
    question_counts = dict(
        db.query(Question.agent_id, func.count(Question.id))
        .filter(Question.agent_id.in_(agent_ids))
        .group_by(Question.agent_id)
        .all()
    ) if agent_ids else {}

    return [
        AdminAgentOut(
            id=a.id,
            name=a.name,
            description=a.description,
            business_name=a.business_name,
            industry=a.industry,
            tone=a.tone,
            owner_username=a.owner.username,
            owner_email=a.owner.email,
            product_count=product_counts.get(a.id, 0),
            question_count=question_counts.get(a.id, 0),
            created_at=a.created_at.isoformat() if a.created_at else None,
        )
        for a in agents
    ]


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()


# --- Activity Logs ---

@router.get("/logs")
def activity_logs(
    search: str = Query("", description="Search by question text or agent name"),
    agent_id: int | None = Query(None, description="Filter by agent ID"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(Question).join(User, Question.user_id == User.id).join(Agent, Question.agent_id == Agent.id)
    if search:
        q = q.filter(or_(Question.question.ilike(f"%{search}%"), Agent.name.ilike(f"%{search}%")))
    if agent_id:
        q = q.filter(Question.agent_id == agent_id)
    logs = q.order_by(Question.created_at.desc()).limit(200).all()

    return [
        ActivityLogOut(
            id=log.id,
            question=log.question,
            username=log.user.username,
            agent_name=log.agent.name,
            agent_id=log.agent_id,
            created_at=log.created_at.isoformat() if log.created_at else None,
        )
        for log in logs
    ]


# --- Token Usage ---

@router.get("/token-usage/agents")
def token_usage_by_agent(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(
            Agent.name.label("agent_name"),
            User.username,
            func.count(Question.id).label("questions"),
            func.coalesce(func.sum(Question.token), 0).label("total_token"),
        )
        .join(User, Question.user_id == User.id)
        .join(Agent, Question.agent_id == Agent.id)
        .group_by(Agent.name, User.username)
        .order_by(func.coalesce(func.sum(Question.token), 0).desc())
        .all()
    )
    return [
        {"agent_name": r.agent_name, "username": r.username, "questions": r.questions, "total_token": r.total_token}
        for r in rows
    ]


@router.get("/token-usage/daily")
def token_usage_daily(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(
            cast(Question.created_at, Date).label("date"),
            func.coalesce(func.sum(Question.token), 0).label("total_token"),
        )
        .filter(Question.created_at >= since)
        .group_by(cast(Question.created_at, Date))
        .order_by(cast(Question.created_at, Date))
        .all()
    )
    date_map = {str(r.date): r.total_token for r in rows}
    result = []
    for i in range(30):
        d = (since + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        result.append({"date": d, "total_token": date_map.get(d, 0)})
    return result


# --- Live Test Chat ---

@router.post("/agents/{agent_id}/chat", response_model=AdminChatResponse)
def admin_chat(agent_id: int, data: AdminChatRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    prompt = generate_prompt(agent, agent.products)
    try:
        result = chat_completion(prompt, data.message)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get AI response")
    return AdminChatResponse(response=result["content"], prompt_used=prompt)
