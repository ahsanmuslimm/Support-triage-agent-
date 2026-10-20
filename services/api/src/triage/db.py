"""Database engine/session wiring for the API service.

The engine is created once per process from ``DATABASE_URL`` (lifespan-managed)
and shared across requests. Each request-scoped session sets the
``app.tenant_id`` connection variable so Row-Level Security policies apply
even when connecting as a non-owner role.
"""

from __future__ import annotations

import os
import secrets
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _parse_api_keys(raw: str) -> dict[str, uuid.UUID]:
    """Parse API_KEYS env: comma-separated ``<api-key>:<tenant-uuid>`` pairs."""
    keys: dict[str, uuid.UUID] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key, _, tenant = entry.partition(":")
        try:
            keys[key] = uuid.UUID(tenant.strip())
        except ValueError:
            continue
    return keys


def get_tenant_id(
    request: Request,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> uuid.UUID:
    """FastAPI dependency: resolve the calling tenant to a UUID.

    When the ``API_KEYS`` env is configured, tenants are identified exclusively
    by their ``X-API-Key`` (``<key>:<tenant-uuid>`` pairs) and header-based
    tenancy is rejected. Otherwise (dev mode) the ``X-Tenant-ID`` header is
    used directly.
    """
    configured = _parse_api_keys(os.getenv("API_KEYS", ""))
    if configured:
        if not x_api_key:
            raise HTTPException(status_code=401, detail="X-API-Key header required")
        tenant: uuid.UUID | None = None
        for key, tid in configured.items():
            if secrets.compare_digest(key, x_api_key):
                tenant = tid
                break
        if tenant is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return tenant

    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="X-Tenant-ID must be a UUID") from e


def stable_uuid(value: str) -> uuid.UUID:
    """Map an external string id to a stable UUID.

    Parses standard UUIDs as-is; any other string maps deterministically via
    UUID5 so the same external id always yields the same row.
    """
    try:
        return uuid.UUID(value)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"urn:triage:conversation:{value}")


def normalize_database_url(url: str) -> str:
    """Normalize a DATABASE_URL to the asyncpg SQLAlchemy driver.

    Accepts postgres://, postgresql://, and +psycopg/+asyncpg forms. Hosted
    providers (Neon, Railway, Heroku) hand out libpq-style ``sslmode=``
    query params; asyncpg's connect() only understands ``ssl=``.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # psycopg (sync or async) variant: rewrite to asyncpg for uniformity
    if url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+asyncpg://") and "sslmode=" in url:
        parsed = urlsplit(url)
        query = [
            (("ssl" if k == "sslmode" else k), v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        ]
        url = urlunsplit(parsed._replace(query=urlencode(query)))
    return url


def get_database_url() -> str:
    """Read DATABASE_URL from env with a sensible local default."""
    return normalize_database_url(
        os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/triage")
    )


def create_engine(database_url: str | None = None) -> AsyncEngine:
    """Create the async engine (pool_pre_ping survives DB restarts)."""
    return create_async_engine(
        database_url or get_database_url(),
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    )


async def init_db(app: FastAPI) -> None:
    """Create engine + session factory and attach to app.state."""
    app.state.engine = create_engine()
    app.state.session_factory = async_sessionmaker(
        bind=app.state.engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def close_db(app: FastAPI) -> None:
    """Dispose the engine on shutdown."""
    engine: AsyncEngine | None = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()
        app.state.engine = None


async def get_session(
    request: Request,
    tenant_id: Annotated[uuid.UUID, Depends(get_tenant_id)],
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: tenant-scoped database session.

    Validates the X-Tenant-ID header (matching the API's tenancy model) and
    sets ``app.tenant_id`` on the connection so RLS policies filter rows for
    non-owner database roles.
    """
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )
    if factory is None:
        raise HTTPException(status_code=503, detail="Database not initialized")

    async with factory() as session:
        try:
            # Transaction-local setting: RLS sees it for this transaction only
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
            )
        except (SQLAlchemyError, OSError) as e:
            # asyncpg can surface raw OSError (connection refused) on connect
            raise HTTPException(status_code=503, detail="Database unavailable") from e
        try:
            yield session
        except (SQLAlchemyError, OSError) as e:
            await session.rollback()
            raise HTTPException(status_code=500, detail="Database error") from e


SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]
