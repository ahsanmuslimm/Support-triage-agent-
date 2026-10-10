"""Triage API package."""

__all__ = ["create_app"]

def create_app():
    """Create and return FastAPI app (lazy import)."""
    from .api.main import create_app as _create_app
    return _create_app()
