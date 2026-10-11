"""ROI calculation."""

from typing import Dict
import logging

logger = logging.getLogger(__name__)


class ROICalculator:
    """Calculate ROI for initiatives."""

    def __init__(self):
        """Initialize calculator."""
        self.initiative_costs: Dict[str, float] = {}

    async def calculate_roi(
        self, initiative_id: str, cost_incurred: float, value_delivered: float
    ) -> float:
        """Calculate ROI percentage."""
        if cost_incurred <= 0:
            return 0.0
        return ((value_delivered - cost_incurred) / cost_incurred) * 100

    async def track_initiative_costs(
        self, initiative_id: str, cost_type: str, amount: float
    ) -> None:
        """Track costs for initiative."""
        if initiative_id not in self.initiative_costs:
            self.initiative_costs[initiative_id] = 0
        self.initiative_costs[initiative_id] += amount

    async def estimate_value_delivered(
        self, initiative_id: str, metric: str
    ) -> float:
        """Estimate value delivered by initiative."""
        # Mock estimation
        return 1000.0
