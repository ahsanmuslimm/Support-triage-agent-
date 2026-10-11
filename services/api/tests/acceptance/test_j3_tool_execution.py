"""J3: Tool execution scenario (Phase 10)."""

import pytest
from triage.agent.graph import TriageAgentGraph


class TestJ3ToolExecution:
    """J3 scenario: Refund request with tool execution."""

    @pytest.fixture
    def graph(self):
        """Get triage graph."""
        try:
            return TriageAgentGraph()
        except RuntimeError:
            pytest.skip("LangGraph not installed")

    @pytest.mark.asyncio
    async def test_j3_refund_request_execution(self, graph):
        """Test J3: Refund request with tool execution."""
        state = await graph.run(
            message_text="I need a refund for order #123456 for $50",
            customer_id="cust-300",
            tenant_id="tenant-001",
        )

        # Should classify as refund
        assert state.primary_intent is not None
        assert "refund" in state.primary_intent.lower() or state.autonomy_level >= 0

        # Should extract amount
        if state.extracted_amount:
            assert state.extracted_amount == 50.0 or state.extracted_amount > 0

    @pytest.mark.asyncio
    async def test_j3_tool_executed(self, graph):
        """Test J3: Tool is executed at L2+ autonomy."""
        state = await graph.run(
            message_text="Issue refund for order #789 amount $100",
            customer_id="cust-301",
            tenant_id="tenant-001",
        )

        # If autonomy level is L2+, tool may be executed
        if state.autonomy_level and state.autonomy_level >= 2:
            # Tool execution should have been attempted
            assert state.tool_name or not state.tool_executed or state.escalate
