"""Campaign optimizer orchestrator."""

from typing import Optional, Dict, Any
import logging

from .incentive import IncentiveMatrixGenerator
from .budget import BudgetAllocator
from .send_time import SendTimeOptimizer
from .channel import ChannelSelector
from .performance import PerformanceMonitor

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
        lifecycle_stage: Optional[str] = None,
        ltv: float = 0.0,
        churn_prob: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
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

    async def execute_campaign(self, campaign: Dict[str, Any]) -> None:
        """Execute campaign."""
        logger.info(f"Executing campaign for customer {campaign['customer_id']}")
