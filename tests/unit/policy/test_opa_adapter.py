"""Unit tests for Sprint 7 OPA policy adapter.

Tests cover:
- All 6 policy types (refund, return, cancel, address, password, plan)
- Embedded policy evaluation
- Guardrail triggering
- Approval requirement logic
"""

import pytest
from unittest.mock import AsyncMock, patch

from services.api.src.triage.policy.opa_adapter import (
    OPAAdapter,
    OPADecision,
)


@pytest.fixture
def opa_adapter():
    """Create OPA adapter with embedded policies."""
    return OPAAdapter(use_embedded=True)


class TestOPAAdapter:
    """Test OPA adapter functionality."""

    def test_opa_initialization(self, opa_adapter):
        """Test adapter initialization."""
        assert opa_adapter.use_embedded is True
        assert opa_adapter.opa_url == "http://localhost:8181"

    @pytest.mark.asyncio
    async def test_adapter_close(self, opa_adapter):
        """Test adapter cleanup."""
        await opa_adapter.close()  # Should not raise


class TestRefundPolicy:
    """Test embedded refund policy."""

    @pytest.mark.asyncio
    async def test_refund_auto_approved_premium_small(self, opa_adapter):
        """Test auto-approval for small premium refund."""
        decision = await opa_adapter.evaluate(
            action_type="refund",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={"order_id": "ord-1", "amount": 5000},  # $50
            context={
                "customer_tier": "premium",
                "account_age_days": 30,
                "previous_refunds": 0,
                "order_status": "delivered",
            },
        )

        assert decision["approved"] is True
        assert len(decision["guardrails_triggered"]) == 0
        assert decision["approval_required"] is False

    @pytest.mark.asyncio
    async def test_refund_rejected_amount_exceeds_limit(self, opa_adapter):
        """Test rejection when amount exceeds limit."""
        decision = await opa_adapter.evaluate(
            action_type="refund",
            tenant_id="tenant-1",
            customer_id="cust-2",
            arguments={"order_id": "ord-2", "amount": 600000},  # $6000, exceeds $500 standard limit
            context={
                "customer_tier": "standard",
                "account_age_days": 60,
                "previous_refunds": 0,
                "order_status": "delivered",
            },
        )

        assert decision["approved"] is False
        assert "amount_exceeds_standard_limit" in decision["guardrails_triggered"]
        assert decision["approval_required"] is True

    @pytest.mark.asyncio
    async def test_refund_rejected_account_too_new(self, opa_adapter):
        """Test rejection for new accounts."""
        decision = await opa_adapter.evaluate(
            action_type="refund",
            tenant_id="tenant-1",
            customer_id="cust-new",
            arguments={"order_id": "ord-3", "amount": 5000},
            context={
                "customer_tier": "standard",
                "account_age_days": 2,  # Brand new account
                "previous_refunds": 0,
                "order_status": "delivered",
            },
        )

        assert decision["approved"] is False
        assert "account_too_new" in decision["guardrails_triggered"]
        assert decision["approval_required"] is True

    @pytest.mark.asyncio
    async def test_refund_rejected_excessive_history(self, opa_adapter):
        """Test rejection for excessive refund history."""
        decision = await opa_adapter.evaluate(
            action_type="refund",
            tenant_id="tenant-1",
            customer_id="cust-return",
            arguments={"order_id": "ord-4", "amount": 5000},
            context={
                "customer_tier": "standard",
                "account_age_days": 90,
                "previous_refunds": 5,  # Too many
                "order_status": "delivered",
            },
        )

        assert decision["approved"] is False
        assert "excessive_refund_history" in decision["guardrails_triggered"]
        assert decision["approval_required"] is True

    @pytest.mark.asyncio
    async def test_refund_rejected_invalid_order_status(self, opa_adapter):
        """Test rejection for invalid order status."""
        decision = await opa_adapter.evaluate(
            action_type="refund",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={"order_id": "ord-5", "amount": 5000},
            context={
                "customer_tier": "premium",
                "account_age_days": 60,
                "previous_refunds": 0,
                "order_status": "pending",  # Not eligible for refund
            },
        )

        assert decision["approved"] is False
        assert "invalid_order_status" in decision["guardrails_triggered"]


class TestReturnPolicy:
    """Test embedded return/RMA policy."""

    @pytest.mark.asyncio
    async def test_return_approved_within_window(self, opa_adapter):
        """Test return approval within return window."""
        decision = await opa_adapter.evaluate(
            action_type="return_rma",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={"order_id": "ord-6", "return_type": "full"},
            context={
                "customer_tier": "standard",
                "order_age_days": 15,  # Within 30-day window
            },
        )

        assert decision["approved"] is True
        assert decision["approval_required"] is False

    @pytest.mark.asyncio
    async def test_return_rejected_window_exceeded_standard(self, opa_adapter):
        """Test return rejection for standard customer outside window."""
        decision = await opa_adapter.evaluate(
            action_type="return_rma",
            tenant_id="tenant-1",
            customer_id="cust-2",
            arguments={"order_id": "ord-7", "return_type": "full"},
            context={
                "customer_tier": "standard",
                "order_age_days": 45,  # Exceeds 30-day window
            },
        )

        assert decision["approved"] is False
        assert "return_window_exceeded" in decision["guardrails_triggered"]

    @pytest.mark.asyncio
    async def test_return_approved_premium_extended_window(self, opa_adapter):
        """Test return approval for premium customer with extended window."""
        decision = await opa_adapter.evaluate(
            action_type="return_rma",
            tenant_id="tenant-1",
            customer_id="cust-premium",
            arguments={"order_id": "ord-8", "return_type": "partial"},
            context={
                "customer_tier": "premium",
                "order_age_days": 45,  # Within 60-day premium window
            },
        )

        assert decision["approved"] is True


