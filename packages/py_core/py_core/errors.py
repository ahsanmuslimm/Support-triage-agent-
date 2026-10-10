"""Error handling and RFC 9457 Problem Details."""

from pydantic import BaseModel


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details for HTTP APIs.

    Serializes to application/problem+json.
    """

    type: str
    """URI reference identifying the problem type (e.g., 'urn:triage:missing_tenant')."""

    title: str
    """Short, human-readable summary (e.g., 'Missing Tenant Context')."""

    status: int
    """HTTP status code."""

    detail: str
    """Human-readable explanation specific to this occurrence."""

    instance: str | None = None
    """URI reference identifying the specific occurrence (e.g., '/v1/conversations/123')."""

    model_config = {"json_schema_extra": {"examples": []}}


class TriageBaseError(Exception):
    """Base exception for domain errors."""

    error_code: str = "internal_error"
    http_status: int = 500
    title: str = "Internal Error"

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(detail)

    def to_problem_detail(self, instance: str | None = None) -> ProblemDetail:
        """Convert exception to RFC 9457 ProblemDetail.

        Args:
            instance: Optional URI reference for this specific occurrence.

        Returns:
            ProblemDetail: Serializable problem detail object.
        """
        return ProblemDetail(
            type=f"urn:triage:{self.error_code}",
            title=self.title,
            status=self.http_status,
            detail=self.detail,
            instance=instance,
        )


class MissingTenantContextError(TriageBaseError):
    """Raised when tenant context is required but not set."""

    error_code = "missing_tenant_context"
    http_status = 403
    title = "Missing Tenant Context"

    def __init__(self) -> None:
        super().__init__("Tenant context is required but was not set.")


class EntityNotFoundError(TriageBaseError):
    """Raised when a requested entity does not exist."""

    error_code = "entity_not_found"
    http_status = 404
    title = "Entity Not Found"


class ValidationError(TriageBaseError):
    """Raised when input validation fails."""

    error_code = "validation_error"
    http_status = 400
    title = "Validation Error"


class UnauthorizedError(TriageBaseError):
    """Raised when an action is not authorized."""

    error_code = "unauthorized"
    http_status = 403
    title = "Unauthorized"


class RateLimitError(TriageBaseError):
    """Raised when rate limit is exceeded."""

    error_code = "rate_limit_exceeded"
    http_status = 429
    title = "Rate Limit Exceeded"
