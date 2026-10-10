"""Tests for entity validation (Phase 3)."""

import pytest

from triage.entity.validator import EntityValidator
from triage.models.entity import EntityType, ExtractedEntity


class TestEntityValidator:
    """Test EntityValidator."""

    @pytest.fixture
    def validator(self):
        """Create validator for test tenant/customer."""
        return EntityValidator(
            tenant_id="tenant-123",
            customer_id="cust-456",
        )

    @pytest.fixture
    def valid_order_entity(self):
        """Valid ORDER_ID entity."""
        return ExtractedEntity(
            entity_type=EntityType.ORDER_ID,
            value="ORDER-123456",
            normalized_value="123456",
            confidence=0.98,
            linked_id=789,
            is_pii=False,
        )

    def test_validate_high_confidence_linked_entity(self, validator, valid_order_entity):
        """Test validation passes for high-confidence linked entity."""
        result = validator.validate_for_tool(valid_order_entity, linked_tenant_id="tenant-123")
        assert result.valid is True
        assert result.can_bind_to_tool is True
        assert result.cross_tenant_risk is False

    def test_validate_low_confidence_entity(self, validator):
        """Test validation fails for low-confidence entity."""
        entity = ExtractedEntity(
            entity_type=EntityType.ORDER_ID,
            value="ORDER-123",
            confidence=0.7,
            linked_id=789,
        )
        result = validator.validate_for_tool(entity, linked_tenant_id="tenant-123")
        assert result.valid is False
        assert result.can_bind_to_tool is False
        assert "confidence" in result.reason.lower()

    def test_validate_unlinked_entity(self, validator):
        """Test validation fails for unlinked entity."""
        entity = ExtractedEntity(
            entity_type=EntityType.ORDER_ID,
            value="ORDER-123",
            confidence=0.98,
            linked_id=None,  # Not linked
        )
        result = validator.validate_for_tool(entity, linked_tenant_id="tenant-123")
        assert result.valid is False
        assert result.can_bind_to_tool is False
        assert "not linked" in result.reason.lower()

    def test_validate_cross_tenant_leak(self, validator):
        """Test validation fails for cross-tenant entity."""
        entity = ExtractedEntity(
            entity_type=EntityType.ORDER_ID,
            value="ORDER-123",
            confidence=0.98,
            linked_id=789,
        )
        # Entity belongs to different tenant
        result = validator.validate_for_tool(entity, linked_tenant_id="tenant-999")
        assert result.valid is False
        assert result.can_bind_to_tool is False
        assert result.cross_tenant_risk is True
        assert "cross-tenant" in result.reason.lower()

    def test_validate_negative_amount(self, validator):
        """Test validation fails for negative amount."""
        entity = ExtractedEntity(
            entity_type=EntityType.AMOUNT,
            value="-50.00",
            confidence=0.98,
            linked_id=1,
        )
        result = validator.validate_for_tool(entity, linked_tenant_id="tenant-123")
        assert result.valid is False
        assert "negative" in result.reason.lower()

    def test_validate_amount_exceeds_limit(self, validator):
        """Test validation fails for amount > $1M."""
        entity = ExtractedEntity(
            entity_type=EntityType.AMOUNT,
            value="$2000000.00",
            confidence=0.98,
            linked_id=1,
        )
        result = validator.validate_for_tool(entity, linked_tenant_id="tenant-123")
        assert result.valid is False
        assert "exceeds" in result.reason.lower() or "limit" in result.reason.lower()

    def test_validate_valid_amount(self, validator):
        """Test validation passes for valid amount."""
        entity = ExtractedEntity(
            entity_type=EntityType.AMOUNT,
            value="$99.99",
            confidence=0.98,
            linked_id=1,
        )
        result = validator.validate_for_tool(entity, linked_tenant_id="tenant-123")
        assert result.valid is True
        assert result.can_bind_to_tool is True

    def test_validate_batch(self, validator, valid_order_entity):
        """Test batch validation of multiple entities."""
        entity2 = ExtractedEntity(
            entity_type=EntityType.AMOUNT,
            value="$50.00",
            confidence=0.95,
            linked_id=2,
        )
        results = validator.validate_entities_batch(
            [valid_order_entity, entity2],
            linked_tenant_ids={
                "ORDER_ID": "tenant-123",
                "AMOUNT": "tenant-123",
            },
        )
        assert len(results) == 2
        assert results[0].valid is True
        assert results[1].valid is True

    def test_validate_batch_with_cross_tenant(self, validator, valid_order_entity):
        """Test batch validation detects cross-tenant risk."""
        entity2 = ExtractedEntity(
            entity_type=EntityType.AMOUNT,
            value="$50.00",
            confidence=0.95,
            linked_id=2,
        )
        results = validator.validate_entities_batch(
            [valid_order_entity, entity2],
            linked_tenant_ids={
                "ORDER_ID": "tenant-999",  # Cross-tenant!
                "AMOUNT": "tenant-123",
            },
        )
        assert results[0].cross_tenant_risk is True
        assert results[1].cross_tenant_risk is False
