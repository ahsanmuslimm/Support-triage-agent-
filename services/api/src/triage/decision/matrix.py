"""Decision matrix: 10+ rules mapping policy input to autonomy level."""

import structlog
import re
from typing import Tuple
from services.api.src.triage.models.decision import (
    PolicyInput,
    DecisionResult,
    AutonomyLevel,
    SafetyFlag,
)

log = structlog.get_logger()


class DecisionMatrix:
    """Pure logic decision matrix for autonomy level determination.

    All rules are deterministic functions of PolicyInput.
    No I/O, no randomness. Rules are applied in order; first match wins.
    """

    # Injection patterns (OWASP LLM Top 10)
    INJECTION_PATTERNS = [
        r"(?i)(ignore.*prompt|forget.*instruction|you are now|system prompt|developer mode)",
        r"(?i)(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|;--)",
        r"(?i)(\.\.\/|\.\.\\|/etc/|c:\\windows|cmd\.exe|bash -i)",
        r"(?i)(script.*>|iframe|javascript:|onerror=|onload=)",
    ]

    @staticmethod
    def _check_safety_flags(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 1: Safety triggers → immediate L0."""
        if policy.safety_flags:
            flags_str = ", ".join(policy.safety_flags)
            return True, f"Safety flag(s): {flags_str}"
        return False, ""

    @staticmethod
    def _check_injection_heuristics(policy: PolicyInput) -> Tuple[bool, str]:
        """Check for injection attack patterns in message."""
        for pattern in DecisionMatrix.INJECTION_PATTERNS:
            if re.search(pattern, policy.message_text):
                return True, f"Injection pattern detected: {pattern[:30]}..."
        return False, ""

    @staticmethod
    def _check_confidence_too_low(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 2: Low confidence → escalate, L0."""
        if policy.intent_confidence is not None and policy.intent_confidence < 0.5:
            return True, f"Confidence too low: {policy.intent_confidence:.2f} < 0.5"
        return False, ""

    @staticmethod
    def _check_repeat_customer_no_resolution(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 3: Repeat customer with failed attempts → escalate."""
        if policy.is_repeat_customer and policy.previous_resolution_attempts >= 2:
            return True, f"Repeat customer with {policy.previous_resolution_attempts} failed attempts"
        return False, ""

    @staticmethod
    def _check_ial_mismatch(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 4: IAL too low for sensitive intents → escalate."""
        sensitive_intents = {"password_reset", "account_delete", "billing_change", "refund"}
        if (
            policy.intent_name in sensitive_intents
            and policy.customer_ial < 2
        ):
            return True, f"IAL {policy.customer_ial} < 2 for sensitive intent {policy.intent_name}"
        return False, ""

    @staticmethod
    def _check_high_value_transaction(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 5: Refunds > $500 require confirmation (L2 max)."""
        if (
            policy.intent_name == "refund"
            and policy.extracted_amount
            and policy.extracted_amount > 500.0
        ):
            return True, f"High-value refund: ${policy.extracted_amount:.2f} > $500"
        return False, ""

    @staticmethod
    def _check_low_confidence_high_value(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 6: Low confidence + high value → escalate."""
        if (
            policy.intent_confidence
            and policy.intent_confidence < 0.7
            and policy.extracted_amount
            and policy.extracted_amount > 100.0
        ):
            return True, f"Low confidence ({policy.intent_confidence:.2f}) + high value (${policy.extracted_amount})"
        return False, ""

    @staticmethod
    def _check_standard_order_status(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 7: Standard WISMO (order status) with high confidence → L1."""
        if (
            policy.intent_name == "order_status"
            and policy.intent_confidence
            and policy.intent_confidence >= 0.7
        ):
            return True, f"Order status with {policy.intent_confidence:.2f} confidence"
        return False, ""

    @staticmethod
    def _check_premium_low_risk(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 8: Premium customer, low-risk intent, high confidence → L2."""
        low_risk_intents = {
            "order_status",
            "shipping_info",
            "product_info",
            "account_view",
            "create_ticket",
        }
        if (
            policy.customer_tier == "premium"
            and policy.intent_name in low_risk_intents
            and policy.intent_confidence
            and policy.intent_confidence >= 0.75
        ):
            return True, f"Premium customer, {policy.intent_name}, confidence {policy.intent_confidence:.2f}"
        return False, ""

    @staticmethod
    def _check_low_risk_refund(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 9: Refund < $100, high confidence, verified customer → L2."""
        if (
            policy.intent_name == "refund"
            and policy.intent_confidence
            and policy.intent_confidence >= 0.75
            and policy.extracted_amount
            and policy.extracted_amount < 100.0
            and policy.customer_ial >= 1
        ):
            return True, f"Low-risk refund: ${policy.extracted_amount} < $100, confidence {policy.intent_confidence:.2f}"
        return False, ""

    @staticmethod
    def _check_enterprise_auto(policy: PolicyInput) -> Tuple[bool, str]:
        """Rule 10: Enterprise customer, very high confidence, low risk → L3."""
        low_risk_intents = {
            "order_status",
            "shipping_info",
            "create_ticket",
        }
        if (
            policy.customer_tier == "enterprise"
            and policy.intent_name in low_risk_intents
            and policy.intent_confidence
            and policy.intent_confidence >= 0.9
        ):
            return True, f"Enterprise customer, {policy.intent_name}, very high confidence {policy.intent_confidence:.2f}"
        return False, ""

    @staticmethod
    def decide(policy: PolicyInput) -> DecisionResult:
        """Apply decision matrix rules in order.

        First match wins. Returns autonomy level and reasoning.

        Args:
            policy: Policy input with context.

        Returns:
            DecisionResult with autonomy level.
        """
        log.info("decision_matrix_evaluate", intent=policy.intent_name, confidence=policy.intent_confidence)

        # Rule 1: Safety flags → L0 (escalate)
        triggered, reason = DecisionMatrix._check_safety_flags(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L0_READ_ONLY,
                reason=reason,
                rule_triggered="rule_1_safety_flags",
                recommended_action="escalate",
            )

        # Check for injection patterns (add to safety flags)
        triggered, reason = DecisionMatrix._check_injection_heuristics(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L0_READ_ONLY,
                reason=reason,
                rule_triggered="rule_0_injection_detected",
                recommended_action="escalate",
                fallback_required=True,
            )

        # Rule 2: Confidence < 0.5 → L0
        triggered, reason = DecisionMatrix._check_confidence_too_low(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L0_READ_ONLY,
                reason=reason,
                rule_triggered="rule_2_low_confidence",
                recommended_action="escalate",
            )

        # Rule 3: Repeat customer with failed attempts → L0
        triggered, reason = DecisionMatrix._check_repeat_customer_no_resolution(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L0_READ_ONLY,
                reason=reason,
                rule_triggered="rule_3_repeat_escalation",
                recommended_action="escalate",
            )

        # Rule 4: IAL mismatch → L0
        triggered, reason = DecisionMatrix._check_ial_mismatch(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L0_READ_ONLY,
                reason=reason,
                rule_triggered="rule_4_ial_mismatch",
                recommended_action="escalate",
            )

        # Rule 5: High-value refund → L2 max (needs confirmation)
        triggered, reason = DecisionMatrix._check_high_value_transaction(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L2_CONFIRM,
                reason=reason,
                rule_triggered="rule_5_high_value_refund",
                recommended_action="propose_tools",
            )

        # Rule 6: Low confidence + high value → L0
        triggered, reason = DecisionMatrix._check_low_confidence_high_value(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L0_READ_ONLY,
                reason=reason,
                rule_triggered="rule_6_low_conf_high_value",
                recommended_action="escalate",
            )

        # Rule 7: Standard order status → L1
        triggered, reason = DecisionMatrix._check_standard_order_status(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L1_SUGGEST,
                reason=reason,
                rule_triggered="rule_7_order_status",
                recommended_action="compose_draft",
            )

        # Rule 8: Premium, low-risk, high confidence → L2
        triggered, reason = DecisionMatrix._check_premium_low_risk(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L2_CONFIRM,
                reason=reason,
                rule_triggered="rule_8_premium_low_risk",
                recommended_action="propose_tools",
            )

        # Rule 9: Low-risk refund → L2
        triggered, reason = DecisionMatrix._check_low_risk_refund(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L2_CONFIRM,
                reason=reason,
                rule_triggered="rule_9_low_risk_refund",
                recommended_action="propose_tools",
            )

        # Rule 10: Enterprise auto → L3
        triggered, reason = DecisionMatrix._check_enterprise_auto(policy)
        if triggered:
            return DecisionResult(
                autonomy_level=AutonomyLevel.L3_AUTO,
                reason=reason,
                rule_triggered="rule_10_enterprise_auto",
                recommended_action="execute_tools",
            )

        # Default: escalate
        return DecisionResult(
            autonomy_level=AutonomyLevel.L0_READ_ONLY,
            reason="No rule matched; defaulting to escalation",
            rule_triggered="default_escalate",
            recommended_action="escalate",
        )
