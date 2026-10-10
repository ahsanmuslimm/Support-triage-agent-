"""Autonomy policy enforcement and promotion workflow."""

import structlog
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta

from triage.models.decision import AutonomyLevel, PolicyInput

log = structlog.get_logger()


class AutonomyGate:
    """Enforces autonomy levels at tool execution time."""

    def __init__(self, autonomy_policies: Optional[Dict[str, int]] = None):
        """Initialize autonomy gate.

        Args:
            autonomy_policies: Dict mapping intent_name -> autonomy_level (0-3).
                              If None, defaults to L0 (read-only).
        """
        self.autonomy_policies = autonomy_policies or {}
        log.info("autonomy_gate_initialized", policies_count=len(self.autonomy_policies))

    def get_autonomy_level(self, intent_name: str) -> AutonomyLevel:
        """Get configured autonomy level for an intent.

        Args:
            intent_name: Intent to check.

        Returns:
            AutonomyLevel from policy, or L0 (default).
        """
        level = self.autonomy_policies.get(intent_name, AutonomyLevel.L0_READ_ONLY)
        return AutonomyLevel(level)

    def can_execute_tool(
        self,
        intent_name: str,
        tool_required_level: AutonomyLevel,
        policy_autonomy_level: AutonomyLevel,
    ) -> Tuple[bool, str]:
        """Check if tool execution is allowed.

        Args:
            intent_name: Intent being executed.
            tool_required_level: Minimum autonomy level required by tool.
            policy_autonomy_level: Autonomy level from decision matrix.

        Returns:
            (allowed: bool, reason: str).
        """
        # Use minimum of policy and tool requirement
        effective_level = min(policy_autonomy_level, AutonomyLevel(self.get_autonomy_level(intent_name)))

        allowed = effective_level >= tool_required_level

        reason = (
            f"Tool requires L{tool_required_level}, effective level L{effective_level}"
            if not allowed
            else f"Tool execution allowed at L{effective_level}"
        )

        log.info(
            "autonomy_gate_check",
            intent=intent_name,
            tool_required=tool_required_level,
            effective=effective_level,
            allowed=allowed,
        )

        return allowed, reason


class AutonomyPromoter:
    """Manages autonomy level promotion and demotion."""

    PROMOTION_CRITERIA = {
        "accuracy_threshold": 0.95,  # ≥ 95% accuracy required
        "groundedness_threshold": 0.95,  # ≥ 95% groundedness required
        "sample_count_threshold": 200,  # ≥ 200 samples required
        "max_promotion_frequency_days": 7,  # Max 1 promotion per 7 days
    }

    DEMOTION_TRIGGERS = {
        "false_resolution_threshold": 0.05,  # > 5% false resolution rate
        "groundedness_drop_threshold": 0.85,  # < 85% groundedness
        "injection_attempts_per_day": 10,  # > 10 injection attempts/day
    }

    def __init__(self):
        """Initialize autonomy promoter."""
        self.last_promotion: Dict[str, datetime] = {}

    def should_promote(
        self,
        intent_name: str,
        accuracy: float,
        groundedness: float,
        sample_count: int,
        admin_approved: bool = False,
    ) -> Tuple[bool, str]:
        """Check if intent should be promoted to higher autonomy.

        Args:
            intent_name: Intent to evaluate.
            accuracy: Top-1 accuracy [0, 1].
            groundedness: Response groundedness [0, 1].
            sample_count: Number of samples evaluated.
            admin_approved: Admin approval given.

        Returns:
            (should_promote: bool, reason: str).
        """
        # Check accuracy
        if accuracy < self.PROMOTION_CRITERIA["accuracy_threshold"]:
            return False, f"Accuracy {accuracy:.2%} < {self.PROMOTION_CRITERIA['accuracy_threshold']:.2%}"

        # Check groundedness
        if groundedness < self.PROMOTION_CRITERIA["groundedness_threshold"]:
            return False, f"Groundedness {groundedness:.2%} < {self.PROMOTION_CRITERIA['groundedness_threshold']:.2%}"

        # Check sample count
        if sample_count < self.PROMOTION_CRITERIA["sample_count_threshold"]:
            return False, f"Sample count {sample_count} < {self.PROMOTION_CRITERIA['sample_count_threshold']}"

        # Check promotion frequency
        if intent_name in self.last_promotion:
            days_since = (datetime.utcnow() - self.last_promotion[intent_name]).days
            if days_since < self.PROMOTION_CRITERIA["max_promotion_frequency_days"]:
                return (
                    False,
                    f"Last promotion {days_since} days ago; {self.PROMOTION_CRITERIA['max_promotion_frequency_days']} days required",
                )

        # Check admin approval
        if not admin_approved:
            return False, "Admin approval required"

        self.last_promotion[intent_name] = datetime.utcnow()
        log.info(
            "autonomy_promotion_approved",
            intent=intent_name,
            accuracy=accuracy,
            groundedness=groundedness,
            sample_count=sample_count,
        )

        return True, "All criteria met; promotion approved"

    def should_demote(
        self,
        intent_name: str,
        false_resolution_rate: float,
        groundedness: float,
        injection_attempts_today: int,
    ) -> Tuple[bool, str]:
        """Check if intent should be demoted to lower autonomy.

        Args:
            intent_name: Intent to evaluate.
            false_resolution_rate: Fraction of false resolutions.
            groundedness: Response groundedness [0, 1].
            injection_attempts_today: Number of injection attacks detected today.

        Returns:
            (should_demote: bool, reason: str).
        """
        reasons = []

        if false_resolution_rate > self.DEMOTION_TRIGGERS["false_resolution_threshold"]:
            reasons.append(
                f"False resolution rate {false_resolution_rate:.2%} > {self.DEMOTION_TRIGGERS['false_resolution_threshold']:.2%}"
            )

        if groundedness < self.DEMOTION_TRIGGERS["groundedness_drop_threshold"]:
            reasons.append(
                f"Groundedness {groundedness:.2%} < {self.DEMOTION_TRIGGERS['groundedness_drop_threshold']:.2%}"
            )

        if injection_attempts_today > self.DEMOTION_TRIGGERS["injection_attempts_per_day"]:
            reasons.append(
                f"Injection attempts {injection_attempts_today} > {self.DEMOTION_TRIGGERS['injection_attempts_per_day']}"
            )

        if reasons:
            reason = "; ".join(reasons)
            log.warning("autonomy_demotion_triggered", intent=intent_name, reasons=reason)
            return True, reason

        return False, "All metrics within acceptable range"
