# app/db/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.db.models import Base
from decouple import config
import logging

logger = logging.getLogger(__name__)

# Get the absolute path to the app_data directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, 'app_data', 'chat.db')

# Ensure directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine with logging based on environment
environment = config('ENVIRONMENT', default='production')
engine = create_engine(
    DATABASE_URL,
    echo=environment == 'development',  # SQL logging only in development
    connect_args={"check_same_thread": False}
)

# Create session factory
SessionLocal = scoped_session(sessionmaker(bind=engine))

def init_db():
    """Initialize the database, creating all tables if they don't exist."""
    try:
        Base.metadata.create_all(engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()