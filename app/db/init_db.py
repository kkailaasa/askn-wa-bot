# app/db/init_db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.database import Base
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def init_db():
    """Initialize database and create all tables"""
    try:
        # Create engine
        engine = create_engine(
            f"sqlite:///{settings.DB_PATH}",
            connect_args={"check_same_thread": False}
        )

        # Create all tables
        Base.metadata.create_all(bind=engine)

        logger.info("Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        return False