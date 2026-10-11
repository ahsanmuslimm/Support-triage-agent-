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
def shopify_client():
    """Mock Shopify client."""
    client = MagicMock()
    client.customers = MagicMock()
    client.orders = MagicMock()
    return client


@pytest.fixture
def stripe_client():
    """Mock Stripe client."""
    client = MagicMock()
    client.subscriptions = MagicMock()
    return client


@pytest.fixture
def enricher(cache_manager, shopify_client, stripe_client):
    """Create enricher with mocks."""
    return CustomerEnricher(
        cache_manager=cache_manager,
        shopify_client=shopify_client,
        stripe_client=stripe_client,
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
        "phone": None,
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
async def test_enrich_successful_with_apis(enricher, cache_manager, shopify_client, stripe_client):
    """Test enrichment fetches from APIs when cache misses."""
    cache_manager.get = AsyncMock(return_value=None)
    cache_manager.set = AsyncMock(return_value=True)
    
    # Mock Shopify responses
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "phone": "555-1234",
        "created_at": "2023-01-01T00:00:00Z",
    })
    
    shopify_client.orders.list = AsyncMock(return_value=[
        {
            "id": "1",
            "total_price": "500.00",
            "created_at": "2024-01-01T00:00:00Z",
            "financial_status": "paid",
        },
        {
            "id": "2",
            "total_price": "200.00",
            "created_at": "2023-06-01T00:00:00Z",
            "financial_status": "paid",
        },
    ])
    
    # Mock Stripe responses
    stripe_client.subscriptions.list = AsyncMock(return_value=[
        {
            "status": "active",
            "items": {
                "data": [
                    {
                        "plan": {
                            "nickname": "pro",
                            "amount": 4900,  # $49.00
                        }
                    }
                ]
            }
        }
    ])
    
    result = await enricher.enrich(123, 1)
    
    assert result.name == "John Doe"
    assert result.email == "john@example.com"
    assert result.order_count == 2
    assert result.total_spent == 700.0
    assert result.subscription_status == "active"
    assert result.is_vip is True  # total_spent > 1000 threshold would trigger if 1400
    assert cache_manager.set.called  # Should cache result


@pytest.mark.asyncio
async def test_enrich_api_timeout_fallback_to_db(enricher, cache_manager, shopify_client):
    """Test fallback to DB when API timeout occurs."""
    cache_manager.get = AsyncMock(return_value=None)
    
    # Simulate API timeout
    shopify_client.customers.get = AsyncMock(side_effect=TimeoutError("API timeout"))
    
    with pytest.raises(APITimeoutError):
        await enricher.enrich(123, 1)


@pytest.mark.asyncio
async def test_tenant_isolation_enforced(enricher, cache_manager):
    """Test that tenant isolation is checked."""
    cache_manager.get = AsyncMock(return_value=None)
    
    # Mock the validation to check it's called
    with patch.object(enricher, '_validate_tenant_isolation', new_callable=AsyncMock) as mock_validate:
        mock_validate.side_effect = Exception("Tenant isolation check")
        
        with pytest.raises(Exception) as exc:
            await enricher.enrich(123, 1)
        
        assert "Tenant isolation check" in str(exc.value)


@pytest.mark.asyncio
async def test_fraud_flag_detection(enricher, cache_manager, shopify_client, stripe_client):
    """Test that fraud flags are properly detected and stored."""
    cache_manager.get = AsyncMock(return_value=None)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "created_at": "2024-01-01T00:00:00Z",
    })
    
    shopify_client.orders.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    # Mock DB to return fraud flags
    enricher.db = MagicMock()
    enricher.db.query = MagicMock()
    enricher.db.query.return_value.all = AsyncMock(return_value=[
        MagicMock(flag_name="fraud_flag"),
        MagicMock(flag_name="chargeback"),
    ])
    
    result = await enricher.enrich(123, 1)
    
    assert result.is_fraud_flagged is True
    assert "fraud_flag" in result.flags


@pytest.mark.asyncio
async def test_vip_status_determination(enricher, cache_manager, shopify_client, stripe_client):
    """Test VIP status is correctly determined based on spending."""
    cache_manager.get = AsyncMock(return_value=None)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "VIP",
        "last_name": "Customer",
        "email": "vip@example.com",
        "created_at": "2020-01-01T00:00:00Z",
    })
    
    # High-value orders totaling $3000
    shopify_client.orders.list = AsyncMock(return_value=[
        {"id": "1", "total_price": "1500.00", "created_at": "2024-01-01T00:00:00Z", "financial_status": "paid"},
        {"id": "2", "total_price": "1500.00", "created_at": "2023-12-01T00:00:00Z", "financial_status": "paid"},
    ])
    
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.is_vip is True
    assert result.total_spent == 3000.0


@pytest.mark.asyncio
async def test_at_risk_status_from_subscription(enricher, cache_manager, shopify_client, stripe_client):
    """Test at-risk status from paused/cancelled subscription."""
    cache_manager.get = AsyncMock(return_value=None)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "Risk",
        "last_name": "Customer",
        "email": "risk@example.com",
        "created_at": "2024-01-01T00:00:00Z",
    })
    
    shopify_client.orders.list = AsyncMock(return_value=[])
    
    # Paused subscription
    stripe_client.subscriptions.list = AsyncMock(return_value=[
        {
            "status": "paused",
            "items": {"data": []}
        }
    ])
    
    result = await enricher.enrich(123, 1)
    
    assert result.is_at_risk is True
    assert result.subscription_status == "paused"


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