class TestCancelPolicy:
    """Test embedded cancel order policy."""

    @pytest.mark.asyncio
    async def test_cancel_approved_pending_order(self, opa_adapter):
        """Test cancellation of pending order."""
        decision = await opa_adapter.evaluate(
            action_type="cancel_order",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={"order_id": "ord-9"},
            context={"order_status": "pending"},
        )

        assert decision["approved"] is True
        assert decision["approval_required"] is False

    @pytest.mark.asyncio
    async def test_cancel_rejected_shipped_order(self, opa_adapter):
        """Test cancellation rejection for shipped order."""
        decision = await opa_adapter.evaluate(
            action_type="cancel_order",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={"order_id": "ord-10"},
            context={"order_status": "shipped"},
        )

        assert decision["approved"] is False
        assert "order_already_shipped" in decision["guardrails_triggered"]

    @pytest.mark.asyncio
    async def test_cancel_rejected_delivered_order(self, opa_adapter):
        """Test cancellation rejection for delivered order."""
        decision = await opa_adapter.evaluate(
            action_type="cancel_order",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={"order_id": "ord-11"},
            context={"order_status": "delivered"},
        )

        assert decision["approved"] is False
        assert "order_already_shipped" in decision["guardrails_triggered"]


class TestAddressPolicy:
    """Test embedded address change policy."""

    @pytest.mark.asyncio
    async def test_address_approved_complete(self, opa_adapter):
        """Test approval for complete valid address."""
        decision = await opa_adapter.evaluate(
            action_type="address_change",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={
                "new_address": {
                    "street": "123 Main St",
                    "city": "Springfield",
                    "state": "IL",
                    "zip": "62701",
                    "country": "US",
                }
            },
            context={},
        )

        assert decision["approved"] is True
        assert decision["approval_required"] is False

    @pytest.mark.asyncio
    async def test_address_rejected_missing_field(self, opa_adapter):
        """Test rejection for missing address field."""
        decision = await opa_adapter.evaluate(
            action_type="address_change",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={
                "new_address": {
                    "street": "123 Main St",
                    "city": "Springfield",
                    # Missing state, zip, country
                }
            },
            context={},
        )

        assert decision["approved"] is False
        assert "missing_field" in str(decision["guardrails_triggered"])


class TestPasswordResetPolicy:
    """Test embedded password reset policy."""

    @pytest.mark.asyncio
    async def test_password_reset_approved_ial2(self, opa_adapter):
        """Test approval for IAL2 customer."""
        decision = await opa_adapter.evaluate(
            action_type="password_reset",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={"email": "user@example.com"},
            context={"customer_ial": 2},
        )

        assert decision["approved"] is True
        assert decision["approval_required"] is False

    @pytest.mark.asyncio
    async def test_password_reset_rejected_insufficient_ial(self, opa_adapter):
        """Test rejection for insufficient identity assurance."""
        decision = await opa_adapter.evaluate(
            action_type="password_reset",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={"email": "user@example.com"},
            context={"customer_ial": 0},  # No verification
        )

        assert decision["approved"] is False
        assert "insufficient_identity_assurance" in decision["guardrails_triggered"]
        assert decision["approval_required"] is True


class TestPlanChangePolicy:
    """Test embedded plan change policy."""

    @pytest.mark.asyncio
    async def test_plan_change_approved_active_billing(self, opa_adapter):
        """Test approval for plan change with active billing."""
        decision = await opa_adapter.evaluate(
            action_type="plan_change",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={
                "new_plan": "pro",
            },
            context={
                "current_plan": "starter",
                "billing_status": "active",
            },
        )

        assert decision["approved"] is True
        assert decision["approval_required"] is False

    @pytest.mark.asyncio
    async def test_plan_change_rejected_billing_in_arrears(self, opa_adapter):
        """Test rejection when billing is not active."""
        decision = await opa_adapter.evaluate(
            action_type="plan_change",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={
                "new_plan": "pro",
            },
            context={
                "current_plan": "starter",
                "billing_status": "past_due",
            },
        )

        assert decision["approved"] is False
        assert "billing_not_active" in decision["guardrails_triggered"]

    @pytest.mark.asyncio
    async def test_plan_change_rejected_invalid_plan(self, opa_adapter):
        """Test rejection for invalid plan name."""
        decision = await opa_adapter.evaluate(
            action_type="plan_change",
            tenant_id="tenant-1",
            customer_id="cust-1",
            arguments={
                "new_plan": "invalid_plan",
            },
            context={
                "current_plan": "starter",
                "billing_status": "active",
            },
        )

        assert decision["approved"] is False
        assert "invalid_plan" in decision["guardrails_triggered"]


class TestOPADecision:
    """Test OPADecision data structure."""

    def test_opa_decision_creation(self):
        """Test decision object creation."""
        decision = OPADecision(
            approved=True,
            reason="Test decision",
            guardrails_triggered=["test_guardrail"],
            approval_required=False,
        )

        assert decision.approved is True
        assert decision.reason == "Test decision"
        assert "test_guardrail" in decision.guardrails_triggered

    def test_opa_decision_to_dict(self):
        """Test conversion to dictionary."""
        decision = OPADecision(
            approved=False,
            reason="Requires approval",
            guardrails_triggered=["guardrail1", "guardrail2"],
            approval_required=True,
        )

        d = decision.to_dict()
        assert d["approved"] is False
        assert d["approval_required"] is True
        assert len(d["guardrails_triggered"]) == 2
