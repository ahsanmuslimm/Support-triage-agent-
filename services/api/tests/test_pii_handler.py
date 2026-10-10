"""Tests for PII detection and redaction."""

import pytest
from triage.ingestion.pii_handler import PiiHandler


@pytest.fixture
def handler():
    """Create PII handler."""
    return PiiHandler()


def test_detect_email(handler):
    """Test email detection."""
    text = "Contact me at alice@example.com"
    entities = handler.detect(text)

    assert len(entities) == 1
    assert entities[0].entity_type == "EMAIL"
    assert entities[0].value == "alice@example.com"


def test_detect_phone(handler):
    """Test phone number detection."""
    text = "Call me at (555) 123-4567"
    entities = handler.detect(text)

    assert len(entities) == 1
    assert entities[0].entity_type == "PHONE"


def test_detect_credit_card(handler):
    """Test credit card detection."""
    text = "Card: 1234-5678-9012-3456"
    entities = handler.detect(text)

    assert len(entities) == 1
    assert entities[0].entity_type == "CREDIT_CARD"


def test_detect_ssn(handler):
    """Test SSN detection."""
    text = "My SSN is 123-45-6789"
    entities = handler.detect(text)

    assert len(entities) == 1
    assert entities[0].entity_type == "SSN"


def test_detect_multiple_pii(handler):
    """Test detection of multiple PII types."""
    text = "Email: bob@example.com, Phone: 555-123-4567, SSN: 123-45-6789"
    entities = handler.detect(text)

    assert len(entities) == 3
    entity_types = {e.entity_type for e in entities}
    assert entity_types == {"EMAIL", "PHONE", "SSN"}


def test_redact_email(handler):
    """Test email redaction."""
    text = "Contact alice@example.com"
    redacted, entities, vault = handler.redact(text)

    assert "alice@example.com" not in redacted
    assert "[PII_EMAIL_" in redacted
    assert "alice@example.com" in vault.values()


def test_redact_preserves_structure(handler):
    """Test that redaction preserves sentence structure."""
    text = "Call me at (555) 123-4567 today"
    redacted, _, _ = handler.redact(text)

    assert redacted.startswith("Call me at")
    assert redacted.endswith("today")


def test_rehydrate(handler):
    """Test re-hydration of redacted text."""
    original = "Email: alice@example.com"
    redacted, _, vault = handler.redact(original)

    rehydrated = handler.re_hydrate(redacted, vault)

    assert "alice@example.com" in rehydrated


def test_no_pii_detected(handler):
    """Test text with no PII."""
    text = "This is a normal support request"
    entities = handler.detect(text)

    assert len(entities) == 0

    redacted, _, vault = handler.redact(text)
    assert redacted == text
    assert len(vault) == 0


def test_token_generation_deterministic(handler):
    """Test that tokens are deterministic."""
    token1 = handler._generate_token("EMAIL", "alice@example.com")
    token2 = handler._generate_token("EMAIL", "alice@example.com")

    assert token1 == token2


def test_different_pii_values_different_tokens(handler):
    """Test that different values get different tokens."""
    token1 = handler._generate_token("EMAIL", "alice@example.com")
    token2 = handler._generate_token("EMAIL", "bob@example.com")

    assert token1 != token2
