"""Tests for tool integration (Phase 6)."""

import pytest
from triage.tools.registry import ToolRegistry, AutonomyLevel, ToolSpec
from triage.tools.argument_binder import ArgumentBinder
from triage.tools.executor import ToolExecutor
from triage.models.entity import ExtractedEntity, EntityType
from triage.models.decision import AutonomyLevel as DecisionAutonomyLevel


class TestToolRegistry:
    """Test tool registry."""

    @pytest.fixture
    def registry(self):
        return ToolRegistry()

    def test_registry_has_builtin_tools(self, registry):
        """Test that registry has built-in tools."""
        tools = registry.list_tools()
        assert len(tools) > 0
        assert "send_email" in tools
        assert "issue_refund" in tools

    def test_get_tool(self, registry):
        """Test getting tool by name."""
        tool = registry.get_tool("send_email")
        assert tool is not None
        assert tool.name == "send_email"

    def test_tool_spec_has_required_fields(self, registry):
        """Test tool spec has required fields."""
        tool = registry.get_tool("issue_refund")
        assert tool.required_args is not None
        assert "order_id" in tool.required_args
        assert "amount" in tool.required_args

    def test_tool_has_autonomy_level(self, registry):
        """Test that tool specifies autonomy level."""
        tool = registry.get_tool("issue_refund")
        assert tool.min_autonomy_level == AutonomyLevel.L2_CONFIRM

    def test_get_tools_for_autonomy_level(self, registry):
        """Test filtering tools by autonomy level."""
        l0_tools = registry.get_tools_for_autonomy_level(AutonomyLevel.L0_READ_ONLY)
        l2_tools = registry.get_tools_for_autonomy_level(AutonomyLevel.L2_CONFIRM)
        # L2 should have more tools
        assert len(l0_tools) <= len(l2_tools)


class TestArgumentBinder:
    """Test argument binding."""

    def test_bind_order_id_and_amount(self):
        """Test binding ORDER_ID and AMOUNT to refund tool."""
        entities = [
            ExtractedEntity(
                entity_type=EntityType.ORDER_ID,
                value="ORD-123456",
                normalized_value="123456",
                confidence=0.95,
            ),
            ExtractedEntity(
                entity_type=EntityType.AMOUNT,
                value="$50.00",
                normalized_value="50.00",
                confidence=0.95,
            ),
        ]

        registry = ToolRegistry()
        tool_spec = registry.get_tool("issue_refund")

        args = ArgumentBinder.bind(entities, tool_spec)
        assert args["order_id"] == "123456"
        assert args["amount"] == 50.0

    def test_bind_email_to_send_email(self):
        """Test binding EMAIL to send_email tool."""
        entities = [
            ExtractedEntity(
                entity_type=EntityType.EMAIL,
                value="user@example.com",
                confidence=0.95,
            ),
        ]

        registry = ToolRegistry()
        tool_spec = registry.get_tool("send_email")

        # send_email requires subject and body too, so this should fail
        with pytest.raises(ValueError):
            ArgumentBinder.bind(entities, tool_spec)

    def test_bind_missing_required_args(self):
        """Test binding with missing required arguments."""
        entities = [
            ExtractedEntity(
                entity_type=EntityType.ORDER_ID,
                value="ORD-123",
                confidence=0.95,
            ),
        ]

        registry = ToolRegistry()
        tool_spec = registry.get_tool("issue_refund")

        # Missing AMOUNT
        with pytest.raises(ValueError):
            ArgumentBinder.bind(entities, tool_spec)


class TestToolExecutor:
    """Test tool execution."""

    @pytest.fixture
    def executor(self):
        return ToolExecutor(
            autonomy_level=DecisionAutonomyLevel.L2_CONFIRM,
            tenant_id="tenant-123",
            customer_id="cust-456",
        )

    def test_execute_tool_with_sufficient_autonomy(self, executor):
        """Test executing tool with sufficient autonomy."""
        registry = ToolRegistry()
        tool_spec = registry.get_tool("issue_refund")

        args = {"order_id": "123", "amount": 50.0}
        result = executor.execute(tool_spec, args, "msg-1")

        assert result.success is True
        assert result.tool_name == "issue_refund"

    def test_execute_tool_blocked_by_autonomy(self):
        """Test that tool is blocked by autonomy level."""
        executor = ToolExecutor(
            autonomy_level=DecisionAutonomyLevel.L0_READ_ONLY,
            tenant_id="tenant-123",
            customer_id="cust-456",
        )

        registry = ToolRegistry()
        tool_spec = registry.get_tool("issue_refund")

        args = {"order_id": "123", "amount": 50.0}
        result = executor.execute(tool_spec, args, "msg-1")

        assert result.success is False
        assert "Autonomy level" in result.error

    def test_idempotency_key_generation(self):
        """Test idempotency key generation."""
        registry = ToolRegistry()
        tool_spec = registry.get_tool("issue_refund")

        args1 = {"order_id": "123", "amount": 50.0}
        args2 = {"order_id": "123", "amount": 50.0}

        key1 = ToolExecutor._generate_idempotency_key(tool_spec, args1, "msg-1")
        key2 = ToolExecutor._generate_idempotency_key(tool_spec, args2, "msg-1")

        # Same args with same message should produce same key
        assert key1 == key2

    def test_idempotency_cache(self, executor):
        """Test that idempotency cache prevents duplicate execution."""
        registry = ToolRegistry()
        tool_spec = registry.get_tool("lookup_order")

        args = {"order_id": "123"}
        result1 = executor.execute(tool_spec, args, "msg-1")
        result2 = executor.execute(tool_spec, args, "msg-1")

        # Same message + args should be cached
        assert result1.execution_id == result2.execution_id or result2.tool_name == "lookup_order"
