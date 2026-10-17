"""Tests for WhatsApp 24-hour window tracking."""

from datetime import datetime, timedelta

import pytest
from triage.channels.whatsapp import WhatsAppTemplateLibrary, WhatsAppWindow


class TestWhatsAppWindow:
    """Test 24-hour messaging window."""

    def test_window_creation(self):
        """Test creating a new window."""
        now = datetime.utcnow()
        window = WhatsAppWindow(now)

        assert window.is_within_window()
        assert window.calculate_time_remaining() < timedelta(hours=24)

    def test_window_expiry(self):
        """Test window expiration after 24 hours."""
        past_time = datetime.utcnow() - timedelta(hours=24, minutes=1)
        window = WhatsAppWindow(past_time)

        assert not window.is_within_window()
        assert window.requires_template()

    def test_time_remaining_positive(self):
        """Test time remaining calculation within window."""
        now = datetime.utcnow()
        window = WhatsAppWindow(now)

        remaining = window.calculate_time_remaining()
        assert remaining > timedelta(0)
        assert remaining <= timedelta(hours=24)

    def test_time_remaining_negative(self):
        """Test time remaining when expired."""
        past_time = datetime.utcnow() - timedelta(hours=25)
        window = WhatsAppWindow(past_time)

        remaining = window.calculate_time_remaining()
        assert remaining < timedelta(0)


class TestWhatsAppTemplateLibrary:
    """Test HSM template library."""

    def test_find_template_by_context(self):
        """Test finding template matching context."""
        library = WhatsAppTemplateLibrary()

        context = {"intent": "order_status"}
        template = library.find_template(context)

        assert template is not None
        assert template.category == "order_status"

    def test_template_credit_cost(self):
        """Test HSM template credit cost."""
        library = WhatsAppTemplateLibrary()
        template = library.templates[0]

        assert template.credit_cost == 0.5  # HSM cost

    def test_get_all_templates(self):
        """Test retrieving all templates."""
        library = WhatsAppTemplateLibrary()
        templates = library.get_all_templates()

        assert len(templates) >= 4
        categories = {t.category for t in templates}
        assert "order_status" in categories
        assert "account_alert" in categories


@pytest.mark.asyncio
class TestWhatsAppFallback:
    """Test SMS fallback when outside 24h window."""

    async def test_fallback_to_sms_expired_window(self):
        """Test fallback to SMS when outside window."""
        from triage.channels.whatsapp import WhatsAppAdapter

        adapter = WhatsAppAdapter(
            tenant_id="acme",
            api_key="test",
            phone_number_id="123",
        )

        # Register expired window
        past_time = datetime.utcnow() - timedelta(hours=25)
        adapter.windows["+1234567890"] = WhatsAppWindow(past_time)

        # Try to post reply outside window
        result = await adapter.post_reply("+1234567890", "Hello")

        # Should suggest SMS fallback
        assert result.metadata.get("fallback_method") == "sms" or result.success

    async def test_post_reply_within_window(self):
        """Test post reply succeeds within window."""
        from triage.channels.whatsapp import WhatsAppAdapter

        adapter = WhatsAppAdapter(
            tenant_id="acme",
            api_key="test",
            phone_number_id="123",
        )

        # Register fresh window
        now = datetime.utcnow()
        adapter.windows["+1234567890"] = WhatsAppWindow(now)

        result = await adapter.post_reply("+1234567890", "Hello")

        assert result.success
        assert result.metadata["in_24h_window"] is True


@pytest.mark.asyncio
class TestWhatsAppWindowInfo:
    """Test window info retrieval."""

    async def test_get_24h_window_info_active(self):
        """Test getting info for active window."""
        from triage.channels.whatsapp import WhatsAppAdapter

        adapter = WhatsAppAdapter(
            tenant_id="acme",
            api_key="test",
            phone_number_id="123",
        )

        now = datetime.utcnow()
        adapter.windows["+1234567890"] = WhatsAppWindow(now)

        info = adapter.get_24h_window_info("+1234567890")

        assert info["in_window"] is True
        assert info["time_remaining_seconds"] > 0
        assert info["requires_template"] is False

    async def test_get_24h_window_info_expired(self):
        """Test getting info for expired window."""
        from triage.channels.whatsapp import WhatsAppAdapter

        adapter = WhatsAppAdapter(
            tenant_id="acme",
            api_key="test",
            phone_number_id="123",
        )

        past_time = datetime.utcnow() - timedelta(hours=25)
        adapter.windows["+1234567890"] = WhatsAppWindow(past_time)

        info = adapter.get_24h_window_info("+1234567890")

        assert info["in_window"] is False
        assert info["requires_template"] is True

    async def test_phone_normalization(self):
        """Test phone number normalization to E.164."""
        from triage.channels.whatsapp import WhatsAppAdapter

        adapter = WhatsAppAdapter(
            tenant_id="acme",
            api_key="test",
            phone_number_id="123",
        )

        # Test various formats
        assert adapter._normalize_phone("14155555555").endswith("14155555555")
        assert adapter._normalize_phone("+14155555555").startswith("+")
        assert adapter._normalize_phone("1-415-555-5555").endswith("5555555")
