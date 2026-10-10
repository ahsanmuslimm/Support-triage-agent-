"""Tests for message normalizers."""

import pytest
from datetime import datetime

from triage.ingestion.normalizers import (
    NormalizerFactory,
    EmailNormalizer,
    WebChatNormalizer,
    ZendeskNormalizer,
)
from triage.models.message import ChannelType, SenderType


def test_email_normalizer_basic():
    """Test email normalization."""
    normalizer = EmailNormalizer()

    payload = {
        "from": "alice@example.com",
        "sender_id": "user-1",
        "body": "  Hello World  ",
        "subject": "Test Email",
        "message_id": "<msg-123@example.com>",
    }

    message = normalizer.normalize(
        tenant_id="tenant-1",
        conversation_id="conv-1",
        channel_id="email",
        payload=payload,
    )

    assert message.tenant_id == "tenant-1"
    assert message.channel_type == ChannelType.EMAIL
    assert message.body == "Hello World"
    assert message.sender_email == "alice@example.com"
    assert message.provider_message_id == "<msg-123@example.com>"


def test_email_normalizer_threading():
    """Test email threading detection."""
    normalizer = EmailNormalizer()

    payload = {
        "from": "bob@example.com",
        "sender_id": "user-2",
        "body": "Thanks",
        "in_reply_to": "<msg-100@example.com>",
    }

    message = normalizer.normalize(
        tenant_id="tenant-1",
        conversation_id="conv-1",
        channel_id="email",
        payload=payload,
    )

    assert message.parent_message_id == "<msg-100@example.com>"


def test_web_chat_normalizer():
    """Test web chat normalization."""
    normalizer = WebChatNormalizer()

    payload = {
        "sender_id": "anon-user",
        "body": "I need help with my order",
        "message_id": "msg-abc123",
        "session_id": "sess-xyz",
    }

    message = normalizer.normalize(
        tenant_id="tenant-1",
        conversation_id="conv-1",
        channel_id="web_chat",
        payload=payload,
    )

    assert message.channel_type == ChannelType.WEB_CHAT
    assert message.body == "I need help with my order"
    assert message.metadata["session_id"] == "sess-xyz"


def test_zendesk_normalizer():
    """Test Zendesk normalization."""
    normalizer = ZendeskNormalizer()

    payload = {
        "ticket_id": "12345",
        "author_id": 987654,
        "author_name": "Support Agent",
        "author_email": "agent@zendesk.com",
        "author_type": "agent",
        "comment": {
            "id": 111222333,
            "body": "Ticket resolved",
            "public": False,
            "created_at": "2024-01-01T10:00:00Z",
        },
    }

    message = normalizer.normalize(
        tenant_id="tenant-1",
        conversation_id="conv-1",
        channel_id="zendesk",
        payload=payload,
    )

    assert message.channel_type == ChannelType.ZENDESK
    assert message.sender_type == SenderType.AGENT
    assert message.provider_message_id == "111222333"
    assert message.metadata["ticket_id"] == "12345"


def test_normalizer_factory():
    """Test normalizer factory."""
    normalizer = NormalizerFactory.get_normalizer(ChannelType.EMAIL)
    assert isinstance(normalizer, EmailNormalizer)

    normalizer = NormalizerFactory.get_normalizer(ChannelType.WEB_CHAT)
    assert isinstance(normalizer, WebChatNormalizer)


def test_normalizer_factory_unsupported_channel():
    """Test factory raises error for unsupported channel."""
    with pytest.raises(ValueError):
        NormalizerFactory.get_normalizer(ChannelType.SLACK)


def test_text_normalization():
    """Test text normalization (whitespace, HTML entities)."""
    normalizer = EmailNormalizer()

    payload = {
        "from": "alice@example.com",
        "sender_id": "user-1",
        "body": "  Hello  &amp;  goodbye  ",
        "message_id": "msg-1",
    }

    message = normalizer.normalize(
        tenant_id="tenant-1",
        conversation_id="conv-1",
        channel_id="email",
        payload=payload,
    )

    assert message.body == "Hello & goodbye"
