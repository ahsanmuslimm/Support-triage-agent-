"""Routing engine for agent assignment."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
import structlog

log = structlog.get_logger()


class RoutingDecision(str, Enum):
    """Routing decision outcomes."""

    AUTONOMOUS_AGENT = "autonomous_agent"
    BILLING_SPECIALIST = "billing_specialist"
    TECHNICAL_SPECIALIST = "technical_specialist"
    GENERAL_AGENT = "general_agent"


@dataclass
class RoutingResult:
    """Result of routing decision."""

    route: RoutingDecision
    agent_id: Optional[str] = None
    reason: Optional[str] = None
    priority: int = 5


class RoutingEngine:
    """Route conversations to appropriate agents or autonomous handling."""

    def route(self, intent_name: str, autonomy_level: int) -> RoutingResult:
        """Route based on intent and autonomy level.

        Args:
            intent_name: Classified intent
            autonomy_level: Autonomy level (0-3)

        Returns:
            RoutingResult
        """
        # Route based on intent
        if intent_name == "order_status" and autonomy_level >= 1:
            return RoutingResult(
                route=RoutingDecision.AUTONOMOUS_AGENT,
                reason="Order status with sufficient autonomy",
                priority=2,
            )

        if intent_name in ("billing", "payment", "invoice"):
            return RoutingResult(
                route=RoutingDecision.BILLING_SPECIALIST,
                reason=f"Intent requires billing specialist: {intent_name}",
                priority=3,
            )

        if intent_name in ("technical", "error", "bug"):
            return RoutingResult(
                route=RoutingDecision.TECHNICAL_SPECIALIST,
                reason=f"Intent requires technical specialist: {intent_name}",
                priority=3,
            )

        # Default to general agent
        return RoutingResult(
            route=RoutingDecision.GENERAL_AGENT,
            reason=f"Intent {intent_name} routed to general queue",
            priority=5,
        )
