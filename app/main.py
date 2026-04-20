from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, inspect
from app.core.database import engine, Base
from app.routers import auth, agents, products, prompts, admin, calendar, whatsapp
from app.models.product import Product
from app.models.question import Question
from app.models.calendar_connection import CalendarConnection
from app.models.whatsapp_number import WhatsappNumber
Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    question_columns = [c["name"] for c in inspect(engine).get_columns("questions")]
    if "token" not in question_columns:
        conn.execute(text("ALTER TABLE questions ADD COLUMN token INTEGER DEFAULT 0"))
        conn.commit()
    if "source_channel" not in question_columns:
        conn.execute(text("ALTER TABLE questions ADD COLUMN source_channel VARCHAR DEFAULT 'web'"))
        conn.commit()

    user_columns = [c["name"] for c in inspect(engine).get_columns("users")]
    if "plan" not in user_columns:
        conn.execute(text("ALTER TABLE users ADD COLUMN plan VARCHAR DEFAULT 'free'"))
        conn.commit()

    product_columns = [c["name"] for c in inspect(engine).get_columns("products")]
    if "type" not in product_columns:
        conn.execute(text("ALTER TABLE products ADD COLUMN type VARCHAR DEFAULT 'product'"))
        conn.commit()
    if "purchase_link" not in product_columns:
        conn.execute(text("ALTER TABLE products ADD COLUMN purchase_link VARCHAR"))
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
app.include_router(calendar.router)
app.include_router(whatsapp.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
