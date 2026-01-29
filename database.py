"""Database connection and session management."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models import Base


# Async engine for bot
async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Initialize database tables."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Sync engine for migrations/scripts
sync_engine = create_engine(settings.sync_database_url, echo=False)
SyncSessionLocal = sessionmaker(bind=sync_engine)


def init_db_sync():
    """Initialize database tables synchronously."""
    Base.metadata.create_all(sync_engine)
