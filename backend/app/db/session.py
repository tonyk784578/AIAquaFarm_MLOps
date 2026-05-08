"""SQLAlchemy async session factory and database initialization.

Uses asyncpg driver to connect to PostgreSQL + TimescaleDB.
TimescaleDB hypertables are created in infra/postgres/init.sql at DB boot.
"""

from collections.abc import AsyncGenerator
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""

    # Subclasses can override __tablename__ to customise the table name.
    pass


# Async engine — shared across the application lifetime
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,  # reconnect on stale connections
    echo=settings.debug,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, Any]:
    """FastAPI dependency that yields an async DB session.

    Commits on success, rolls back on exception, and always closes.

    Yields:
        An open AsyncSession bound to the shared engine.

    Example:
        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Verify database connectivity at startup.

    Schema is managed exclusively by Alembic (`alembic upgrade head`).
    TimescaleDB hypertables and extensions are handled separately in
    infra/postgres/init.sql which runs at container first-start.
    """
    async with engine.connect() as conn:
        await conn.execute(sa.text("SELECT 1"))
    logger.info("database_connection_verified")
