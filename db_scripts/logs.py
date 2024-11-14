from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from .base import Base

class ConversationLog(Base):
    __tablename__ = "conversation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(50), index=True)
    message = Column(Text)
    response = Column(Text)
    conversation_id = Column(String(100), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata = Column(JSON)

class ErrorLog(Base):
    __tablename__ = "error_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    error_type = Column(String(100))
    error_message = Column(Text)
    stack_trace = Column(Text)
    conversation_id = Column(String(100), nullable=True)
    phone_number = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata = Column(JSON)