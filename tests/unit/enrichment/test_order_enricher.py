"""Unit tests for S3.2 Order Enricher."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from services.api.src.triage.enrichment.order_enricher import OrderEnricher
from services.api.src.triage.enrichment.base import CacheManager
from services.api.src.triage.enrichment.exceptions import APITimeoutError, EnrichmentError


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


def _make_iso_date(dt: datetime) -> str:
    """Convert datetime to ISO format string with Z suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace('+00:00', 'Z')


@pytest.mark.asyncio
async def test_order_enrichment_basic(enricher, cache_manager, shopify_client):
    """Test basic order enrichment."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {
                "id": "1",
                "total_price": "100.00",
                "created_at": _make_iso_date(now),
                "financial_status": "paid",
            },
            {
                "id": "2",
                "total_price": "200.00",
                "created_at": _make_iso_date(thirty_days_ago),
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

    now = datetime.now(tz=timezone.utc)
    five_days_ago = now - timedelta(days=5)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "600.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
            {"id": "2", "total_price": "400.00", "created_at": _make_iso_date(five_days_ago), "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.high_value_orders == 1  # Only first order >$500


@pytest.mark.asyncio
async def test_return_rate_calculation(enricher, cache_manager, shopify_client):
    """Test return rate calculation."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    five_days_ago = now - timedelta(days=5)
    ten_days_ago = now - timedelta(days=10)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
            {"id": "2", "total_price": "100.00", "created_at": _make_iso_date(five_days_ago), "financial_status": "paid"},
            {"id": "3", "total_price": "100.00", "created_at": _make_iso_date(ten_days_ago), "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(
        return_value=[
            {"id": "r1", "order_id": "1", "created_at": _make_iso_date(now), "amount": 100.0},
        ]
    )

    result = await enricher.enrich(123, 1)

    assert result.refund_count_90d == 1
    assert result.return_rate == pytest.approx(1/3, 0.01)


