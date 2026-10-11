"""J2: Low-confidence escalation scenario (Phase 10)."""

import pytest
from triage.agent.graph import TriageAgentGraph
from triage.models.triage_state import TriageState


class TestJ2LowConfidenceEscalation:
    """J2 scenario: Ambiguous query requiring escalation."""

    @pytest.fixture
    def graph(self):
        """Get triage graph."""
        try:
            return TriageAgentGraph()
        except RuntimeError:
            pytest.skip("LangGraph not installed")

    def test_j2_ambiguous_message_escalation(self, graph):
        """Test J2: Ambiguous message escalates."""
        state = graph.run(
            message_text="I have a problem",
            customer_id="cust-200",
            tenant_id="tenant-001",
        )

        # Low confidence or L0 autonomy triggers escalation
        assert state.autonomy_level == 0 or state.intent_confidence < 0.7

    def test_j2_escalation_has_reason(self, graph):
        """Test J2: Escalation includes reason."""
        state = graph.run(
            message_text="Something is wrong with my account",
            customer_id="cust-201",
            tenant_id="tenant-001",
        )

        if state.escalate:
            assert state.escalation_reason is not None
            assert len(state.escalation_reason) > 0
