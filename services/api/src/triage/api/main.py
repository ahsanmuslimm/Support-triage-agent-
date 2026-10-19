"""FastAPI application factory and main entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..db import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the DB engine on startup and dispose it on shutdown."""
    await init_db(app)
    yield
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
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
