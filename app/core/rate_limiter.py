from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.question import Question

PLAN_LIMITS = {
    "free": 50,
    "starter": 1000,
    "professional": 5000,
    "business": 20000,
    "admin": 999999,
}


def get_monthly_usage(user_id: int, db: Session) -> int:
    first_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = db.query(func.count(Question.id)).filter(
        Question.user_id == user_id,
        Question.created_at >= first_of_month,
    ).scalar()
    return count or 0


def check_rate_limit(user_id: int, plan: str, db: Session) -> tuple[bool, int, int]:
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    usage = get_monthly_usage(user_id, db)
    return usage < limit, usage, limit
