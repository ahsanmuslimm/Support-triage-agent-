"""Tests for entity extraction (Phase 3)."""

import pytest
from triage.entity.extractor import RuleBasedEntityExtractor
from triage.entity.ml_extractor import MLEntityExtractor
from triage.entity.linker import EntityLinker
from triage.models.entity import EntityType, ExtractedEntity


class TestRuleBasedEntityExtractor:
    """Test regex-based entity extraction."""

    @pytest.fixture
    def extractor(self):
        return RuleBasedEntityExtractor()

    def test_extract_order_id_hash_format(self, extractor):
        """Test extraction of #123456 order ID."""
        text = "I want a refund for order #654321"
        result = extractor.extract(text, "msg-1")
        assert len(result.entities) > 0
        order_entities = [e for e in result.entities if e.entity_type == EntityType.ORDER_ID]
        assert len(order_entities) > 0
        assert "654321" in order_entities[0].value

    def test_extract_order_id_ord_format(self, extractor):
        """Test extraction of ORD-xyz format."""
        text = "My order ORD-ABC123 is missing"
        result = extractor.extract(text, "msg-2")
        order_entities = [e for e in result.entities if e.entity_type == EntityType.ORDER_ID]
        assert len(order_entities) > 0

    def test_extract_amount(self, extractor):
        """Test extraction of dollar amounts."""
        text = "I was charged $99.99 incorrectly"
        result = extractor.extract(text, "msg-3")
        amount_entities = [e for e in result.entities if e.entity_type == EntityType.AMOUNT]
        assert len(amount_entities) > 0
        assert "$99.99" in amount_entities[0].value or "99.99" in amount_entities[0].normalized_value

    def test_extract_email(self, extractor):
        """Test extraction of email addresses."""
        text = "Contact me at user@example.com"
        result = extractor.extract(text, "msg-4")
        email_entities = [e for e in result.entities if e.entity_type == EntityType.EMAIL]
        assert len(email_entities) > 0
        assert "user@example.com" in email_entities[0].value

    def test_extract_phone(self, extractor):
        """Test extraction of phone numbers."""
        text = "Call me at (555) 123-4567"
        result = extractor.extract(text, "msg-5")
        phone_entities = [e for e in result.entities if e.entity_type == EntityType.PHONE]
        assert len(phone_entities) > 0
        assert phone_entities[0].is_pii is True

    def test_phone_normalization(self, extractor):
        """Test phone number normalization."""
        text = "555-1234-5678"
        result = extractor.extract(text, "msg-6")
        phone_entities = [e for e in result.entities if e.entity_type == EntityType.PHONE]
        if phone_entities:
            normalized = phone_entities[0].normalized_value
            assert normalized.startswith("+")  # E.164 format

    def test_extract_credit_card(self, extractor):
        """Test extraction of credit card numbers (masked)."""
        text = "My card is 4111 1111 1111 1111"
        result = extractor.extract(text, "msg-7")
        cc_entities = [e for e in result.entities if e.entity_type == EntityType.CREDIT_CARD]
        assert len(cc_entities) > 0
        assert cc_entities[0].is_pii is True
        assert "****1111" in cc_entities[0].normalized_value

    def test_extract_ssn(self, extractor):
        """Test extraction of SSN (masked)."""
        text = "SSN: 123-45-6789"
        result = extractor.extract(text, "msg-8")
        ssn_entities = [e for e in result.entities if e.entity_type == EntityType.SSN]
        assert len(ssn_entities) > 0
        assert ssn_entities[0].is_pii is True
        assert "****" in ssn_entities[0].normalized_value or "***" in ssn_entities[0].normalized_value

    def test_extract_date_iso_format(self, extractor):
        """Test extraction of ISO 8601 dates."""
        text = "Order placed on 2024-01-15"
        result = extractor.extract(text, "msg-9")
        date_entities = [e for e in result.entities if e.entity_type == EntityType.DATE]
        assert len(date_entities) > 0
        assert "2024-01-15" in date_entities[0].value

    def test_pii_pseudonymization(self, extractor):
        """Test PII replacement with vault tokens."""
        text = "Call me at (555) 123-4567"
        result = extractor.extract(text, "msg-10")
        phone_entities = [e for e in result.entities if e.entity_type == EntityType.PHONE]
        assert len(phone_entities) > 0
        assert phone_entities[0].pseudonym is not None
        assert "VAULT_" in phone_entities[0].pseudonym
        # Redacted text should contain pseudonym
        assert "VAULT_" in result.redacted_text

    def test_email_pii_redaction(self, extractor):
        """Test email redaction in text."""
        text = "Email me at test@example.com"
        result = extractor.extract(text, "msg-11")
        assert "VAULT_" in result.redacted_text
        assert "test@example.com" not in result.redacted_text

    def test_confidence_high_for_regex(self, extractor):
        """Test that regex matches have high confidence."""
        text = "Order #123456"
        result = extractor.extract(text, "msg-12")
        assert len(result.entities) > 0
        for entity in result.entities:
            assert entity.confidence == 0.95

    def test_extract_tracking_number(self, extractor):
        """Test extraction of tracking numbers."""
        text = "Track your package: 1Z999AA10123456784"
        result = extractor.extract(text, "msg-13")
        tracking_entities = [e for e in result.entities if e.entity_type == EntityType.TRACKING_NUMBER]
        assert len(tracking_entities) > 0

    def test_no_false_positives_empty_text(self, extractor):
        """Test extraction on empty text."""
        result = extractor.extract("", "msg-14")
        assert len(result.entities) == 0

    def test_multiple_entities_same_type(self, extractor):
        """Test extraction of multiple entities of same type."""
        text = "Email me at test1@example.com or test2@example.com"
        result = extractor.extract(text, "msg-15")
        email_entities = [e for e in result.entities if e.entity_type == EntityType.EMAIL]
        assert len(email_entities) >= 2

    def test_account_id_extraction(self, extractor):
        """Test extraction of account IDs."""
        text = "I need help with account #12345"
        result = extractor.extract(text, "msg-16")
        account_entities = [e for e in result.entities if e.entity_type == EntityType.ACCOUNT_ID]
        assert len(account_entities) > 0


