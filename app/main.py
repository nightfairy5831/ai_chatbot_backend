from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, inspect
from app.core.database import engine, Base
from app.routers import auth, agents, products, prompts, admin
from app.models.product import Product  # noqa: F401 — ensure table is created
from app.models.question import Question  # noqa: F401 — ensure table is created

Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    columns = [c["name"] for c in inspect(engine).get_columns("questions")]
    if "token" not in columns:
        conn.execute(text("ALTER TABLE questions ADD COLUMN token INTEGER DEFAULT 0"))
        conn.commit()

app = FastAPI(title="AI Chatbot SaaS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://146.19.215.88:5173", "https://ai-chatbot-frontend-virid.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(products.router)
app.include_router(prompts.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
