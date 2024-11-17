# db_scripts/base.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from core.config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any, Optional

# Convert the standard DB URL to async format
def get_async_db_url(url: str) -> str:
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    return url

SQLALCHEMY_DATABASE_URL = get_async_db_url(settings.DATABASE_URL)

# Create async engine
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG
)

# Create both sync and async session factories for compatibility
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions"""
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception as e:
        await session.rollback()
        raise
    finally:
        await session.close()

async def get_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI endpoints"""
    async with get_db() as session:
        yield session

# For backwards compatibility with Celery tasks
def get_sync_db():
    """Sync database session for legacy code"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

__all__ = [
    'Base',
    'get_db',
    'get_db_dependency',
    'get_sync_db',
    'AsyncSessionLocal',
    'SessionLocal',
    'engine'
]