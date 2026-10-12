"""Outcome tracker orchestrator."""

import logging

from .attribution import AttributionModel
from .cohort import CohortAnalyzer
from .retention import RetentionAnalyzer
from .revenue_lift import RevenueLiftCalculator

logger = logging.getLogger(__name__)


class OutcomeTracker:
    """Orchestrate outcome tracking."""

    def __init__(self):
        """Initialize tracker."""
        self.attribution = AttributionModel()
        self.retention = RetentionAnalyzer()
        self.revenue_lift = RevenueLiftCalculator()
        self.cohort = CohortAnalyzer()

    async def track_outcome(
        self, customer_id: int, event_type: str
    ) -> None:
        """Track outcome event."""
        logger.info(f"Tracked outcome for customer {customer_id}: {event_type}")
