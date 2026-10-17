"""Send time optimization."""

import logging

logger = logging.getLogger(__name__)


class SendTimeOptimizer:
    """Optimize send time for campaigns."""

    def __init__(self):
        """Initialize optimizer."""
        self.engagement_schedules: dict[int, dict[int, float]] = {}

    async def build_engagement_schedule(
        self,
        customer_id: int,
        tenant_id: int,
        hourly_engagement: dict[int, float] | None = None,
    ) -> dict[int, float]:
        """Build hourly engagement schedule."""
        if hourly_engagement:
            self.engagement_schedules[customer_id] = hourly_engagement
            return hourly_engagement

        # Mock: default schedule
        return {h: 0.5 + (h / 24) * 0.3 for h in range(24)}

    async def recommend_send_time(
        self, customer_id: int, tenant_id: int
    ) -> int:
        """Recommend optimal send hour (0-23)."""
        schedule = self.engagement_schedules.get(customer_id)
        if not schedule:
            schedule = {h: 0.5 + (h / 24) * 0.3 for h in range(24)}

        # Return hour with highest engagement
        best_hour = max(range(24), key=lambda h: schedule.get(h, 0.5))
        return best_hour if best_hour >= 0 else 10  # Default 10am
