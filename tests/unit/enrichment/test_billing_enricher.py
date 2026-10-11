"""Unit tests for S3.3 Billing Enricher."""

import pytest
from datetime import datetime, timedelta, date, timezone
from unittest.mock import AsyncMock, MagicMock

from services.api.src.triage.enrichment.billing_enricher import BillingEnricher
from services.api.src.triage.enrichment.base import CacheManager


@pytest.fixture
def cache_manager():
    manager = MagicMock(spec=CacheManager)
    manager.get = AsyncMock(return_value=None)
    manager.set = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def stripe_client():
    client = MagicMock()
    client.payment_methods = MagicMock()
    client.invoices = MagicMock()
    client.subscriptions = MagicMock()
    return client


@pytest.fixture
def enricher(cache_manager, stripe_client):
    return BillingEnricher(
        cache_manager=cache_manager,
        stripe_client=stripe_client,
        db_session=None,
    )


@pytest.mark.asyncio
async def test_billing_enrichment_basic(enricher, cache_manager, stripe_client):
    """Test basic billing enrichment."""
    cache_manager.get.return_value = None

    stripe_client.payment_methods.list = AsyncMock(
        return_value=[
            {
                "id": "pm_1234",
                "type": "card",
                "card": {
                    "exp_month": 12,
                    "exp_year": 2025,
                },
            }
        ]
    )
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {
                "id": "inv_1",
                "status": "paid",
                "amount_paid": 9900,
                "created": int(datetime.now(tz=timezone.utc).timestamp()),
            }
        ]
    )
    stripe_client.subscriptions.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.payment_method_count == 1
    assert result.primary_payment_type == "card"
    assert result.successful_payments_90d == 1


@pytest.mark.asyncio
async def test_card_expiry_flag(enricher, cache_manager, stripe_client):
    """Test card expiry flag (<30 days)."""
    cache_manager.get.return_value = None

    # Card expiring in 15 days
    future_date = datetime.now(tz=timezone.utc).date() + timedelta(days=15)
    stripe_client.payment_methods.list = AsyncMock(
        return_value=[
            {
                "id": "pm_1234",
                "type": "card",
                "card": {
                    "exp_month": future_date.month,
                    "exp_year": future_date.year,
                },
            }
        ]
    )
    stripe_client.invoices.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.card_expiring_soon is True
    assert 10 <= result.card_expiry_days <= 20  # Allow variance


@pytest.mark.asyncio
async def test_failed_payment_tracking(enricher, cache_manager, stripe_client):
    """Test failed payment tracking."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": "inv_1", "status": "paid", "amount_paid": 100, "created": int(now.timestamp())},
            {"id": "inv_2", "status": "failed", "amount_paid": 0, "created": int((now - timedelta(days=5)).timestamp())},
            {"id": "inv_3", "status": "failed", "amount_paid": 0, "created": int((now - timedelta(days=10)).timestamp())},
        ]
    )
    stripe_client.subscriptions.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.failed_payments_90d == 2
    assert result.successful_payments_90d == 1
    assert result.payment_success_rate == pytest.approx(1/3, 0.01)


@pytest.mark.asyncio
async def test_churn_risk_from_failed_payments(enricher, cache_manager, stripe_client):
    """Test churn risk detection from 3+ failed payments."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": f"inv_{i}", "status": "failed", "amount_paid": 0, "created": int((now - timedelta(days=i*5)).timestamp())}
            for i in range(3)
        ]
    )
    stripe_client.subscriptions.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.is_churn_risk is True


@pytest.mark.asyncio
async def test_payment_success_rate_calculation(enricher, cache_manager, stripe_client):
    """Test payment success rate calculation."""
    cache_manager.get.return_value = None

    now = datetime.now(tz=timezone.utc)
    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    # 7 paid, 3 failed
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": f"inv_{i}", "status": "paid", "amount_paid": 100, "created": int((now - timedelta(days=i)).timestamp())}
            for i in range(7)
        ]
        + [
            {"id": f"inv_f{i}", "status": "failed", "amount_paid": 0, "created": int((now - timedelta(days=7+i)).timestamp())}
            for i in range(3)
        ]
    )
    stripe_client.subscriptions.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.payment_success_rate == pytest.approx(0.7, 0.01)


@pytest.mark.asyncio
async def test_cache_hit_on_billing_enrichment(enricher, cache_manager):
    """Test cached billing context is returned."""
    import json
    cached_context = {
        "customer_id": 123,
        "tenant_id": 1,
        "payment_method_count": 2,
        "primary_payment_type": "card",
        "card_expiring_soon": False,
        "card_expiry_days": 100,
        "failed_payments_90d": 0,
        "successful_payments_90d": 12,
        "payment_success_rate": 1.0,
        "is_churn_risk": False,
        "dunning_notice_count": 0,
    }
    cache_manager.get = AsyncMock(return_value=json.dumps(cached_context))
    
    result = await enricher.enrich(123, 1)
    
    assert result.payment_method_count == 2
    assert result.payment_success_rate == 1.0


@pytest.mark.asyncio
async def test_no_payment_methods(enricher, cache_manager, stripe_client):
    """Test handling when customer has no payment methods."""
    cache_manager.get.return_value = None
    
    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    stripe_client.invoices.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.payment_method_count == 0
    assert result.primary_payment_type is None or result.primary_payment_type == ""


