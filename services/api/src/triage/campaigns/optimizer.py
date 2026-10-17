"""Campaign optimizer orchestrator."""

import logging
from typing import Any

from .budget import BudgetAllocator
from .channel import ChannelSelector
from .incentive import IncentiveMatrixGenerator
from .performance import PerformanceMonitor
from .send_time import SendTimeOptimizer

logger = logging.getLogger(__name__)


class CampaignOptimizer:
    """Orchestrate campaign optimization."""

    def __init__(self):
        """Initialize optimizer."""
        self.incentive = IncentiveMatrixGenerator()
        self.budget = BudgetAllocator()
        self.send_time = SendTimeOptimizer()
        self.channel = ChannelSelector()
        self.performance = PerformanceMonitor()

    async def generate_campaign(
        self,
        customer_id: int,
        tenant_id: int,
        lifecycle_stage: str | None = None,
        ltv: float = 0.0,
        churn_prob: float = 0.0,
    ) -> dict[str, Any] | None:
        """Generate campaign for customer."""
        # Select incentive
        offer = await self.incentive.select_offer(ltv=ltv, churn_prob=churn_prob)

        # Select send time
        send_hour = await self.send_time.recommend_send_time(customer_id, tenant_id)

        # Select channel
        channel = await self.channel.select_channel(customer_id)

        if not channel:
            return None

        return {
            "customer_id": customer_id,
            "offer": offer,
            "send_hour": send_hour,
            "channel": channel,
            "lifecycle_stage": lifecycle_stage,
        }

    async def execute_campaign(self, campaign: dict[str, Any]) -> None:
        """Execute campaign."""
        logger.info(f"Executing campaign for customer {campaign['customer_id']}")
