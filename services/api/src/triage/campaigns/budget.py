"""Budget allocator for campaigns."""

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class BudgetAllocator:
    """Allocate budget to segments based on LTV."""

    def __init__(self):
        """Initialize allocator."""
        self.budget_store: Dict[str, float] = {}

    async def allocate_budget(
        self,
        total_budget: float,
        segments: List[Dict[str, float]],
    ) -> Dict[str, float]:
        """Allocate budget to segments proportional to LTV."""
        if not segments:
            return {}

        total_ltv = sum(s.get("ltv", 0) for s in segments)
        if total_ltv <= 0:
            # Equal distribution
            per_segment = total_budget / len(segments)
            return {i: per_segment for i in range(len(segments))}

        allocation = {}
        for i, segment in enumerate(segments):
            ltv = segment.get("ltv", 0)
            allocated = (ltv / total_ltv) * total_budget
            allocation[str(i)] = allocated
            self.budget_store[str(i)] = allocated

        return allocation

    async def track_spend(self, segment_id: str, amount: float) -> None:
        """Track spending for segment."""
        if segment_id in self.budget_store:
            self.budget_store[segment_id] -= amount

    async def check_budget_available(
        self, segment_id: str, amount: float
    ) -> bool:
        """Check if budget available for spend."""
        return self.budget_store.get(segment_id, 0) >= amount
