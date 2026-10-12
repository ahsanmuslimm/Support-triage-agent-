"""Contract tests for multi-channel adapters."""

from datetime import datetime

import pytest
from triage.channels import (
    FreshdeskAdapter,
    IntercomAdapter,
    TicketPriority,
    TicketStatus,
    WhatsAppAdapter,
    ZendeskAdapter,
)


@pytest.fixture
def intercom_adapter():
    return IntercomAdapter(tenant_id="acme", api_key="test-key")


@pytest.fixture
def freshdesk_adapter():
    return FreshdeskAdapter(tenant_id="acme", api_key="test-key")


@pytest.fixture
def zendesk_adapter():
    return ZendeskAdapter(tenant_id="acme", api_key="test-key")


@pytest.fixture
def whatsapp_adapter():
    return WhatsAppAdapter(
        tenant_id="acme",
        api_key="test-key",
        phone_number_id="1234567890",
    )


@pytest.mark.asyncio
class TestMessageNormalization:
    """Test message normalization across adapters."""

    async def test_intercom_normalize_message(self, intercom_adapter):
        """Test Intercom message normalization."""
        provider_message = {
            "id": 123,
            "body": "Help needed",
            "author": {"id": "contact_456", "email": "user@example.com", "name": "John"},
            "conversation_id": "conv_789",
            "created_at": "2024-01-15T10:00:00Z",
            "attachments": [],
        }

        result = await intercom_adapter.normalize_message(provider_message)

        assert result.message_id == "123"
        assert result.body == "Help needed"
        assert result.sender_email == "user@example.com"
        assert result.sender_name == "John"
        assert result.thread_id == "conv_789"

    async def test_freshdesk_normalize_message(self, freshdesk_adapter):
        """Test Freshdesk message normalization."""
        provider_message = {
            "id": 999,
            "body": "Issue resolved",
            "user_id": "agent_1",
            "user_name": "Support Team",
            "user_email": "support@acme.com",
            "ticket_id": "5555",
            "created_at": "2024-01-15T11:00:00Z",
            "attachments": [],
        }

        result = await freshdesk_adapter.normalize_message(provider_message)

        assert result.message_id == "999"
        assert result.body == "Issue resolved"
        assert result.sender_id == "agent_1"
        assert result.thread_id == "5555"

    async def test_zendesk_normalize_message(self, zendesk_adapter):
        """Test Zendesk message normalization."""
        provider_message = {
            "id": 777,
            "body": "Please clarify",
            "html_body": "<p>Please clarify</p>",
            "author_id": "user_888",
            "ticket_id": "ticket_999",
            "created_at": "2024-01-15T12:00:00Z",
            "public": True,
            "attachments": [],
        }

        result = await zendesk_adapter.normalize_message(provider_message)

        assert result.message_id == "777"
        assert result.sender_id == "user_888"
        assert result.thread_id == "ticket_999"

    async def test_whatsapp_normalize_message(self, whatsapp_adapter):
        """Test WhatsApp message normalization."""
        provider_message = {
            "id": "wamsg_123",
            "from": "+14155555555",
            "text": {"body": "I need help"},
            "timestamp": "1705315200",
            "profile": {"name": "Customer Name"},
            "type": "text",
            "attachments": [],
        }

        result = await whatsapp_adapter.normalize_message(provider_message)

        assert result.message_id == "wamsg_123"
        assert result.body == "I need help"
        assert result.sender_name == "Customer Name"


@pytest.mark.asyncio
class TestTicketNormalization:
    """Test ticket normalization across adapters."""

    async def test_intercom_normalize_ticket(self, intercom_adapter):
        """Test Intercom ticket normalization."""
        provider_ticket = {
            "id": "conv_123",
            "state": "open",
            "contact": {
                "id": "contact_1",
                "email": "user@example.com",
                "name": "Alice",
            },
            "custom_attributes": {"priority": "p1"},
            "created_at": "2024-01-15T09:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
        }

        result = await intercom_adapter.normalize_ticket(provider_ticket)

        assert result.ticket_id == "conv_123"
        assert result.status == TicketStatus.OPEN
        assert result.priority == TicketPriority.P1
        assert result.requester_email == "user@example.com"

    async def test_freshdesk_normalize_ticket(self, freshdesk_adapter):
        """Test Freshdesk ticket normalization."""
        provider_ticket = {
            "id": 5555,
            "subject": "Bug report",
            "description": "There is a bug",
            "status": 2,  # Open
            "priority": 3,  # High
            "requester_id": 9999,
            "requester": {"email": "customer@example.com", "name": "Bob"},
            "created_at": "2024-01-15T08:00:00Z",
            "updated_at": "2024-01-15T09:00:00Z",
        }

        result = await freshdesk_adapter.normalize_ticket(provider_ticket)

        assert result.ticket_id == "5555"
        assert result.subject == "Bug report"
        assert result.status == TicketStatus.OPEN
        assert result.priority == TicketPriority.P1

    async def test_zendesk_normalize_ticket(self, zendesk_adapter):
        """Test Zendesk ticket normalization."""
        provider_ticket = {
            "id": 88888,
            "subject": "Feature request",
            "description": "Please add feature X",
            "status": "open",
            "priority": "high",
            "requester_id": 777,
            "requester": {"email": "feature@example.com", "name": "Carol"},
            "created_at": "2024-01-15T07:00:00Z",
            "updated_at": "2024-01-15T08:00:00Z",
        }

        result = await zendesk_adapter.normalize_ticket(provider_ticket)

        assert result.ticket_id == "88888"
        assert result.subject == "Feature request"
        assert result.status == TicketStatus.OPEN
        assert result.priority == TicketPriority.P1


