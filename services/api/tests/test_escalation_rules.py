"""Tests for escalation rules engine (S4.3)."""

from datetime import datetime, timedelta

import pytest
from triage.escalation.models import Priority, TriageState
from triage.escalation.rules_engine import EscalationRulesEngine


class TestEscalationRulesEngine:
    """Test EscalationRulesEngine."""

    @pytest.fixture
    def engine(self):
        """Create rules engine."""
        return EscalationRulesEngine()

    @pytest.fixture
    def base_state(self):
        """Base triage state for testing."""
        return TriageState(
            tenant_id=1,
            ticket_id="TICKET-001",
            customer_id=100,
            intent="order_status",
            intent_confidence=0.85,
            entities={"order_id": "ORD-123"},
            safety_flags=[],
            enrichment_context={},
            escalation_count=0,
        )

    @pytest.mark.asyncio
    async def test_engine_initialization(self, engine):
        """Test engine initializes correctly."""
        assert engine.confidence_threshold == 0.50
        assert hasattr(engine, 'anomaly_priority_map')

    @pytest.mark.asyncio
    async def test_confidence_rule_low_confidence(self, engine, base_state):
        """Test confidence rule with low confidence."""
        base_state.intent_confidence = 0.35

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P1
        assert job.ticket_id == "TICKET-001"

    @pytest.mark.asyncio
    async def test_confidence_rule_high_confidence(self, engine, base_state):
        """Test confidence rule with high confidence."""
        base_state.intent_confidence = 0.85
        base_state.entity_extraction_error = None
        base_state.safety_flags = []
        base_state.escalation_count = 0

        job = await engine.evaluate(base_state)
        assert job is None  # No escalation

    @pytest.mark.asyncio
    async def test_safety_flag_chargeback(self, engine, base_state):
        """Test safety flag escalation for chargeback."""
        base_state.safety_flags = ["chargeback"]

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P0

    @pytest.mark.asyncio
    async def test_safety_flag_legal_threat(self, engine, base_state):
        """Test safety flag escalation for legal threat."""
        base_state.safety_flags = ["legal_threat"]

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P0

    @pytest.mark.asyncio
    async def test_safety_flag_fraud_suspected(self, engine, base_state):
        """Test safety flag escalation for fraud."""
        base_state.safety_flags = ["fraud_suspected"]

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P0

    @pytest.mark.asyncio
    async def test_entity_extraction_failure_empty(self, engine, base_state):
        """Test entity extraction failure with empty entities."""
        base_state.entities = {}

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P1

    @pytest.mark.asyncio
    async def test_entity_extraction_failure_error(self, engine, base_state):
        """Test entity extraction failure with error."""
        base_state.entity_extraction_error = "Parse error"

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P1

    @pytest.mark.asyncio
    async def test_repeat_escalation_rule_2x(self, engine, base_state):
        """Test repeat escalation rule at 2 escalations."""
        base_state.escalation_count = 2

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P0

    @pytest.mark.asyncio
    async def test_repeat_escalation_rule_3x(self, engine, base_state):
        """Test repeat escalation rule at 3 escalations."""
        base_state.escalation_count = 3

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P0

    @pytest.mark.asyncio
    async def test_anomaly_signal_churn_spike(self, engine, base_state):
        """Test anomaly signal detection for churn spike."""
        base_state.enrichment_context = {
            "anomaly_signal": {"type": "churn_spike"}
        }

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P1

    @pytest.mark.asyncio
    async def test_anomaly_signal_fraud_pattern(self, engine, base_state):
        """Test anomaly signal detection for fraud pattern."""
        base_state.enrichment_context = {
            "anomaly_signal": {"type": "fraud_pattern"}
        }

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.priority == Priority.P0

    @pytest.mark.asyncio
    async def test_escalation_job_sla_p0(self, engine, base_state):
        """Test SLA deadline calculation for P0."""
        base_state.safety_flags = ["fraud_suspected"]

        job = await engine.evaluate(base_state)
        assert job is not None

        # P0 should have 15 min SLA (allow 20 second tolerance)
        expected_deadline = datetime.utcnow() + timedelta(minutes=15)
        time_diff = abs((job.deadline - expected_deadline).total_seconds())
        assert time_diff < 20  # Within 20 seconds

    @pytest.mark.asyncio
    async def test_escalation_job_sla_p1(self, engine, base_state):
        """Test SLA deadline calculation for P1."""
        base_state.intent_confidence = 0.4

        job = await engine.evaluate(base_state)
        assert job is not None

        # P1 should have 1 hour SLA
        expected_deadline = datetime.utcnow() + timedelta(minutes=60)
        time_diff = abs((job.deadline - expected_deadline).total_seconds())
        assert time_diff < 10

    @pytest.mark.asyncio
    async def test_no_escalation_healthy_state(self, engine, base_state):
        """Test no escalation for healthy state."""
        # All checks pass
        base_state.intent_confidence = 0.9
        base_state.entities = {"order_id": "123"}
        base_state.entity_extraction_error = None
        base_state.safety_flags = []
        base_state.escalation_count = 0
        base_state.enrichment_context = {}

        job = await engine.evaluate(base_state)
        assert job is None

    @pytest.mark.asyncio
    async def test_escalation_job_status_pending(self, engine, base_state):
        """Test escalation job starts in pending status."""
        base_state.intent_confidence = 0.3

        job = await engine.evaluate(base_state)
        assert job is not None
        assert job.status == "pending"

    @pytest.mark.asyncio
    async def test_escalation_job_created_at_recent(self, engine, base_state):
        """Test escalation job creation timestamp is recent."""
        base_state.intent_confidence = 0.3
        now = datetime.utcnow()

        job = await engine.evaluate(base_state)
        assert job is not None
        assert (job.created_at - now).total_seconds() < 5
