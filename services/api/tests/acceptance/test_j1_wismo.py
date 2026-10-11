"""J1: WISMO auto-resolve scenario (Phase 10)."""

import pytest
import time
from triage.agent.graph import TriageAgentGraph
from triage.models.triage_state import TriageState


class TestJ1WISMOAutoResolve:
    """J1 scenario: Order status query with high confidence."""

    @pytest.fixture
    def graph(self):
        """Get triage graph."""
        try:
            return TriageAgentGraph()
        except RuntimeError:
            # LangGraph not installed; skip
            pytest.skip("LangGraph not installed")

    @pytest.mark.asyncio
    async def test_j1_order_status_high_confidence(self, graph):
        """Test J1: High-confidence WISMO query."""
        start = time.perf_counter()

        state = await graph.run(
            message_text="Where is order #654321?",
            customer_id="cust-123",
            tenant_id="tenant-001",
        )

        latency_ms = (time.perf_counter() - start) * 1000

        # Assertions
        assert state.primary_intent == "order_status"
        assert state.intent_confidence > 0.7
        assert state.autonomy_level >= 1
        assert state.response_text is not None
        assert latency_ms < 2000  # < 2 seconds

    @pytest.mark.asyncio
    async def test_j1_no_escalation(self, graph):
        """Test J1: No escalation for confident order status."""
        state = await graph.run(
            message_text="Can you track my order?",
            customer_id="cust-124",
            tenant_id="tenant-001",
        )

        assert not state.escalate or state.intent_confidence > 0.7
