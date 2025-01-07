# models.py
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class MessageLog(Base):
    __tablename__ = 'message_logs'

    id = Column(Integer, primary_key=True)
    phone_number = Column(String(50))
    message = Column(Text)
    response = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50))  # success, error, rate_limited