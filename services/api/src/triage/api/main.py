"""FastAPI application factory and main entry point."""

import asyncio
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..db import close_db, init_db


def _cors_config() -> tuple[list[str], bool]:
    """Allowed origins + whether credentials are allowed, from CORS_ORIGINS env.

    ``CORS_ORIGINS=*`` enables a credential-less wildcard (dev only). A
    comma-separated list enables credentialed CORS for those origins. When
    unset, localhost dev ports are allowed so the console/widget work locally.
    """
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw == "*":
        return ["*"], False
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if origins:
        return origins, True
    return ["http://localhost:3000", "http://localhost:5173"], True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the DB engine on startup and dispose it on shutdown.

    With WORKER_INPROCESS=1 the outbox-polling triage worker runs as a task
    in this process, so a single-container deployment triages messages
    without a second Railway service (free plan allows only one resource).
    """
    await init_db(app)
    worker_task: asyncio.Task[None] | None = None
    if os.getenv("WORKER_INPROCESS", "").lower() in ("1", "true", "yes"):
        try:
            from triage_worker import run_forever
        except ImportError:
            pass
        else:
            worker_task = asyncio.create_task(run_forever())
    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
        await close_db(app)


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="Triage API",
        description="Message ingestion and streaming for AI-powered support triage",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS
    allow_origins, allow_credentials = _cors_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import routers here to avoid circular imports
    from .endpoints import conversations, messages, webhooks

    # Register routers
    app.include_router(messages.router, prefix="/api/v1", tags=["messages"])
    app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
    app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])

    # Health checks
    @app.get("/health", tags=["system"])
    async def health_check():
        """Liveness probe: process is up."""
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    async def readiness_check():
        """Readiness probe: database connectivity."""
        engine = getattr(app.state, "engine", None)
        if engine is None:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "database": "uninitialized"},
            )
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            # asyncpg can surface raw OSError (e.g. ConnectionRefusedError) on
            # connect failures; a probe must degrade to 503, never 500.
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "database": "unavailable"},
            )
        return {"status": "ready", "database": "ok"}

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
