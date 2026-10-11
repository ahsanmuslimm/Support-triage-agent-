"""Unit tests for Sprint 7 write tools.

Tests cover:
- All 6 write tools
- Idempotency
- Error handling
- Tool-specific business logic
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from services.api.src.triage.tools.write_tools import (
    RefundTool,
    ReturnRMATool,
    CancelOrderTool,
    AddressChangeTool,
    PasswordResetTool,
    PlanChangeTool,
    WriteToolResult,
)


@pytest.fixture
def idempotency_store():
    """Mock idempotency store."""
    store = AsyncMock()
    store.get = AsyncMock(return_value=None)
    store.set = AsyncMock(return_value=True)
    return store


class TestRefundTool:
    """Test refund write tool."""

    @pytest.fixture
    def refund_tool(self, idempotency_store):
        """Create refund tool."""
        stripe_client = AsyncMock()
        shopify_client = AsyncMock()
        return RefundTool(stripe_client, shopify_client, idempotency_store)

    @pytest.mark.asyncio
    async def test_refund_stripe_execution(self, refund_tool, idempotency_store):
        """Test Stripe refund execution."""
        refund_tool.stripe_client.refunds.create = AsyncMock(
            return_value=MagicMock(
                id="ref_123",
                status="succeeded",
                created=1234567890,
            )
        )

        result = await refund_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-123",
            amount=10000,
            processor="stripe",
            payment_intent_id="pi_123",
        )

        assert result.success is True
        assert result.result_data["refund_id"] == "ref_123"
        assert result.result_data["processor"] == "stripe"
        idempotency_store.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_refund_shopify_execution(self, refund_tool, idempotency_store):
        """Test Shopify refund execution."""
        refund_tool.shopify_client.refund.create = AsyncMock(
            return_value=MagicMock(
                id="ref_456",
                status="success",
                created_at=datetime.utcnow().isoformat(),
            )
        )

        result = await refund_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-456",
            amount=25000,
            processor="shopify",
            transaction_id="txn_789",
        )

        assert result.success is True
        assert result.result_data["processor"] == "shopify"

    @pytest.mark.asyncio
    async def test_refund_idempotency(self, refund_tool, idempotency_store):
        """Test refund idempotency on duplicate calls."""
        cached_result = {"refund_id": "ref_cached", "amount": 10000}
        idempotency_store.get.return_value = cached_result

        result = await refund_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-789",
            amount=10000,
            processor="stripe",
        )

        assert result.success is True
        assert result.result_data == cached_result
        # Should return cached result without calling Stripe
        refund_tool.stripe_client.refunds.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_refund_error_handling(self, refund_tool, idempotency_store):
        """Test refund error handling."""
        refund_tool.stripe_client.refunds.create = AsyncMock(
            side_effect=Exception("Stripe API error")
        )

        result = await refund_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-999",
            amount=50000,
            processor="stripe",
            payment_intent_id="pi_999",
        )

        assert result.success is False
        assert "Stripe API error" in result.error

    @pytest.mark.asyncio
    async def test_refund_idempotency_key_generation(self, refund_tool):
        """Test idempotency key generation."""
        key1 = refund_tool._generate_idempotency_key(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-100",
            amount=10000,
        )

        key2 = refund_tool._generate_idempotency_key(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-100",
            amount=10000,
        )

        # Same inputs should generate same key
        assert key1 == key2

        # Different amount should generate different key
        key3 = refund_tool._generate_idempotency_key(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-100",
            amount=20000,
        )
        assert key1 != key3


class TestReturnRMATool:
    """Test return/RMA write tool."""

    @pytest.fixture
    def return_tool(self, idempotency_store):
        """Create return/RMA tool."""
        logistics_client = AsyncMock()
        return ReturnRMATool(logistics_client, idempotency_store)

    @pytest.mark.asyncio
    async def test_return_rma_creation(self, return_tool, idempotency_store):
        """Test RMA creation."""
        result = await return_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-200",
            return_type="full",
            reason="customer_requested",
        )

        assert result.success is True
        assert "rma_number" in result.result_data
        assert result.result_data["return_type"] == "full"
        assert "shipping_label" in result.result_data

    @pytest.mark.asyncio
    async def test_return_partial_rma(self, return_tool):
        """Test partial RMA creation."""
        result = await return_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-201",
            return_type="partial",
            reason="defective_item",
        )

        assert result.success is True
        assert result.result_data["return_type"] == "partial"

    @pytest.mark.asyncio
    async def test_return_idempotency(self, return_tool, idempotency_store):
        """Test return idempotency."""
        cached = {"rma_number": "RMA-CACHED", "status": "created"}
        idempotency_store.get.return_value = cached

        result = await return_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-202",
            return_type="full",
        )

        assert result.result_data == cached


class TestCancelOrderTool:
    """Test cancel order write tool."""

    @pytest.fixture
    def cancel_tool(self, idempotency_store):
        """Create cancel tool."""
        order_service = AsyncMock()
        order_service.cancel_order = AsyncMock(
            return_value={"order_id": "ord-x", "status": "cancelled"}
        )
        return CancelOrderTool(order_service, idempotency_store)

    @pytest.mark.asyncio
    async def test_cancel_order_execution(self, cancel_tool):
        """Test order cancellation."""
        result = await cancel_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-300",
            reason="customer_requested",
        )

        assert result.success is True
        assert result.result_data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_order_idempotency(self, cancel_tool, idempotency_store):
        """Test cancel order idempotency."""
        cached = {"order_id": "ord-x", "status": "cancelled"}
        idempotency_store.get.return_value = cached

        result = await cancel_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            order_id="ord-301",
        )

        assert result.result_data == cached


class TestAddressChangeTool:
    """Test address change write tool."""

    @pytest.fixture
    def address_tool(self, idempotency_store):
        """Create address change tool."""
        customer_service = AsyncMock()
        customer_service.update_address = AsyncMock(
            return_value={"customer_id": "cust-x", "status": "updated"}
        )
        return AddressChangeTool(customer_service, idempotency_store)

    @pytest.mark.asyncio
    async def test_address_change_execution(self, address_tool):
        """Test address change."""
        new_address = {
            "street": "123 Main St",
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "country": "US",
        }

        result = await address_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            new_address=new_address,
        )

        assert result.success is True
        assert result.result_data["status"] == "updated"

    @pytest.mark.asyncio
    async def test_address_change_idempotency(self, address_tool, idempotency_store):
        """Test address change idempotency."""
        new_address = {
            "street": "456 Oak Ave",
            "city": "Chicago",
            "state": "IL",
            "zip": "60601",
            "country": "US",
        }

        cached = {"customer_id": "cust-x", "status": "updated"}
        idempotency_store.get.return_value = cached

        result = await address_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            new_address=new_address,
        )

        assert result.result_data == cached


class TestPasswordResetTool:
    """Test password reset write tool."""

    @pytest.fixture
    def password_tool(self, idempotency_store):
        """Create password reset tool."""
        auth_service = AsyncMock()
        auth_service.generate_reset_token = AsyncMock(return_value="reset_token_abc123xyz")
        email_service = AsyncMock()
        email_service.send_password_reset_email = AsyncMock(return_value=True)
        return PasswordResetTool(auth_service, email_service, idempotency_store)

    @pytest.mark.asyncio
    async def test_password_reset_execution(self, password_tool):
        """Test password reset."""
        result = await password_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            email="user@example.com",
        )

        assert result.success is True
        assert result.result_data["status"] == "sent"
        assert "token_id" in result.result_data

    @pytest.mark.asyncio
    async def test_password_reset_idempotency_hourly(self, password_tool, idempotency_store):
        """Test password reset idempotency (hourly window)."""
        cached = {"token_id": "***", "status": "sent"}
        idempotency_store.get.return_value = cached

        result = await password_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            email="user@example.com",
        )

        assert result.result_data == cached

    @pytest.mark.asyncio
    async def test_password_reset_token_obfuscation(self, password_tool):
        """Test that tokens are obfuscated in results."""
        result = await password_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            email="user@example.com",
        )

        # Token should be obfuscated (ending with ***)
        assert "***" in result.result_data["token_id"]
        # Should not contain full token
        assert "reset_token" not in result.result_data["token_id"]


class TestPlanChangeTool:
    """Test plan change write tool."""

    @pytest.fixture
    def plan_tool(self, idempotency_store):
        """Create plan change tool."""
        billing_service = AsyncMock()
        billing_service.change_plan = AsyncMock(
            return_value={"customer_id": "cust-x", "new_plan": "pro"}
        )
        return PlanChangeTool(billing_service, idempotency_store)

    @pytest.mark.asyncio
    async def test_plan_change_immediate(self, plan_tool):
        """Test immediate plan change."""
        result = await plan_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            new_plan="pro",
        )

        assert result.success is True
        assert result.result_data["new_plan"] == "pro"

    @pytest.mark.asyncio
    async def test_plan_change_scheduled(self, plan_tool):
        """Test scheduled plan change."""
        effective_date = "2025-01-01T00:00:00Z"

        result = await plan_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            new_plan="enterprise",
            effective_date=effective_date,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_plan_change_idempotency(self, plan_tool, idempotency_store):
        """Test plan change idempotency."""
        cached = {"customer_id": "cust-x", "new_plan": "starter"}
        idempotency_store.get.return_value = cached

        result = await plan_tool.execute(
            tenant_id="tenant-1",
            customer_id="cust-1",
            new_plan="starter",
        )

        assert result.result_data == cached


class TestWriteToolResult:
    """Test WriteToolResult data structure."""

    def test_result_structure(self):
        """Test result structure."""
        result = WriteToolResult(
            tool_name="refund",
            success=True,
            execution_id="exec-123",
            idempotency_key="idem-456",
            result_data={"refund_id": "ref-789"},
            executed_at=datetime.utcnow(),
        )

        assert result.tool_name == "refund"
        assert result.success is True
        assert result.result_data["refund_id"] == "ref-789"

    def test_result_error(self):
        """Test result with error."""
        result = WriteToolResult(
            tool_name="refund",
            success=False,
            execution_id="exec-124",
            idempotency_key="idem-457",
            result_data={},
            error="Service unavailable",
        )

        assert result.success is False
        assert "Service unavailable" in result.error
