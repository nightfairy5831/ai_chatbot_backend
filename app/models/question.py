from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    question = Column(Text, nullable=False)
    token = Column(Integer, default=0)
    source_channel = Column(String, nullable=False, server_default="web")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    agent = relationship("Agent")
