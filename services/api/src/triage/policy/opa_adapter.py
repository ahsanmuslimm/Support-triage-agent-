"""OPA policy engine adapter for Sprint 7.

Evaluates write actions against Rego policies:
- refund_policy: When refunds are safe
- eligibility: Customer eligibility checks
- guardrails: Anti-fraud and compliance guardrails
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import structlog
import aiohttp

log = structlog.get_logger()


class OPADecision:
    """Decision result from OPA policy evaluation."""

    def __init__(self, approved: bool, reason: str, guardrails_triggered: List[str], approval_required: bool):
        """Initialize OPA decision."""
        self.approved = approved
        self.reason = reason
        self.guardrails_triggered = guardrails_triggered
        self.approval_required = approval_required

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "approved": self.approved,
            "reason": self.reason,
            "guardrails_triggered": self.guardrails_triggered,
            "approval_required": self.approval_required,
        }


class OPAAdapter:
    """Adapter for OPA policy engine.
    
    In production, this calls a real OPA server via HTTP.
    For testing, policies are embedded or mocked.
    """

    def __init__(self, opa_url: str = "http://localhost:8181", use_embedded: bool = False):
        """Initialize OPA adapter.
        
        Args:
            opa_url: URL to OPA server
            use_embedded: If True, use embedded policies (for testing)
        """
        self.opa_url = opa_url
        self.use_embedded = use_embedded
        self.session: Optional[aiohttp.ClientSession] = None

    async def evaluate(
        self,
        action_type: str,
        tenant_id: str,
        customer_id: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate action against policies.
        
        Args:
            action_type: Type of action (refund, cancel, etc.)
            tenant_id: Tenant ID
            customer_id: Customer ID
            arguments: Action arguments
            context: Customer and order context
            
        Returns:
            Dictionary with approval decision
        """
        log.info(
            "opa_evaluate_start",
            action_type=action_type,
            tenant_id=tenant_id,
            customer_id=customer_id,
        )

        # Build input data for OPA
        input_data = {
            "action_type": action_type,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "arguments": arguments,
            "context": context,
        }

        try:
            if self.use_embedded:
                decision = await self._evaluate_embedded(input_data)
            else:
                decision = await self._evaluate_remote(input_data, action_type)

            log.info(
                "opa_evaluate_complete",
                action_type=action_type,
                approved=decision.approved,
                guardrails_triggered=len(decision.guardrails_triggered),
            )

            return decision.to_dict()

        except Exception as e:
            log.error("opa_evaluate_error", action_type=action_type, error=str(e))
            # Default to conservative policy on error
            return {
                "approved": False,
                "reason": f"Policy evaluation error: {str(e)}",
                "guardrails_triggered": ["policy_error"],
                "approval_required": True,
            }

    async def _evaluate_remote(self, input_data: Dict[str, Any], action_type: str) -> OPADecision:
        """Evaluate using remote OPA server."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        # Select policy path based on action type
        policy_path = self._get_policy_path(action_type)

        url = f"{self.opa_url}/v1/data/{policy_path}"
        payload = {"input": input_data}

        try:
            async with self.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    decision_data = result.get("result", {})
                    return OPADecision(
                        approved=decision_data.get("approved", False),
                        reason=decision_data.get("reason", ""),
                        guardrails_triggered=decision_data.get("guardrails_triggered", []),
                        approval_required=decision_data.get("approval_required", False),
                    )
                else:
                    raise Exception(f"OPA server returned status {resp.status}")
        except aiohttp.ClientConnectorError as e:
            log.warning("opa_connection_failed", error=str(e))
            # Fall back to embedded policy
            return await self._evaluate_embedded(input_data)

    async def _evaluate_embedded(self, input_data: Dict[str, Any]) -> OPADecision:
        """Evaluate using embedded policies (for testing/offline)."""
        action_type = input_data.get("action_type")

        if action_type == "refund":
            return self._evaluate_refund_policy(input_data)
        elif action_type == "return_rma":
            return self._evaluate_return_policy(input_data)
        elif action_type == "cancel_order":
            return self._evaluate_cancel_policy(input_data)
        elif action_type == "address_change":
            return self._evaluate_address_policy(input_data)
        elif action_type == "password_reset":
            return self._evaluate_password_reset_policy(input_data)
        elif action_type == "plan_change":
            return self._evaluate_plan_change_policy(input_data)
        else:
            return OPADecision(
                approved=False,
                reason=f"Unknown action type: {action_type}",
                guardrails_triggered=["unknown_action_type"],
                approval_required=True,
            )

    def _evaluate_refund_policy(self, input_data: Dict[str, Any]) -> OPADecision:
        """Embedded refund policy."""
        arguments = input_data.get("arguments", {})
        context = input_data.get("context", {})

        amount = arguments.get("amount", 0)
        customer_tier = context.get("customer_tier", "standard")
        account_age_days = context.get("account_age_days", 0)
        previous_refunds = context.get("previous_refunds", 0)
        order_status = context.get("order_status", "unknown")
        
        guardrails = []

        # Guardrail 1: Amount limits
        if customer_tier == "standard" and amount > 50000:  # $500
            guardrails.append("amount_exceeds_standard_limit")
        elif customer_tier == "premium" and amount > 100000:  # $1000
            guardrails.append("amount_exceeds_premium_limit")

        # Guardrail 2: Account age
        if account_age_days < 7:
            guardrails.append("account_too_new")

        # Guardrail 3: Refund frequency
        if previous_refunds >= 3:
            guardrails.append("excessive_refund_history")

        # Guardrail 4: Order status
        if order_status not in ("completed", "shipped", "delivered"):
            guardrails.append("invalid_order_status")

        # Decision logic
        if guardrails:
            # Any guardrail triggers approval requirement
            return OPADecision(
                approved=False,
                reason=f"Guardrails triggered: {', '.join(guardrails)}",
                guardrails_triggered=guardrails,
                approval_required=True,
            )

        # Auto-approve low-risk refunds
        if customer_tier in ("premium", "enterprise") and amount < 10000:  # <$100
            return OPADecision(
                approved=True,
                reason="Low-risk refund: premium customer, small amount",
                guardrails_triggered=[],
                approval_required=False,
            )

        # Standard customers: approve refunds <$100 with good history
        if customer_tier == "standard" and amount < 10000 and previous_refunds == 0:
            return OPADecision(
                approved=True,
                reason="Refund approved: no history, small amount",
                guardrails_triggered=[],
                approval_required=False,
            )

        # Otherwise require approval
        return OPADecision(
            approved=False,
            reason="Refund requires human approval",
            guardrails_triggered=[],
            approval_required=True,
        )

    def _evaluate_return_policy(self, input_data: Dict[str, Any]) -> OPADecision:
        """Embedded return/RMA policy."""
        arguments = input_data.get("arguments", {})
        context = input_data.get("context", {})

        return_type = arguments.get("return_type", "full")
        order_age_days = context.get("order_age_days", 0)
        
        guardrails = []

        # Return window: 30 days standard, 60 days for premium
        if context.get("customer_tier") == "standard" and order_age_days > 30:
            guardrails.append("return_window_exceeded")
        elif context.get("customer_tier") == "premium" and order_age_days > 60:
            guardrails.append("return_window_exceeded")

        if guardrails:
            return OPADecision(
                approved=False,
                reason=f"Return not allowed: {', '.join(guardrails)}",
                guardrails_triggered=guardrails,
                approval_required=True,
            )

        return OPADecision(
            approved=True,
            reason=f"Return/RMA approved ({return_type})",
            guardrails_triggered=[],
            approval_required=False,
        )

    def _evaluate_cancel_policy(self, input_data: Dict[str, Any]) -> OPADecision:
        """Embedded cancel order policy."""
        context = input_data.get("context", {})

        order_status = context.get("order_status", "unknown")
        guardrails = []

        # Can't cancel shipped or delivered orders
        if order_status in ("shipped", "delivered", "completed"):
            guardrails.append("order_already_shipped")

        if guardrails:
            return OPADecision(
                approved=False,
                reason=f"Cannot cancel: {', '.join(guardrails)}",
                guardrails_triggered=guardrails,
                approval_required=True,
            )

        return OPADecision(
            approved=True,
            reason="Order cancellation approved",
            guardrails_triggered=[],
            approval_required=False,
        )

    def _evaluate_address_policy(self, input_data: Dict[str, Any]) -> OPADecision:
        """Embedded address change policy."""
        arguments = input_data.get("arguments", {})
        new_address = arguments.get("new_address", {})

        guardrails = []

        # Validate address fields
        required_fields = ["street", "city", "state", "zip", "country"]
        for field in required_fields:
            if not new_address.get(field):
                guardrails.append(f"missing_field_{field}")

        if guardrails:
            return OPADecision(
                approved=False,
                reason=f"Invalid address: {', '.join(guardrails)}",
                guardrails_triggered=guardrails,
                approval_required=True,
            )

        return OPADecision(
            approved=True,
            reason="Address change approved",
            guardrails_triggered=[],
            approval_required=False,
        )

    def _evaluate_password_reset_policy(self, input_data: Dict[str, Any]) -> OPADecision:
        """Embedded password reset policy."""
        # Password reset requires IAL2 (identity verification)
        context = input_data.get("context", {})
        ial = context.get("customer_ial", 0)

        if ial < 2:
            return OPADecision(
                approved=False,
                reason="Customer requires IAL2 for password reset",
                guardrails_triggered=["insufficient_identity_assurance"],
                approval_required=True,
            )

        return OPADecision(
            approved=True,
            reason="Password reset approved (IAL2 verified)",
            guardrails_triggered=[],
            approval_required=False,
        )

    def _evaluate_plan_change_policy(self, input_data: Dict[str, Any]) -> OPADecision:
        """Embedded plan change policy."""
        arguments = input_data.get("arguments", {})
        context = input_data.get("context", {})

        new_plan = arguments.get("new_plan", "")
        current_plan = context.get("current_plan", "")
        billing_status = context.get("billing_status", "active")

        guardrails = []

        # Can't change if billing is in arrears
        if billing_status != "active":
            guardrails.append("billing_not_active")

        # Validate plan exists
        valid_plans = ["starter", "pro", "enterprise"]
        if new_plan not in valid_plans:
            guardrails.append("invalid_plan")

        if guardrails:
            return OPADecision(
                approved=False,
                reason=f"Plan change blocked: {', '.join(guardrails)}",
                guardrails_triggered=guardrails,
                approval_required=True,
            )

        return OPADecision(
            approved=True,
            reason=f"Plan change approved: {current_plan} -> {new_plan}",
            guardrails_triggered=[],
            approval_required=False,
        )

    def _get_policy_path(self, action_type: str) -> str:
        """Get OPA policy data path for action type."""
        policy_map = {
            "refund": "triage/policies/refund_policy",
            "return_rma": "triage/policies/return_policy",
            "cancel_order": "triage/policies/cancel_policy",
            "address_change": "triage/policies/address_policy",
            "password_reset": "triage/policies/password_reset_policy",
            "plan_change": "triage/policies/plan_change_policy",
        }
        return policy_map.get(action_type, "triage/policies/default")

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