@pytest.mark.asyncio
async def test_risk_score_computation(enricher, cache_manager, shopify_client):
    """Test risk score computation from high value and high refunds."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    five_days_ago = now - timedelta(days=5)
    ten_days_ago = now - timedelta(days=10)
    fifteen_days_ago = now - timedelta(days=15)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "600.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(
        return_value=[
            {"id": "r1", "order_id": "1", "created_at": _make_iso_date(now), "amount": 100.0},
            {"id": "r2", "order_id": "1", "created_at": _make_iso_date(five_days_ago), "amount": 100.0},
            {"id": "r3", "order_id": "1", "created_at": _make_iso_date(ten_days_ago), "amount": 100.0},
            {"id": "r4", "order_id": "1", "created_at": _make_iso_date(fifteen_days_ago), "amount": 100.0},
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

    now = datetime.now(tz=timezone.utc)
    ten_days_ago = now - timedelta(days=10)
    twenty_days_ago = now - timedelta(days=20)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
            {"id": "2", "total_price": "100.00", "created_at": _make_iso_date(ten_days_ago), "financial_status": "paid"},
            {"id": "3", "total_price": "100.00", "created_at": _make_iso_date(twenty_days_ago), "financial_status": "paid"},
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

    now = datetime.now(tz=timezone.utc)
    orders = [
        {"id": str(i), "total_price": "100.00", "created_at": _make_iso_date(now - timedelta(days=i)), "financial_status": "paid"}
        for i in range(6)
    ]

    shopify_client.orders.list = AsyncMock(return_value=orders)
    shopify_client.refunds.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.is_high_velocity is True


@pytest.mark.asyncio
async def test_cache_hit_on_order_enrichment(enricher, cache_manager, shopify_client):
    """Test that cached order context is used when available."""
    import json
    cached_context = {
        "customer_id": 123,
        "tenant_id": 1,
        "order_count_90d": 5,
        "total_value_90d": 1000.0,
        "refund_count_90d": 1,
        "return_rate": 0.2,
        "high_value_orders": 2,
        "risk_score": 0.3,
        "is_high_velocity": False,
        "ordering_frequency_median": 10.0,
    }
    cache_manager.get.return_value = json.dumps(cached_context)
    
    result = await enricher.enrich(123, 1)
    
    assert result.order_count_90d == 5
    assert result.total_value_90d == 1000.0
    shopify_client.orders.list.assert_not_called()  # Should not fetch from API


@pytest.mark.asyncio
async def test_no_orders_in_90_days(enricher, cache_manager, shopify_client):
    """Test handling when customer has no orders in last 90 days."""
    cache_manager.get.return_value = None
    
    shopify_client.orders.list = AsyncMock(return_value=[])
    shopify_client.refunds.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.order_count_90d == 0
    assert result.total_value_90d == 0.0
    assert result.high_value_orders == 0
    assert result.is_high_velocity is False


@pytest.mark.asyncio
async def test_orders_outside_90_day_window_excluded(enricher, cache_manager, shopify_client):
    """Test that orders older than 90 days are excluded."""
    cache_manager.get.return_value = None
    
    now = datetime.now(tz=timezone.utc)
    sixty_days_ago = now - timedelta(days=60)
    one_hundred_days_ago = now - timedelta(days=100)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": _make_iso_date(sixty_days_ago), "financial_status": "paid"},
            {"id": "2", "total_price": "200.00", "created_at": _make_iso_date(one_hundred_days_ago), "financial_status": "paid"},  # Too old
        ]
    )
    shopify_client.refunds.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.order_count_90d == 1
    assert result.total_value_90d == 100.0


@pytest.mark.asyncio
async def test_multiple_refunds_trigger_risk(enricher, cache_manager, shopify_client):
    """Test that >3 refunds in 90d triggers high risk."""
    cache_manager.get.return_value = None
    
    now = datetime.now(tz=timezone.utc)
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(
        return_value=[
            {"id": "r1", "order_id": "1", "created_at": _make_iso_date(now - timedelta(days=i)), "amount": 25.0}
            for i in range(5)  # 5 refunds
        ]
    )
    
    result = await enricher.enrich(123, 1)
    
    assert result.refund_count_90d > 3
    assert result.risk_score > 0.5  # Should be significantly elevated


@pytest.mark.asyncio
async def test_api_timeout_raises_error(enricher, cache_manager, shopify_client):
    """Test API timeout handling."""
    cache_manager.get.return_value = None
    shopify_client.orders.list = AsyncMock(side_effect=TimeoutError("API timeout"))
    
    with pytest.raises(APITimeoutError):
        await enricher.enrich(123, 1)


@pytest.mark.asyncio
async def test_cache_serialization(enricher, cache_manager, shopify_client):
    """Test that results are properly cached."""
    cache_manager.get.return_value = None
    cache_manager.set = AsyncMock(return_value=True)
    
    now = datetime.now(tz=timezone.utc)
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    # Verify cache.set was called
    assert cache_manager.set.called
    
    # Verify cache contains valid JSON
    call_args = cache_manager.set.call_args
    cache_data = call_args[0][1]
    import json
    parsed = json.loads(cache_data)
    assert parsed is not None


@pytest.mark.asyncio
async def test_ordering_frequency_single_order(enricher, cache_manager, shopify_client):
    """Test frequency calculation with single order (no intervals)."""
    cache_manager.get.return_value = None
    
    now = datetime.now(tz=timezone.utc)
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    # With single order, median should be 0 or handled gracefully
    assert result.ordering_frequency_median >= 0


@pytest.mark.asyncio
async def test_order_enrichment_refund_partial_amounts(enricher, cache_manager, shopify_client):
    """Test refund amount is correctly summed when partial refunds exist on single order."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "300.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
        ]
    )
    # Partial refunds on same order
    shopify_client.refunds.list = AsyncMock(
        return_value=[
            {"id": "r1", "order_id": "1", "created_at": _make_iso_date(now), "amount": 50.0},
            {"id": "r2", "order_id": "1", "created_at": _make_iso_date(now - timedelta(days=1)), "amount": 75.0},
        ]
    )

    result = await enricher.enrich(123, 1)

    # Return rate should be refund_count (2) / order_count (1), not refund_amount / order_value
    assert result.refund_count_90d == 2
    assert result.return_rate == 2.0  # 2 refunds / 1 order


@pytest.mark.asyncio
async def test_risk_score_multiple_chargebacks_capped(enricher, cache_manager, shopify_client):
    """Test risk score caps at 1.0 when chargebacks + refunds + high-value orders present."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "600.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
            {"id": "2", "total_price": "550.00", "created_at": _make_iso_date(now - timedelta(days=5)), "financial_status": "paid"},
        ]
    )
    # Many refunds
    shopify_client.refunds.list = AsyncMock(
        return_value=[
            {"id": f"r{i}", "order_id": "1", "created_at": _make_iso_date(now - timedelta(days=i)), "amount": 50.0}
            for i in range(8)  # Many refunds
        ]
    )

    result = await enricher.enrich(123, 1)

    # Risk score should be capped at 1.0, not exceed it
    assert 0.0 <= result.risk_score <= 1.0
    assert result.risk_score == 1.0  # Should cap at maximum


@pytest.mark.asyncio
async def test_ordering_frequency_two_orders_interval(enricher, cache_manager, shopify_client):
    """Test frequency median with exactly 2 orders."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    ten_days_ago = now - timedelta(days=10)
    
    shopify_client.orders.list = AsyncMock(
        return_value=[
            {"id": "1", "total_price": "100.00", "created_at": _make_iso_date(now), "financial_status": "paid"},
            {"id": "2", "total_price": "100.00", "created_at": _make_iso_date(ten_days_ago), "financial_status": "paid"},
        ]
    )
    shopify_client.refunds.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    # With 2 orders 10 days apart, median interval is 10 days
    assert result.ordering_frequency_median == 10.0
