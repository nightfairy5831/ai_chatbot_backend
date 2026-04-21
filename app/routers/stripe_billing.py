import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import (
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_STARTER,
    STRIPE_PRICE_GROWTH,
    STRIPE_PRICE_SCALE,
    FRONTEND_URL,
)
from app.core.rate_limiter import PLAN_LIMITS, get_monthly_usage
from app.models.user import User

router = APIRouter(prefix="/api/stripe", tags=["stripe"])

stripe.api_key = STRIPE_SECRET_KEY

PRICE_TO_PLAN = {
    STRIPE_PRICE_STARTER: "starter",
    STRIPE_PRICE_GROWTH: "growth",
    STRIPE_PRICE_SCALE: "scale",
}

PLAN_INFO = {
    "free": {"name": "Free", "price": 0},
    "starter": {"name": "Starter", "price": 197},
    "growth": {"name": "Growth", "price": 397},
    "scale": {"name": "Scale", "price": 797},
}


def get_or_create_customer(user: User, db: Session) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email,
        name=user.username,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


@router.post("/create-checkout-session")
def create_checkout_session(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe is not configured")

    plan = data.get("plan")
    price_map = {
        "starter": STRIPE_PRICE_STARTER,
        "growth": STRIPE_PRICE_GROWTH,
        "scale": STRIPE_PRICE_SCALE,
    }
    price_id = price_map.get(plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan")

    customer_id = get_or_create_customer(current_user, db)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{FRONTEND_URL}?stripe=success",
        cancel_url=f"{FRONTEND_URL}?stripe=cancel",
        metadata={"user_id": str(current_user.id), "plan": plan},
    )
    return {"url": session.url}


@router.post("/create-portal-session")
def create_portal_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active subscription")

    session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=f"{FRONTEND_URL}",
    )
    return {"url": session.url}


@router.get("/subscription")
def get_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = current_user.plan or "free"
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    usage = get_monthly_usage(current_user.id, db)

    result = {
        "plan": plan,
        "plan_name": PLAN_INFO.get(plan, {}).get("name", plan.capitalize()),
        "price": PLAN_INFO.get(plan, {}).get("price", 0),
        "usage": usage,
        "limit": limit,
        "has_subscription": bool(current_user.stripe_subscription_id),
    }

    if current_user.stripe_subscription_id:
        try:
            sub = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
            result["status"] = sub.status
            result["current_period_end"] = sub.current_period_end
        except Exception:
            result["status"] = "unknown"

    return result


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event.type == "checkout.session.completed":
        session = event.data.object
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        plan = session.get("metadata", {}).get("plan", "starter")

        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.plan = plan
            user.stripe_subscription_id = subscription_id
            db.commit()

    elif event.type == "customer.subscription.updated":
        sub = event.data.object
        customer_id = sub.get("customer")
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            if sub.get("status") == "active":
                price_id = sub["items"]["data"][0]["price"]["id"] if sub.get("items", {}).get("data") else None
                if price_id and price_id in PRICE_TO_PLAN:
                    user.plan = PRICE_TO_PLAN[price_id]
            user.stripe_subscription_id = sub.get("id")
            db.commit()

    elif event.type == "customer.subscription.deleted":
        sub = event.data.object
        customer_id = sub.get("customer")
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.plan = "free"
            user.stripe_subscription_id = None
            db.commit()

    return JSONResponse(content={"received": True})
