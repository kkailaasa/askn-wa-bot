from sqlalchemy import Column, Integer, String, DateTime, Float, JSON
from sqlalchemy.sql import func
from .base import Base

class LoadBalancerLog(Base):
    __tablename__ = "load_balancer_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    client_ip = Column(String(50))
    user_agent = Column(String(200))
    referrer = Column(String(200))
    assigned_number = Column(String(50))
    request_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    additional_data = Column(JSON)

class NumberLoadStats(Base):
    __tablename__ = "number_load_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(50))
    messages_per_second = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())