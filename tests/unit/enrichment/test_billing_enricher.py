"""Unit tests for S3.3 Billing Enricher."""

import pytest
from datetime import datetime, timedelta, date
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
                "created": int(datetime.utcnow().timestamp()),
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
    future_date = datetime.utcnow().date() + timedelta(days=15)
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

    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": "inv_1", "status": "paid", "amount_paid": 100, "created": int(datetime.utcnow().timestamp())},
            {"id": "inv_2", "status": "failed", "amount_paid": 0, "created": int((datetime.utcnow() - timedelta(days=5)).timestamp())},
            {"id": "inv_3", "status": "failed", "amount_paid": 0, "created": int((datetime.utcnow() - timedelta(days=10)).timestamp())},
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

    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": f"inv_{i}", "status": "failed", "amount_paid": 0, "created": int((datetime.utcnow() - timedelta(days=i*5)).timestamp())}
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

    stripe_client.payment_methods.list = AsyncMock(return_value=[])
    # 7 paid, 3 failed
    stripe_client.invoices.list = AsyncMock(
        return_value=[
            {"id": f"inv_{i}", "status": "paid", "amount_paid": 100, "created": int((datetime.utcnow() - timedelta(days=i)).timestamp())}
            for i in range(7)
        ]
        + [
            {"id": f"inv_f{i}", "status": "failed", "amount_paid": 0, "created": int((datetime.utcnow() - timedelta(days=7+i)).timestamp())}
            for i in range(3)
        ]
    )
    stripe_client.subscriptions.list = AsyncMock(return_value=[])

    result = await enricher.enrich(123, 1)

    assert result.payment_success_rate == pytest.approx(0.7, 0.01)
