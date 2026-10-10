"""Tests for idempotency management."""

import pytest
from triage.ingestion.idempotency import IdempotencyManager


def test_compute_body_hash():
    """Test body hash computation."""
    body = "Hello World"
    hash1 = IdempotencyManager.compute_body_hash(body)
    hash2 = IdempotencyManager.compute_body_hash(body)

    assert hash1 == hash2  # Deterministic
    assert len(hash1) == 64  # SHA256 hex


def test_body_hash_whitespace_normalized():
    """Test that body hash ignores leading/trailing whitespace."""
    hash1 = IdempotencyManager.compute_body_hash("  Hello World  ")
    hash2 = IdempotencyManager.compute_body_hash("Hello World")

    assert hash1 == hash2


def test_generate_key_with_provider_id():
    """Test key generation with provider message ID."""
    key = IdempotencyManager.generate_key(
        tenant_id="tenant-1",
        provider_message_id="msg-12345",
    )

    assert key == "tenant-1#msg-12345"
    assert key == IdempotencyManager.generate_key(
        tenant_id="tenant-1",
        provider_message_id="msg-12345",
    )


def test_generate_key_with_sender_and_hash():
    """Test key generation with sender ID and body hash."""
    key = IdempotencyManager.generate_key(
        tenant_id="tenant-1",
        sender_id="user-456",
        body_hash="abcd1234",
    )

    assert key == "tenant-1#user-456#abcd1234"


def test_generate_key_provider_id_takes_priority():
    """Test that provider_message_id takes priority over sender+hash."""
    key1 = IdempotencyManager.generate_key(
        tenant_id="tenant-1",
        provider_message_id="msg-99",
        sender_id="user-456",
        body_hash="abcd1234",
    )

    assert key1 == "tenant-1#msg-99"


def test_generate_key_requires_either_provider_or_sender_hash():
    """Test that at least provider_id or (sender_id + hash) is required."""
    with pytest.raises(ValueError):
        IdempotencyManager.generate_key(
            tenant_id="tenant-1",
            provider_message_id=None,
            sender_id="user-456",
            body_hash=None,  # Missing body_hash
        )


def test_is_duplicate_true():
    """Test duplicate detection."""
    assert IdempotencyManager.is_duplicate("existing-msg-id") is True


def test_is_duplicate_false():
    """Test non-duplicate detection."""
    assert IdempotencyManager.is_duplicate(None) is False