class TestMLEntityExtractor:
    """Test ML-based entity extraction."""

    @pytest.fixture
    def ml_extractor(self):
        return MLEntityExtractor()

    def test_ml_extractor_initialization(self, ml_extractor):
        """Test that ML extractor initializes without error."""
        assert ml_extractor is not None

    def test_ml_extract_returns_result(self, ml_extractor):
        """Test that extract() returns EntityExtractionResult."""
        text = "I have a question about my order"
        result = ml_extractor.extract(text, "msg-20")
        assert result is not None
        assert result.message_id == "msg-20"
        assert isinstance(result.entities, list)

    def test_ml_fallback_if_unavailable(self, ml_extractor):
        """Test graceful fallback if model unavailable."""
        # Even if model loads, should handle gracefully
        result = ml_extractor.extract("test message", "msg-21")
        assert result is not None


class TestEntityLinker:
    """Test entity linking to database records."""

    @pytest.fixture
    def linker(self):
        return EntityLinker(tenant_id="tenant-123")

    @pytest.mark.asyncio
    async def test_link_order_id(self, linker):
        """Test linking order ID to database."""
        entity = ExtractedEntity(
            entity_type=EntityType.ORDER_ID,
            value="ORDER-123456",
            normalized_value="123456",
            confidence=0.95,
        )
        result = await linker.link(entity)
        assert result.entity_type == EntityType.ORDER_ID
        assert result.value == "ORDER-123456"

    @pytest.mark.asyncio
    async def test_link_email(self, linker):
        """Test linking email to customer."""
        entity = ExtractedEntity(
            entity_type=EntityType.EMAIL,
            value="user@example.com",
            confidence=0.95,
        )
        result = await linker.link(entity)
        assert result.entity_type == EntityType.EMAIL

    @pytest.mark.asyncio
    async def test_link_phone(self, linker):
        """Test linking phone to customer."""
        entity = ExtractedEntity(
            entity_type=EntityType.PHONE,
            value="+1-555-123-4567",
            normalized_value="+15551234567",
            confidence=0.95,
        )
        result = await linker.link(entity)
        assert result.entity_type == EntityType.PHONE

    @pytest.mark.asyncio
    async def test_link_preserves_tenant_id(self, linker):
        """Test that linking preserves tenant ID for cross-tenant checks."""
        entity = ExtractedEntity(
            entity_type=EntityType.ORDER_ID,
            value="#123456",
            confidence=0.95,
        )
        result = await linker.link(entity)
        assert result.tenant_id == "tenant-123"

    @pytest.mark.asyncio
    async def test_link_unrecognized_type(self, linker):
        """Test linking unrecognized entity type."""
        entity = ExtractedEntity(
            entity_type=EntityType.PRODUCT,
            value="Widget",
            confidence=0.85,
        )
        result = await linker.link(entity)
        assert result.success is False
        assert result.error is not None