@pytest.mark.asyncio
class TestThreadHistory:
    """Test thread history retrieval."""

    async def test_intercom_fetch_thread_history(self, intercom_adapter):
        """Test Intercom thread history."""
        history = await intercom_adapter.fetch_thread_history("conv_123", limit=10)

        assert len(history) > 0
        assert all(hasattr(h, "message_id") for h in history)
        assert all(hasattr(h, "body") for h in history)

    async def test_freshdesk_fetch_thread_history(self, freshdesk_adapter):
        """Test Freshdesk thread history."""
        history = await freshdesk_adapter.fetch_thread_history("5555", limit=20)

        assert len(history) > 0
        assert all(h.sender_type in ("customer", "agent") for h in history)

    async def test_zendesk_fetch_thread_history(self, zendesk_adapter):
        """Test Zendesk thread history."""
        history = await zendesk_adapter.fetch_thread_history("88888", limit=15)

        assert len(history) > 0
        assert all(h.timestamp is not None for h in history)

    async def test_whatsapp_fetch_thread_history(self, whatsapp_adapter):
        """Test WhatsApp thread history."""
        history = await whatsapp_adapter.fetch_thread_history("+14155555555", limit=10)

        assert len(history) > 0


@pytest.mark.asyncio
class TestPostReply:
    """Test posting replies to tickets."""

    async def test_intercom_post_reply(self, intercom_adapter):
        """Test Intercom reply posting."""
        result = await intercom_adapter.post_reply("conv_123", "Thank you for reporting")

        assert result.success
        assert result.provider_message_id != ""

    async def test_freshdesk_post_reply(self, freshdesk_adapter):
        """Test Freshdesk reply posting."""
        result = await freshdesk_adapter.post_reply("5555", "We have fixed this")

        assert result.success

    async def test_zendesk_post_reply(self, zendesk_adapter):
        """Test Zendesk reply posting."""
        result = await zendesk_adapter.post_reply("88888", "Feature coming soon")

        assert result.success

    async def test_whatsapp_post_reply(self, whatsapp_adapter):
        """Test WhatsApp reply posting."""
        from triage.channels.whatsapp import WhatsAppWindow

        # Register active 24h window for this phone
        whatsapp_adapter.windows["+14155555555"] = WhatsAppWindow(datetime.utcnow())

        result = await whatsapp_adapter.post_reply("+14155555555", "Hi there!")

        assert result.success


@pytest.mark.asyncio
class TestUpdateTicket:
    """Test ticket updates."""

    async def test_intercom_update_ticket(self, intercom_adapter):
        """Test Intercom ticket update."""
        from triage.channels import TicketUpdateRequest

        request = TicketUpdateRequest(
            status=TicketStatus.CLOSED,
            custom_fields={"priority": "p0"},
        )
        result = await intercom_adapter.update_ticket("conv_123", request)

        assert result

    async def test_freshdesk_update_ticket(self, freshdesk_adapter):
        """Test Freshdesk ticket update."""
        from triage.channels import TicketUpdateRequest

        request = TicketUpdateRequest(
            priority=TicketPriority.P2,
            tags=["urgent"],
        )
        result = await freshdesk_adapter.update_ticket("5555", request)

        assert result

    async def test_zendesk_update_ticket(self, zendesk_adapter):
        """Test Zendesk ticket update."""
        from triage.channels import TicketUpdateRequest

        request = TicketUpdateRequest(
            status=TicketStatus.SOLVED,
        )
        result = await zendesk_adapter.update_ticket("88888", request)

        assert result
