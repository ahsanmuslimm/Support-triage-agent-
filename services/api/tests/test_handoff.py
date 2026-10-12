"""Tests for conversation handoff (S4.8)."""

from datetime import datetime, timedelta

import pytest
from triage.escalation.handoff import HandoffComposer
from triage.escalation.models import EscalationJob, Priority, TriageState


class TestHandoffComposer:
    """Test HandoffComposer."""

    @pytest.fixture
    def composer(self):
        """Create handoff composer."""
        return HandoffComposer()

    @pytest.fixture
    def base_state(self):
        """Base triage state."""
        return TriageState(
            tenant_id=1,
            ticket_id="TICKET-001",
            customer_id=100,
            intent="order_status",
            intent_confidence=0.35,
            entities={"order_id": "ORD-123"},
            safety_flags=[],
            enrichment_context={},
        )

    @pytest.fixture
    def sample_job(self):
        """Sample escalation job."""
        return EscalationJob(
            id=1,
            tenant_id=1,
            ticket_id="TICKET-001",
            priority=Priority.P1,
            deadline=datetime.utcnow() + timedelta(hours=1),
            status="pending",
            created_at=datetime.utcnow(),
        )

    @pytest.fixture
    def enrichment_context(self):
        """Sample enrichment context."""
        return {
            "health_score": 0.45,
            "churn_risk": 0.75,
            "customer": {
                "name": "John Doe",
                "email": "john@example.com",
                "is_vip": False,
                "account_age_days": 365,
                "order_count": 10,
                "total_spent": 500.0,
            },
            "last_3_attempts": [
                {"intent": "refund", "confidence": 0.8},
                {"intent": "order_status", "confidence": 0.3},
                {"intent": "billing", "confidence": 0.5},
            ],
        }

    @pytest.mark.asyncio
    async def test_composer_initialization(self, composer):
        """Test composer initializes correctly."""
        assert composer.quality_threshold == 0.90
        assert composer.db_session is None

    @pytest.mark.asyncio
    async def test_compose_handoff_success(
        self, composer, base_state, sample_job, enrichment_context
    ):
        """Test successful handoff composition."""
        handoff = await composer.compose_handoff(
            escalation_id=1,
            state=base_state,
            enrichment_context=enrichment_context,
            escalation_job=sample_job,
        )

        assert handoff is not None
        assert handoff.escalation_id == 1
        assert len(handoff.summary_text) > 0
        assert handoff.customer_context is not None
        assert 0.0 <= handoff.quality_score <= 1.0

    @pytest.mark.asyncio
    async def test_summary_extraction(self, composer, base_state, enrichment_context):
        """Test summary text extraction."""
        summary = composer._extract_summary(
            base_state, enrichment_context, EscalationJob(
                id=1, tenant_id=1, ticket_id="TICKET-001", priority=Priority.P1,
                deadline=datetime.utcnow(), status="pending", created_at=datetime.utcnow()
            )
        )

        assert len(summary) > 0
        assert len(summary) >= 50  # At least 50 chars
        assert "order_status" in summary or "Issue" in summary

    @pytest.mark.asyncio
    async def test_customer_context_extraction(
        self, composer, base_state, enrichment_context
    ):
        """Test customer context extraction."""
        context = composer._extract_customer_context(
            enrichment_context, base_state
        )

        assert "health_score" in context
        assert "churn_risk" in context
        assert "is_vip" in context
        assert "account_age_days" in context
        assert "customer_name" in context
        assert "order_count" in context

    @pytest.mark.asyncio
    async def test_quality_score_perfect(self, composer):
        """Test quality score computation for perfect handoff."""
        handoff_data = {
            "summary": "This is a comprehensive summary with all details. Customer needs support.",
            "customer_context": {
                "health_score": 0.5,
                "churn_risk": 0.7,
                "is_vip": True,
                "customer_name": "John Doe",
                "last_3_attempts": [{"intent": "help"}],
            },
        }

        score = composer._compute_quality_score(handoff_data)
        assert score >= 0.7  # High quality

    @pytest.mark.asyncio
    async def test_quality_score_poor(self, composer):
        """Test quality score computation for poor handoff."""
        handoff_data = {
            "summary": "Bad",
            "customer_context": {},
        }

        score = composer._compute_quality_score(handoff_data)
        assert score < 0.5  # Low quality

    @pytest.mark.asyncio
    async def test_quality_score_bounds(self, composer):
        """Test quality score is between 0 and 1."""
        for _ in range(10):
            handoff_data = {
                "summary": "Summary",
                "customer_context": {"health_score": 0.5},
            }
            score = composer._compute_quality_score(handoff_data)
            assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_handoff_includes_vip_status(
        self, composer, base_state, sample_job
    ):
        """Test handoff includes VIP status."""
        enrichment = {
            "customer": {"is_vip": True},
            "health_score": 0.7,
        }

        handoff = await composer.compose_handoff(
            1, base_state, enrichment, sample_job
        )

        assert handoff is not None
        assert handoff.customer_context["is_vip"] is True

    @pytest.mark.asyncio
    async def test_handoff_includes_churn_risk(
        self, composer, base_state, sample_job
    ):
        """Test handoff includes churn risk."""
        enrichment = {
            "churn_risk": 0.85,
            "customer": {},
            "health_score": 0.3,
        }

        handoff = await composer.compose_handoff(
            1, base_state, enrichment, sample_job
        )

        assert handoff is not None
        assert handoff.customer_context["churn_risk"] == 0.85

    @pytest.mark.asyncio
    async def test_handoff_empty_enrichment(self, composer, base_state, sample_job):
        """Test handoff composition with empty enrichment."""
        handoff = await composer.compose_handoff(
            1, base_state, {}, sample_job
        )

        assert handoff is not None
        # Should still produce valid handoff with defaults
