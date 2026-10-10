"""Tests for autonomy gate and promoter (Phase 2)."""

import pytest
from datetime import datetime, timedelta

from triage.decision.autonomy import AutonomyGate, AutonomyPromoter
from triage.models.decision import AutonomyLevel


class TestAutonomyGate:
    """Test AutonomyGate enforcement."""

    @pytest.fixture
    def gate(self):
        """Create autonomy gate with sample policies."""
        return AutonomyGate(
            autonomy_policies={
                "order_status": AutonomyLevel.L1_SUGGEST,
                "refund": AutonomyLevel.L2_CONFIRM,
                "password_reset": AutonomyLevel.L0_READ_ONLY,
            }
        )

    def test_get_autonomy_level(self, gate):
        """Test retrieving autonomy level for intent."""
        assert gate.get_autonomy_level("refund") == AutonomyLevel.L2_CONFIRM
        assert gate.get_autonomy_level("order_status") == AutonomyLevel.L1_SUGGEST

    def test_get_autonomy_level_default(self, gate):
        """Test default autonomy level for unknown intent."""
        result = gate.get_autonomy_level("unknown_intent")
        assert result == AutonomyLevel.L0_READ_ONLY

    def test_can_execute_tool_allowed(self, gate):
        """Test tool execution is allowed when autonomy level sufficient."""
        allowed, reason = gate.can_execute_tool(
            intent_name="refund",
            tool_required_level=AutonomyLevel.L2_CONFIRM,
            policy_autonomy_level=AutonomyLevel.L2_CONFIRM,
        )
        assert allowed is True

    def test_can_execute_tool_blocked_insufficient_level(self, gate):
        """Test tool execution blocked when autonomy level too low."""
        allowed, reason = gate.can_execute_tool(
            intent_name="refund",
            tool_required_level=AutonomyLevel.L3_AUTO,
            policy_autonomy_level=AutonomyLevel.L2_CONFIRM,
        )
        assert allowed is False
        assert "requires" in reason.lower()

    def test_can_execute_tool_uses_minimum(self, gate):
        """Test that effective level is minimum of policy and tool requirement."""
        # Policy says L2, tool requires L1 -> effective is L1 -> allowed
        allowed, reason = gate.can_execute_tool(
            intent_name="refund",
            tool_required_level=AutonomyLevel.L1_SUGGEST,
            policy_autonomy_level=AutonomyLevel.L2_CONFIRM,
        )
        assert allowed is True


class TestAutonomyPromoter:
    """Test AutonomyPromoter promotion/demotion logic."""

    @pytest.fixture
    def promoter(self):
        """Create autonomy promoter."""
        return AutonomyPromoter()

    def test_should_promote_all_criteria_met(self, promoter):
        """Test promotion when all criteria met."""
        should_promote, reason = promoter.should_promote(
            intent_name="refund",
            accuracy=0.96,
            groundedness=0.97,
            sample_count=250,
            admin_approved=True,
        )
        assert should_promote is True
        assert "approved" in reason.lower()

    def test_should_promote_insufficient_accuracy(self, promoter):
        """Test promotion blocked on low accuracy."""
        should_promote, reason = promoter.should_promote(
            intent_name="refund",
            accuracy=0.94,
            groundedness=0.97,
            sample_count=250,
            admin_approved=True,
        )
        assert should_promote is False
        assert "accuracy" in reason.lower()

    def test_should_promote_insufficient_groundedness(self, promoter):
        """Test promotion blocked on low groundedness."""
        should_promote, reason = promoter.should_promote(
            intent_name="refund",
            accuracy=0.96,
            groundedness=0.94,
            sample_count=250,
            admin_approved=True,
        )
        assert should_promote is False
        assert "groundedness" in reason.lower()

    def test_should_promote_insufficient_samples(self, promoter):
        """Test promotion blocked on low sample count."""
        should_promote, reason = promoter.should_promote(
            intent_name="refund",
            accuracy=0.96,
            groundedness=0.97,
            sample_count=150,
            admin_approved=True,
        )
        assert should_promote is False
        assert "sample" in reason.lower()

    def test_should_promote_no_admin_approval(self, promoter):
        """Test promotion blocked without admin approval."""
        should_promote, reason = promoter.should_promote(
            intent_name="refund",
            accuracy=0.96,
            groundedness=0.97,
            sample_count=250,
            admin_approved=False,
        )
        assert should_promote is False
        assert "admin" in reason.lower()

    def test_should_promote_frequency_limit(self, promoter):
        """Test promotion blocked if promoted recently."""
        # First promotion
        promoter.should_promote(
            intent_name="refund",
            accuracy=0.96,
            groundedness=0.97,
            sample_count=250,
            admin_approved=True,
        )

        # Second promotion should be blocked (within 7 days)
        should_promote, reason = promoter.should_promote(
            intent_name="refund",
            accuracy=0.96,
            groundedness=0.97,
            sample_count=250,
            admin_approved=True,
        )
        assert should_promote is False
        assert "promotion" in reason.lower() and "days" in reason.lower()

    def test_should_demote_high_false_resolution(self, promoter):
        """Test demotion triggered by high false resolution rate."""
        should_demote, reason = promoter.should_demote(
            intent_name="refund",
            false_resolution_rate=0.08,
            groundedness=0.96,
            injection_attempts_today=0,
        )
        assert should_demote is True
        assert "false resolution" in reason.lower()

    def test_should_demote_low_groundedness(self, promoter):
        """Test demotion triggered by low groundedness."""
        should_demote, reason = promoter.should_demote(
            intent_name="refund",
            false_resolution_rate=0.02,
            groundedness=0.80,
            injection_attempts_today=0,
        )
        assert should_demote is True
        assert "groundedness" in reason.lower()

    def test_should_demote_injection_attempts(self, promoter):
        """Test demotion triggered by injection attempts."""
        should_demote, reason = promoter.should_demote(
            intent_name="refund",
            false_resolution_rate=0.02,
            groundedness=0.96,
            injection_attempts_today=15,
        )
        assert should_demote is True
        assert "injection" in reason.lower()

    def test_should_not_demote_all_metrics_ok(self, promoter):
        """Test no demotion when all metrics acceptable."""
        should_demote, reason = promoter.should_demote(
            intent_name="refund",
            false_resolution_rate=0.02,
            groundedness=0.96,
            injection_attempts_today=0,
        )
        assert should_demote is False
        assert "acceptable" in reason.lower()
