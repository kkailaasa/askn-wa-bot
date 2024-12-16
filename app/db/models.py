# app/db/models.py

from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base

class MessageLog(Base):
    """Log of all messages processed by the system"""
    __tablename__ = "message_logs"

    id = Column(Integer, primary_key=True, index=True)
    message_sid = Column(String, unique=True, index=True)
    conversation_id = Column(String, index=True)
    from_number = Column(String, index=True)
    to_number = Column(String, index=True)
    message = Column(Text)
    response = Column(Text)
    media_data = Column(JSON, nullable=True)
    processing_time = Column(Integer)  # in milliseconds
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<MessageLog(message_sid={self.message_sid}, from={self.from_number})>"

class ErrorLog(Base):
    """Log of errors that occur in the system"""
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    error_type = Column(String)
    error_message = Column(Text)
    metadata = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<ErrorLog(type={self.error_type}, timestamp={self.timestamp})>"

class RequestLog(Base):
    """Log of all HTTP requests to the system"""
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, index=True)
    message_sid = Column(String, index=True, nullable=True)
    task_id = Column(String, nullable=True)
    twilio_number = Column(String)
    client_ip = Column(String)
    cloudflare_data = Column(JSON, nullable=True)
    request_data = Column(JSON)
    response_status = Column(Integer, default=200)
    processing_time = Column(Integer)  # in milliseconds
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<RequestLog(message_sid={self.message_sid}, status={self.response_status})>"