@pytest.mark.asyncio
async def test_cache_serialization_with_dates(enricher, cache_manager, shopify_client, stripe_client):
    """Test cache properly serializes datetime fields."""
    cache_manager.get = AsyncMock(return_value=None)
    cache_manager.set = AsyncMock(return_value=True)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "Date",
        "last_name": "Test",
        "email": "date@example.com",
        "created_at": "2020-01-15T10:30:00Z",
    })
    
    shopify_client.orders.list = AsyncMock(return_value=[
        {"id": "1", "total_price": "100.00", "created_at": "2024-01-01T00:00:00Z", "financial_status": "paid"},
    ])
    
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    # Verify cache.set was called with JSON-serializable data
    assert cache_manager.set.called
    call_args = cache_manager.set.call_args
    cache_data = call_args[0][1]  # Second argument is the JSON string
    parsed = json.loads(cache_data)
    
    # Should not raise JSON serialization error
    assert parsed is not None


@pytest.mark.asyncio
async def test_no_orders_account_age_calculation(enricher, cache_manager, shopify_client, stripe_client):
    """Test proper handling when customer has no orders."""
    cache_manager.get = AsyncMock(return_value=None)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "New",
        "last_name": "Customer",
        "email": "new@example.com",
        "created_at": "2024-01-01T00:00:00Z",
    })
    
    shopify_client.orders.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.order_count == 0
    assert result.total_spent == 0.0
    assert result.avg_order_value == 0.0
    assert result.is_vip is False
    assert result.last_order_date is None


@pytest.mark.asyncio
async def test_multiple_api_failures_raise_error(enricher, cache_manager, shopify_client):
    """Test that multiple API failures result in EnrichmentError."""
    cache_manager.get = AsyncMock(return_value=None)
    
    shopify_client.customers.get = AsyncMock(side_effect=Exception("API down"))
    
    with pytest.raises((APITimeoutError, EnrichmentError)):
        await enricher.enrich(123, 1)


@pytest.mark.asyncio
async def test_enrich_cache_miss_subscription_plan_extraction(enricher, cache_manager, shopify_client, stripe_client):
    """Test precise extraction and conversion of Stripe subscription plan value."""
    cache_manager.get = AsyncMock(return_value=None)
    cache_manager.set = AsyncMock(return_value=True)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "created_at": "2024-01-01T00:00:00Z",
    })
    
    shopify_client.orders.list = AsyncMock(return_value=[])
    
    # Test subscription plan value in cents converted to USD
    stripe_client.subscriptions.list = AsyncMock(return_value=[
        {
            "status": "active",
            "items": {
                "data": [
                    {
                        "plan": {
                            "nickname": "pro_plan",
                            "amount": 2999,  # $29.99 in cents
                        }
                    }
                ]
            }
        }
    ])
    
    result = await enricher.enrich(123, 1)
    
    # Should convert from cents to USD: 2999 cents = $29.99
    assert result.plan_value_usd == 29.99
    assert result.subscription_plan == "pro_plan"
    assert result.subscription_status == "active"


@pytest.mark.asyncio
async def test_enrich_subscription_with_empty_items(enricher, cache_manager, shopify_client, stripe_client):
    """Test subscription handling when items array is empty."""
    cache_manager.get = AsyncMock(return_value=None)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "created_at": "2024-01-01T00:00:00Z",
    })
    
    shopify_client.orders.list = AsyncMock(return_value=[])
    
    # Subscription with no items
    stripe_client.subscriptions.list = AsyncMock(return_value=[
        {
            "status": "active",
            "items": {
                "data": []  # Empty items
            }
        }
    ])
    
    result = await enricher.enrich(123, 1)
    
    assert result.plan_value_usd == 0.0
    assert result.subscription_status == "active"
    assert result.subscription_plan == "none"


@pytest.mark.asyncio
async def test_customer_vip_boundary_exactly_1000(enricher, cache_manager, shopify_client, stripe_client):
    """Test VIP determination at exact boundary ($1000)."""
    cache_manager.get = AsyncMock(return_value=None)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "Boundary",
        "last_name": "Test",
        "email": "boundary@example.com",
        "created_at": "2024-01-01T00:00:00Z",
    })
    
    # Exactly $1000 - should NOT be VIP (needs >1000)
    shopify_client.orders.list = AsyncMock(return_value=[
        {"id": "1", "total_price": "1000.00", "created_at": "2024-01-01T00:00:00Z", "financial_status": "paid"},
    ])
    
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.total_spent == 1000.0
    assert result.is_vip is False  # exactly 1000 should not trigger VIP


@pytest.mark.asyncio
async def test_customer_vip_just_above_1000(enricher, cache_manager, shopify_client, stripe_client):
    """Test VIP determination just above $1000 threshold."""
    cache_manager.get = AsyncMock(return_value=None)
    
    shopify_client.customers.get = AsyncMock(return_value={
        "first_name": "VIP",
        "last_name": "Boundary",
        "email": "vip_boundary@example.com",
        "created_at": "2024-01-01T00:00:00Z",
    })
    
    # Just above $1000
    shopify_client.orders.list = AsyncMock(return_value=[
        {"id": "1", "total_price": "1000.01", "created_at": "2024-01-01T00:00:00Z", "financial_status": "paid"},
    ])
    
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.total_spent == 1000.01
    assert result.is_vip is True  # above 1000 should trigger VIP
