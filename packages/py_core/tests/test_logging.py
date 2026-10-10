"""Unit tests for structured logging and PII masking."""

import pytest

from py_core.logging import PiiFilter, configure_logging, get_logger


@pytest.mark.unit
def test_pii_filter_masks_email() -> None:
    """Test that PII filter masks email addresses."""
    pii_filter = PiiFilter()

    event_dict = {"email": "user@example.com"}
    result = pii_filter(None, "info", event_dict)
    assert result["email"] == "[REDACTED]"


@pytest.mark.unit
def test_pii_filter_masks_phone() -> None:
    """Test that PII filter masks phone numbers."""
    pii_filter = PiiFilter()

    event_dict = {"phone": "+1 (555) 123-4567"}
    result = pii_filter(None, "info", event_dict)
    assert result["phone"] == "[REDACTED]"


@pytest.mark.unit
def test_pii_filter_masks_email_value_pattern() -> None:
    """Test that PII filter masks email-like values by pattern."""
    pii_filter = PiiFilter()

    event_dict = {"customer_contact": "john.doe@example.com"}
    result = pii_filter(None, "info", event_dict)
    assert result["customer_contact"] == "[REDACTED_EMAIL]"


@pytest.mark.unit
def test_pii_filter_masks_ip_pattern() -> None:
    """Test that PII filter masks IP addresses."""
    pii_filter = PiiFilter()

    event_dict = {"request_source": "192.168.1.1"}
    result = pii_filter(None, "info", event_dict)
    assert result["request_source"] == "[REDACTED_IP]"


@pytest.mark.unit
def test_pii_filter_preserves_non_pii() -> None:
    """Test that PII filter preserves non-PII fields."""
    pii_filter = PiiFilter()

    event_dict = {"user_id": "123", "action": "login", "timestamp": "2024-01-01"}
    result = pii_filter(None, "info", event_dict)
    assert result["user_id"] == "123"
    assert result["action"] == "login"
    assert result["timestamp"] == "2024-01-01"


@pytest.mark.unit
def test_configure_logging_production() -> None:
    """Test logging configuration for production."""
    configure_logging(environment="production")
    logger = get_logger(__name__)
    assert logger is not None


@pytest.mark.unit
def test_configure_logging_development() -> None:
    """Test logging configuration for development."""
    configure_logging(environment="development")
    logger = get_logger(__name__)
    assert logger is not None


@pytest.mark.unit
def test_get_logger_returns_bound_logger() -> None:
    """Test that get_logger returns a BoundLogger."""
    logger = get_logger(__name__)
    assert hasattr(logger, "info")
    assert hasattr(logger, "debug")
    assert hasattr(logger, "error")
