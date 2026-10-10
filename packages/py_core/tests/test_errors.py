"""Unit tests for error handling and Problem Details."""

import pytest

from py_core.errors import (
    EntityNotFoundError,
    MissingTenantContextError,
    ProblemDetail,
    RateLimitError,
    TriageBaseError,
    UnauthorizedError,
    ValidationError,
)


@pytest.mark.unit
def test_problem_detail_serializes_correctly() -> None:
    """Test that ProblemDetail serializes to JSON with all fields."""
    detail = ProblemDetail(
        type="urn:triage:entity_not_found",
        title="Entity Not Found",
        status=404,
        detail="Customer 123 not found",
        instance="/v1/customers/123",
    )

    json_data = detail.model_dump()
    assert json_data["type"] == "urn:triage:entity_not_found"
    assert json_data["title"] == "Entity Not Found"
    assert json_data["status"] == 404
    assert json_data["detail"] == "Customer 123 not found"
    assert json_data["instance"] == "/v1/customers/123"


@pytest.mark.unit
def test_missing_tenant_context_error_to_problem_detail() -> None:
    """Test MissingTenantContextError converts to ProblemDetail."""
    exc = MissingTenantContextError()
    problem = exc.to_problem_detail()

    assert problem.type == "urn:triage:missing_tenant_context"
    assert problem.status == 403
    assert problem.title == "Missing Tenant Context"
    assert "Tenant context is required" in problem.detail


@pytest.mark.unit
def test_entity_not_found_error_to_problem_detail() -> None:
    """Test EntityNotFoundError converts to ProblemDetail."""
    exc = EntityNotFoundError("Conversation 456 not found")
    problem = exc.to_problem_detail(instance="/v1/conversations/456")

    assert problem.type == "urn:triage:entity_not_found"
    assert problem.status == 404
    assert problem.instance == "/v1/conversations/456"


@pytest.mark.unit
def test_validation_error_to_problem_detail() -> None:
    """Test ValidationError converts to ProblemDetail."""
    exc = ValidationError("Invalid email format: not-an-email")
    problem = exc.to_problem_detail()

    assert problem.type == "urn:triage:validation_error"
    assert problem.status == 400
    assert "Invalid email" in problem.detail


@pytest.mark.unit
def test_unauthorized_error_to_problem_detail() -> None:
    """Test UnauthorizedError converts to ProblemDetail."""
    exc = UnauthorizedError("User does not have permission")
    problem = exc.to_problem_detail()

    assert problem.type == "urn:triage:unauthorized"
    assert problem.status == 403


@pytest.mark.unit
def test_rate_limit_error_to_problem_detail() -> None:
    """Test RateLimitError converts to ProblemDetail."""
    exc = RateLimitError("Rate limit of 100 requests/min exceeded")
    problem = exc.to_problem_detail()

    assert problem.type == "urn:triage:rate_limit_exceeded"
    assert problem.status == 429


@pytest.mark.unit
def test_custom_triage_error_to_problem_detail() -> None:
    """Test custom TriageBaseError subclass."""

    class CustomError(TriageBaseError):
        error_code = "custom_error"
        http_status = 418
        title = "I'm a teapot"

    exc = CustomError("This is a test error")
    problem = exc.to_problem_detail()

    assert problem.type == "urn:triage:custom_error"
    assert problem.status == 418
    assert problem.title == "I'm a teapot"
