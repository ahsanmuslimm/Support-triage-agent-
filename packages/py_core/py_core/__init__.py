"""Shared Python core library for Triage Agent."""

from py_core.errors import (
    EntityNotFoundError,
    MissingTenantContextError,
    ProblemDetail,
    RateLimitError,
    TriageBaseError,
    UnauthorizedError,
    ValidationError,
)
from py_core.logging import configure_logging, get_logger
from py_core.otel import configure_otel, get_tracer
from py_core.tenant import get_tenant, set_tenant

__version__ = "0.1.0"

__all__ = [
    "ProblemDetail",
    "TriageBaseError",
    "MissingTenantContextError",
    "EntityNotFoundError",
    "ValidationError",
    "UnauthorizedError",
    "RateLimitError",
    "get_tenant",
    "set_tenant",
    "configure_logging",
    "get_logger",
    "configure_otel",
    "get_tracer",
]
