"""Unit tests for S3.2 Order Enricher."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from services.api.src.triage.enrichment.order_enricher import OrderEnricher
from services.api.src.triage.enrichment.base import CacheManager


@pytest.fixture
def cache_manager():
    manager = MagicMock(spec=CacheManager)
    manager.get = AsyncMock(return_value=None)
    manager.set = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def shopify_client():
    client = MagicMock()
    client.orders = MagicMock()
    client.refunds = MagicMock()
    return client


@pytest.fixture
def enricher(cache_manager, shopify_client):
    return OrderEnricher(
        cache_manager=cache_manager,
        shopify_client=shopify_client,
        db_session=None,
    )


@pytest.mark.asyncio
async def test_order_enrichment_basic(enricher, cache_manager, shopify_client):
    """Test basic order enrichment."""
    cache_manager.get.return_value = None

    shopify_client.orders.list = AsyncMock(
        return_value=[
            {
                "id": "1",
                "total_price": "100.00",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "financial_status": "paid",
            },
            {
                "id": "2",
                "total_price": "200.00",
                "created_at": (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z",
                "financial_status": "paid",
            },
        ]
    )
    shopify_client.refunds.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.order_count_90d == 2
    assert result.total_value_90d == 300.0
    assert result.refund_count_90d == 0


@pytest.mark.asyncio
async def test_high_value_order_detection(enricher, cache_manager, shopify_client):
    """Test detection of high-value orders (>$500)."""
    cache_manager.get.return_value = None

    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "600.00", "created_at": datetime.utcnow().isoformat() + "Z", "financial_status": "paid"},
            {"id": "2", "total_price": "400.00", "created_at": (datetime.utcnow() - timedelta(days=5)).isoformat() + "Z", "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.high_value_orders == 1  # Only first order >$500


@pytest.mark.asyncio
async def test_return_rate_calculation(enricher, cache_manager, shopify_client):
    """Test return rate calculation."""
    cache_manager.get.return_value = None

    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": datetime.utcnow().isoformat() + "Z", "financial_status": "paid"},
            {"id": "2", "total_price": "100.00", "created_at": (datetime.utcnow() - timedelta(days=5)).isoformat() + "Z", "financial_status": "paid"},
            {"id": "3", "total_price": "100.00", "created_at": (datetime.utcnow() - timedelta(days=10)).isoformat() + "Z", "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(
        return_value=[
            {"id": "r1", "order_id": "1", "created_at": datetime.utcnow().isoformat() + "Z", "amount": 100.0},
        ]
    )

    result = await enricher.enrich(123, 1)

    assert result.refund_count_90d == 1
    assert result.return_rate == pytest.approx(1/3, 0.01)


@pytest.mark.asyncio
async def test_risk_score_computation(enricher, cache_manager, shopify_client):
    """Test risk score computation."""
    cache_manager.get.return_value = None

    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "600.00", "created_at": datetime.utcnow().isoformat() + "Z", "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(
        return_value=[
            {"id": "r1", "order_id": "1", "created_at": datetime.utcnow().isoformat() + "Z", "amount": 100.0},
            {"id": "r2", "order_id": "1", "created_at": (datetime.utcnow() - timedelta(days=5)).isoformat() + "Z", "amount": 100.0},
            {"id": "r3", "order_id": "1", "created_at": (datetime.utcnow() - timedelta(days=10)).isoformat() + "Z", "amount": 100.0},
            {"id": "r4", "order_id": "1", "created_at": (datetime.utcnow() - timedelta(days=15)).isoformat() + "Z", "amount": 100.0},
        ]
    )

    result = await enricher.enrich(123, 1)

    # Should have risk from high refund count and high-value order
    assert 0.0 <= result.risk_score <= 1.0
    assert result.risk_score > 0.3  # Should be elevated


@pytest.mark.asyncio
async def test_frequency_median_calculation(enricher, cache_manager, shopify_client):
    """Test median ordering frequency."""
    cache_manager.get.return_value = None

    now = datetime.utcnow()
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": now.isoformat() + "Z", "financial_status": "paid"},
            {"id": "2", "total_price": "100.00", "created_at": (now - timedelta(days=10)).isoformat() + "Z", "financial_status": "paid"},
            {"id": "3", "total_price": "100.00", "created_at": (now - timedelta(days=20)).isoformat() + "Z", "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    # Intervals: 10 days, 10 days. Median = 10
    assert result.ordering_frequency_median == 10.0


@pytest.mark.asyncio
async def test_high_velocity_detection(enricher, cache_manager, shopify_client):
    """Test detection of high-velocity ordering (>5 in 30 days)."""
    cache_manager.get.return_value = None

    now = datetime.utcnow()
    orders = [
        {"id": str(i), "total_price": "100.00", "created_at": (now - timedelta(days=i)).isoformat() + "Z", "financial_status": "paid"}
        for i in range(6)
    ]

    shopify_client.orders.list = AsyncMock(return_value=orders)
    shopify_client.refunds.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.is_high_velocity is True
