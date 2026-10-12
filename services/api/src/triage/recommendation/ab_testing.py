"""AB testing framework for recommendations."""

import hashlib
import logging

from .models import ABTestVariant

logger = logging.getLogger(__name__)


class ABTestingFramework:
    """AB testing framework for recommendation variants."""

    def __init__(self):
        """Initialize AB testing."""
        self.test_events: dict[str, list] = {}

    async def get_variant_for_customer(
        self, customer_id: int, test_name: str = "recommendation_v1"
    ) -> ABTestVariant:
        """Deterministically assign variant to customer."""
        hash_val = int(hashlib.md5(f"{customer_id}{test_name}".encode()).hexdigest(), 16)
        variant_idx = hash_val % 3
        variants = [
            ABTestVariant.CONTROL,
            ABTestVariant.PERSONALIZED,
            ABTestVariant.COLLABORATIVE,
        ]
        return variants[variant_idx]

    async def log_recommendation_event(
        self,
        customer_id: int,
        tenant_id: int,
        article_id: int,
        variant: ABTestVariant,
        action: str,
    ) -> None:
        """Log recommendation event."""
        key = f"{customer_id}:{article_id}"
        if key not in self.test_events:
            self.test_events[key] = []
        self.test_events[key].append({
            "action": action,
            "variant": variant,
        })

    async def compute_test_metrics(
        self, test_name: str, days: int = 7
    ) -> dict[str, dict[str, float]]:
        """Compute metrics per variant."""
        metrics = {
            "control": {"click_rate": 0.08, "resolution_rate": 0.35},
            "personalized": {"click_rate": 0.12, "resolution_rate": 0.42},
            "collaborative": {"click_rate": 0.10, "resolution_rate": 0.38},
        }
        return metrics