@pytest.mark.asyncio
async def test_multiple_payment_methods(enricher, cache_manager, stripe_client):
    """Test handling multiple payment methods."""
    cache_manager.get.return_value = None
    
    stripe_client.payment_methods.list = AsyncMock(
        return_value=[
            {"id": "pm_1", "type": "card", "card": {"exp_month": 12, "exp_year": 2025}},
            {"id": "pm_2", "type": "card", "card": {"exp_month": 6, "exp_year": 2025}},
            {"id": "pm_3", "type": "bank_account", "bank_account": {}},
        ]
    )
    stripe_client.invoices.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.payment_method_count == 3


@pytest.mark.asyncio
async def test_invoices_outside_90_day_window(enricher, cache_manager, stripe_client):
    """Test that invoices older than 90 days are excluded."""
    cache_manager.get.return_value = None
    
    now = datetime.now(tz=timezone.utc)
    sixty_days_ago = now - timedelta(days=60)
    one_hundred_days_ago = now - timedelta(days=100)
    
    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": "inv_1", "status": "paid", "amount_paid": 100, "created": int(sixty_days_ago.timestamp())},
            {"id": "inv_2", "status": "paid", "amount_paid": 100, "created": int(one_hundred_days_ago.timestamp())},  # Too old
        ]
    )
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.successful_payments_90d == 1


@pytest.mark.asyncio
async def test_consecutive_failed_payments_dunning_signal(enricher, cache_manager, stripe_client):
    """Test detection of consecutive failed payments (dunning scenario)."""
    cache_manager.get.return_value = None
    
    now = datetime.now(tz=timezone.utc)
    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    
    # Alternating paid and failed to simulate dunning
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": "inv_1", "status": "failed", "amount_paid": 0, "created": int(now.timestamp())},
            {"id": "inv_2", "status": "failed", "amount_paid": 0, "created": int((now - timedelta(days=1)).timestamp())},
            {"id": "inv_3", "status": "failed", "amount_paid": 0, "created": int((now - timedelta(days=2)).timestamp())},
        ]
    )
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.failed_payments_90d >= 3
    assert result.is_churn_risk is True


@pytest.mark.asyncio
async def test_cache_serialization(enricher, cache_manager, stripe_client):
    """Test that results are properly cached."""
    cache_manager.get.return_value = None
    cache_manager.set = AsyncMock(return_value=True)
    
    stripe_client.payment_methods.list = AsyncMock(
        return_value=[
            {"id": "pm_1", "type": "card", "card": {"exp_month": 12, "exp_year": 2025}},
        ]
    )
    stripe_client.invoices.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
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
async def test_zero_successful_payments_all_failed(enricher, cache_manager, stripe_client):
    """Test when all invoices failed (success rate = 0)."""
    cache_manager.get.return_value = None
    
    now = datetime.now(tz=timezone.utc)
    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": f"inv_{i}", "status": "failed", "amount_paid": 0, "created": int((now - timedelta(days=i)).timestamp())}
            for i in range(5)
        ]
    )
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.payment_success_rate == 0.0
    assert result.is_churn_risk is True


@pytest.mark.asyncio
async def test_card_expiry_calculation_future(enricher, cache_manager, stripe_client):
    """Test card expiry days calculation for future expiry."""
    cache_manager.get.return_value = None
    
    # Card expiring in 60 days
    future_date = datetime.now(tz=timezone.utc).date() + timedelta(days=60)
    stripe_client.payment_methods.list = AsyncMock(
        return_value=[
            {
                "id": "pm_1",
                "type": "card",
                "card": {
                    "exp_month": future_date.month,
                    "exp_year": future_date.year,
                },
            }
        ]
    )
    stripe_client.invoices.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.card_expiring_soon is False
    assert result.card_expiry_days > 30


@pytest.mark.asyncio
async def test_card_already_expired(enricher, cache_manager, stripe_client):
    """Test detection of already-expired card."""
    cache_manager.get.return_value = None
    
    # Card expired last month
    past_date = datetime.now(tz=timezone.utc).date() - timedelta(days=10)
    stripe_client.payment_methods.list = AsyncMock(
        return_value=[
            {
                "id": "pm_1",
                "type": "card",
                "card": {
                    "exp_month": past_date.month,
                    "exp_year": past_date.year,
                },
            }
        ]
    )
    stripe_client.invoices.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.card_expiry_days < 0


@pytest.mark.asyncio
async def test_payment_method_type_extraction_non_card(enricher, cache_manager, stripe_client):
    """Test extraction of non-card payment types (bank_account, etc)."""
    cache_manager.get.return_value = None
    
    stripe_client.payment_methods.list = AsyncMock(
        return_value=[
            {"id": "pm_1", "type": "bank_account", "bank_account": {}},
        ]
    )
    stripe_client.invoices.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    assert result.payment_method_count == 1
    assert result.primary_payment_type == "bank_account"


@pytest.mark.asyncio
async def test_card_expiry_boundary_exactly_30_days(enricher, cache_manager, stripe_client):
    """Test card expiring at exactly 30-day boundary."""
    cache_manager.get.return_value = None
    
    # Card expiring in exactly 30 days
    future_date = datetime.now(tz=timezone.utc).date() + timedelta(days=30)
    stripe_client.payment_methods.list = AsyncMock(
        return_value=[
            {
                "id": "pm_1",
                "type": "card",
                "card": {
                    "exp_month": future_date.month,
                    "exp_year": future_date.year,
                },
            }
        ]
    )
    stripe_client.invoices.list = AsyncMock(return_value=[])
    stripe_client.subscriptions.list = AsyncMock(return_value=[])
    
    result = await enricher.enrich(123, 1)
    
    # At exactly 30 days, should trigger the flag (<=30)
    assert result.card_expiring_soon is True
    assert abs(result.card_expiry_days - 30) <= 1  # Allow 1 day variance
