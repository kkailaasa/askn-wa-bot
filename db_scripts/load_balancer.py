from sqlalchemy import Column, Integer, String, DateTime, JSON, Index
from sqlalchemy.sql import func
from .base import Base

class LoadBalancerLog(Base):
    """Model for tracking load balancer redirects and client information"""
    __tablename__ = "load_balancer_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_ip = Column(String(50), comment='Real client IP from CF-Connecting-IP')
    cf_country = Column(String(2), comment='Country code from CF-IPCountry header')
    user_agent = Column(String(200))
    referrer = Column(String(200))
    assigned_number = Column(String(50))
    request_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    additional_data = Column(JSON)  # Stores request_id, other headers, etc.

    __table_args__ = (
        Index('idx_lb_logs_client_ip', 'client_ip'),
        Index('idx_lb_logs_timestamp_client', 'request_timestamp', 'client_ip'),
        Index('idx_lb_logs_assigned_timestamp', 'assigned_number', 'request_timestamp'),
        Index('idx_lb_logs_country', 'cf_country'),
        Index('idx_lb_logs_country_timestamp', 'cf_country', 'request_timestamp'),
    )

class NumberLoadStats(Base):
    """Model for tracking message load per number"""
    __tablename__ = "number_load_stats"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(50))
    messages_per_second = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_number_load_stats_phone_timestamp', 'phone_number', 'timestamp'),
    )