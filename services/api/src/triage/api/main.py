"""FastAPI application factory and main entry point."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="Triage API",
        description="Message ingestion and streaming for AI-powered support triage",
        version="0.1.0",
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
    from .endpoints import messages, webhooks, conversations

    # Register routers
    app.include_router(messages.router, prefix="/api/v1", tags=["messages"])
    app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
    app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])

    # Health checks
    @app.get("/health", tags=["system"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    async def readiness_check():
        """Readiness check endpoint."""
        # TODO: Check database, Redis, Zendesk API connectivity
        return {"status": "ready"}

    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
