"""Unit tests for S3.1 Customer Enricher."""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from services.api.src.triage.enrichment.customer_enricher import CustomerEnricher
from services.api.src.triage.enrichment.models import CustomerContext
from services.api.src.triage.enrichment.base import CacheManager
from services.api.src.triage.enrichment.exceptions import APITimeoutError, EnrichmentError


@pytest.fixture
def cache_manager():
    """Mock cache manager."""
    manager = MagicMock()
    manager.get = AsyncMock(return_value=None)
    manager.set = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def enricher(cache_manager):
    """Create enricher with mocks."""
    return CustomerEnricher(
        cache_manager=cache_manager,
        shopify_client=None,
        stripe_client=None,
        db_session=None,
    )


@pytest.mark.asyncio
async def test_enrich_from_cache(enricher, cache_manager):
    """Test that cached context is returned when available."""
    cached_context = {
        "customer_id": 123,
        "tenant_id": 1,
        "name": "John Doe",
        "email": "john@example.com",
        "account_age_days": 365,
        "order_count": 5,
        "total_spent": 1500.0,
        "account_created_at": None,
        "last_order_date": None,
        "avg_order_value": 300.0,
        "subscription_status": "active",
        "subscription_plan": "pro",
        "plan_value_usd": 49.0,
        "flags": [],
        "is_vip": True,
        "is_at_risk": False,
        "is_fraud_flagged": False,
        "fetched_at": None,
        "cache_ttl_seconds": 3600,
    }
    cache_manager.get = AsyncMock(return_value=json.dumps(cached_context))

    result = await enricher.enrich(123, 1)

    assert result.name == "John Doe"
    assert result.order_count == 5
    cache_manager.get.assert_called_once()


@pytest.mark.asyncio
async def test_enrich_cache_miss(enricher, cache_manager):
    """Test enrichment when cache misses and APIs are unavailable (no APIs configured)."""
    cache_manager.get = AsyncMock(return_value=None)
    # When shopify/stripe are None, methods will not be called
    # This tests graceful degradation
    
    with pytest.raises(EnrichmentError):
        await enricher.enrich(123, 1)
    
    cache_manager.get.assert_called_once()


def test_customer_context_creation():
    """Test CustomerContext dataclass creation."""
    context = CustomerContext(
        customer_id=123,
        tenant_id=1,
        name="John Doe",
        email="john@example.com",
        account_age_days=365,
        order_count=10,
        total_spent=5000.0,
        is_vip=True,
    )
    
    assert context.customer_id == 123
    assert context.is_vip is True
    assert context.is_fraud_flagged is False


@pytest.mark.asyncio
async def test_cache_key_generation(enricher):
    """Test cache key generation includes tenant isolation."""
    key = enricher._make_cache_key(1, 123, "customer_enrichment")
    
    assert "customer_enrichment:1:123" == key
    assert "1" in key  # Tenant ID present
    assert "123" in key  # Customer ID present


def test_customer_context_dict_conversion():
    """Test CustomerContext to dict conversion."""
    context = CustomerContext(
        customer_id=123,
        tenant_id=1,
        name="Test",
        email="test@example.com",
    )
    
    data = context.__dict__
    assert data["customer_id"] == 123
    assert data["name"] == "Test"
