# db_scripts/base.py

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from core.config import settings
from contextlib import asynccontextmanager

# Convert the standard DB URL to async format
# Example: postgresql:// -> postgresql+asyncpg://
def get_async_db_url(url: str) -> str:
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    return url

SQLALCHEMY_DATABASE_URL = get_async_db_url(settings.DATABASE_URL)

# Create async engine
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    echo=settings.DEBUG
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Create Base class for declarative models
Base = declarative_base()

@asynccontextmanager
async def get_db():
    """Async context manager for database sessions"""
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception as e:
        await session.rollback()
        raise e
    finally:
        await session.close()

# Additional helper for dependency injection in FastAPI
async def get_db_dependency():
    """Dependency for FastAPI endpoints"""
    async with get_db() as session:
        yield session

# Function to initialize tables (useful for testing)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Function to close all connections
async def close_db():
    await engine.dispose()