"""RFC 9457 Problem Details error handling (S10.1)."""

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details for HTTP APIs."""

    type: str = Field(..., description="Problem type URI")
    title: str = Field(..., description="Short human-readable summary")
    status: int = Field(..., description="HTTP status code")
    detail: str | None = Field(None, description="Human-readable explanation")
    instance: str | None = Field(None, description="URI to specific occurrence")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    extensions: dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "type": "https://api.triage.app/problems/invalid-scope",
                "title": "Invalid Scope",
                "status": 403,
                "detail": "API key lacks 'conversations:write' scope",
                "instance": "/api/v1/conversations/conv_123/messages",
            }
        }


class APIError(HTTPException):
    """Base API error with RFC 9457 formatting."""

    def __init__(
        self,
        type: str,
        title: str,
        status_code: int,
        detail: str | None = None,
        instance: str | None = None,
        extensions: dict[str, Any] | None = None,
    ):
        self.type = type
        self.title = title
        self.status_code = status_code
        self.detail_text = detail
        self.instance = instance
        self.extensions = extensions or {}

        # Create problem detail
        problem = ProblemDetail(
            type=type,
            title=title,
            status=status_code,
            detail=detail,
            instance=instance,
            extensions=extensions or {},
        )
        self.detail = problem.model_dump(exclude_none=True)
        super().__init__(
            status_code=status_code,
            detail=self.detail,
        )


# Common error types
class InvalidScopeError(APIError):
    """API key lacks required scope."""

    def __init__(self, required_scope: str, instance: str | None = None):
        super().__init__(
            type="https://api.triage.app/problems/invalid-scope",
            title="Invalid Scope",
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key lacks '{required_scope}' scope",
            instance=instance,
        )


class InvalidAPIKeyError(APIError):
    """Invalid or missing API key."""

    def __init__(self, instance: str | None = None):
        super().__init__(
            type="https://api.triage.app/problems/invalid-api-key",
            title="Invalid API Key",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is invalid, expired, or missing",
            instance=instance,
        )


class ConflictError(APIError):
    """Resource conflict (e.g., duplicate idempotency key)."""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(
            type="https://api.triage.app/problems/conflict",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            instance=instance,
        )


class NotFoundError(APIError):
    """Resource not found."""

    def __init__(self, resource_type: str, resource_id: str, instance: str | None = None):
        super().__init__(
            type="https://api.triage.app/problems/not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_type} '{resource_id}' not found",
            instance=instance,
        )


class PreconditionFailedError(APIError):
    """ETag mismatch or precondition failed."""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(
            type="https://api.triage.app/problems/precondition-failed",
            title="Precondition Failed",
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=detail,
            instance=instance,
        )


class RateLimitError(APIError):
    """Rate limit exceeded."""

    def __init__(self, reset_at: int, instance: str | None = None):
        super().__init__(
            type="https://api.triage.app/problems/rate-limit-exceeded",
            title="Rate Limit Exceeded",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            instance=instance,
            extensions={"reset_at": reset_at},
        )


def format_error_response(error: APIError) -> dict[str, Any]:
    """Format error as RFC 9457 response."""
    return {
        "type": error.type,
        "title": error.title,
        "status": error.status_code,
        "detail": error.detail,
        "instance": error.instance,
        "timestamp": datetime.utcnow().isoformat(),
        **(error.extensions or {}),
    }
