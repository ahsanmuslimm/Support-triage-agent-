"""Database connection and session management."""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from py_core.tenant import get_tenant, set_tenant


async def create_async_engine_from_env() -> AsyncEngine:
    """Create an async SQLAlchemy engine from environment variables.

    Reads DATABASE_URL from environment; defaults to local PostgreSQL.

    Returns:
        AsyncEngine: Configured async engine.
    """
    database_url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres_dev@localhost/triage"
    )

    engine = create_async_engine(
        database_url,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        pool_pre_ping=True,
    )

    return engine


# Create a session factory (to be bound to an engine later)
AsyncSessionFactory = sessionmaker(
    class_=AsyncSession, expire_on_commit=False, autoflush=False, autocommit=False
)


async def get_db_session(
    session_factory: sessionmaker,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.

    Assumes set_tenant() has been called upstream.
    Yields a session with tenant context already set.

    Args:
        session_factory: sessionmaker instance to use.

    Yields:
        AsyncSession: Database session for the request.

    Raises:
        MissingTenantContextError: If tenant context is not set.
    """
    # Verify tenant is set before yielding session
    _ = get_tenant()

    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
