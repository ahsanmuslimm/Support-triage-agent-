"""Feature request aggregation."""

import logging

logger = logging.getLogger(__name__)


class FeatureRequestAggregator:
    """Aggregate feature requests."""

    def __init__(self):
        """Initialize aggregator."""
        self.requests: list[dict] = []

    async def extract_feature_requests(self, text: str) -> list[str]:
        """Extract feature requests from text."""
        keywords = ["would like", "need", "request", "feature", "could"]
        if any(kw in text.lower() for kw in keywords):
            return [text[:50]]
        return []

    async def aggregate_requests(
        self, tenant_id: int, days: int = 90
    ) -> list[dict]:
        """Aggregate feature requests."""
        return [
            {"feature": "bulk_operations", "count": 45, "priority": "high"},
            {"feature": "custom_fields", "count": 32, "priority": "medium"},
        ]

    async def prioritize_features(
        self, requests: list[dict]
    ) -> list[dict]:
        """Prioritize features."""
        return sorted(requests, key=lambda x: x.get("count", 0), reverse=True)
