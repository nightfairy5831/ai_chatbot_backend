"""
Seed script — creates default admin and test client users.

Usage:
    python seed.py

Credentials:
    Admin  — admin@aiagent.com / admin123
    Client — user@aiagent.com / client123
"""

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.agent import Agent  # noqa: F401
from app.models.product import Product  # noqa: F401
from app.models.question import Question  # noqa: F401


SEEDS = [
    {
        "username": "admin",
        "email": "admin@aiagent.com",
        "password": "admin123",
        "role": "admin",
    },
    {
        "username": "testuser",
        "email": "user@aiagent.com",
        "password": "client123",
        "role": "client",
    },
]


def seed():
    db = SessionLocal()
    try:
        for data in SEEDS:
            existing = db.query(User).filter(User.email == data["email"]).first()
            if existing:
                print(f"  ✓ {data['role']:6s} | {data['email']} (already exists)")
                continue

            user = User(
                username=data["username"],
                email=data["email"],
                hashed_password=hash_password(data["password"]),
                role=data["role"],
            )
            db.add(user)
            db.commit()
            print(f"  + {data['role']:6s} | {data['email']} created")
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding users...")
    seed()
    print("Done.")
