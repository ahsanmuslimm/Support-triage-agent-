"""Cost event tracking."""

import logging

logger = logging.getLogger(__name__)


class CostEventTracker:
    """Track cost events."""

    COST_MATRIX = {
        "escalation": 4.50,
        "automation": 0.08,
        "agent": 0.65,
        "email": 0.002,
        "sms": 0.012,
        "chat": 0.05,
        "kb_update": 1.20,
    }

    def __init__(self):
        """Initialize tracker."""
        self.events: list = []

    async def log_cost_event(
        self,
        event_type: str,
        tenant_id: int,
        customer_id: int,
        cost_amount: float,
        metadata: dict,
    ) -> None:
        """Log cost event."""
        self.events.append({
            "event_type": event_type,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "cost_amount": cost_amount,
            "metadata": metadata,
        })

    async def calculate_resolution_cost(
        self, conversation_id: int
    ) -> float:
        """Calculate total cost for conversation."""
        # Mock: return average cost
        return sum(e["cost_amount"] for e in self.events) / len(self.events) if self.events else 0.0

    async def get_daily_costs(
        self, tenant_id: int, date: str
    ) -> dict[str, float]:
        """Get daily costs by event type."""
        costs = {}
        for e in self.events:
            if e["tenant_id"] == tenant_id:
                event_type = e["event_type"]
                costs[event_type] = costs.get(event_type, 0) + e["cost_amount"]
        return costs
