import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.rate_limiter import check_rate_limit, PLAN_LIMITS
from app.models.user import User
from app.models.agent import Agent
from app.models.product import Product
from app.models.question import Question
from app.schemas.agent import AgentCreate, AgentUpdate, AgentOut

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/usage")
def get_usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed, usage, limit = check_rate_limit(current_user.id, current_user.plan, db)
    return {"plan": current_user.plan, "usage": usage, "limit": limit, "remaining": limit - usage}


@router.get("/stats")
def get_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_agents = db.query(Agent).filter(Agent.user_id == current_user.id)
    agent_ids = [a.id for a in user_agents.all()]

    total_agents = len(agent_ids)
    total_products = db.query(func.count(Product.id)).filter(Product.agent_id.in_(agent_ids)).scalar() if agent_ids else 0
    total_questions = db.query(func.count(Question.id)).filter(Question.user_id == current_user.id).scalar()

    most_used = None
    if agent_ids:
        row = (
            db.query(Question.agent_id, func.count(Question.id).label("cnt"))
            .filter(Question.agent_id.in_(agent_ids))
            .group_by(Question.agent_id)
            .order_by(func.count(Question.id).desc())
            .first()
        )
        if row:
            agent = db.query(Agent).get(row.agent_id)
            most_used = {"id": agent.id, "name": agent.name, "question_count": row.cnt}

    recent = user_agents.order_by(Agent.created_at.desc()).first()

    return {
        "total_agents": total_agents,
        "total_products": total_products,
        "total_questions": total_questions,
        "most_used_agent": most_used,
        "recent_agent": {"id": recent.id, "name": recent.name} if recent else None,
    }


@router.get("/logs")
def user_activity_logs(
    agent_id: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Question).filter(Question.user_id == current_user.id).join(Agent, Question.agent_id == Agent.id)
    if agent_id:
        q = q.filter(Question.agent_id == agent_id)
    logs = q.order_by(Question.created_at.desc()).limit(100).all()
    return [
        {
            "id": log.id,
            "question": log.question,
            "agent_name": log.agent.name,
            "agent_id": log.agent_id,
            "source_channel": log.source_channel,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/", response_model=list[AgentOut])
def list_agents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Agent).filter(Agent.user_id == current_user.id).all()


@router.post("/", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(data: AgentCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = Agent(name=data.name, description=data.description, user_id=current_user.id)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(agent_id: int, data: AgentUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)

    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/upload-sinstruction", response_model=AgentOut)
async def upload_sinstruction(
    agent_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    try:
        import PyPDF2
        content = await file.read()
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        text = text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
        agent.sinstruction = text
        db.commit()
        db.refresh(agent)
        return agent
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process PDF: {str(e)}")


@router.delete("/{agent_id}/sinstruction", response_model=AgentOut)
def delete_sinstruction(
    agent_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.sinstruction = None
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
