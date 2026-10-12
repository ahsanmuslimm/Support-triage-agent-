"""KB article performance tracking."""

import logging

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Track KB article performance."""

    def __init__(self):
        """Initialize tracker."""
        self.interactions: dict[int, list] = {}

    async def log_article_interaction(
        self, article_id: int, action: str, duration_sec: int
    ) -> None:
        """Log article interaction."""
        if article_id not in self.interactions:
            self.interactions[article_id] = []
        self.interactions[article_id].append({
            "action": action,
            "duration": duration_sec,
        })

    async def compute_article_metrics(
        self, article_id: int, days: int = 30
    ) -> dict[str, float]:
        """Compute article metrics."""
        interactions = self.interactions.get(article_id, [])
        views = len(interactions)
        clicks = sum(1 for i in interactions if i["action"] == "clicked")
        resolved = sum(1 for i in interactions if i["action"] == "resolved")
        avg_dwell = sum(i["duration"] for i in interactions) / views if views > 0 else 0

        return {
            "views": views,
            "clicks": clicks,
            "resolutions": resolved,
            "ctr": clicks / views if views > 0 else 0,
            "resolution_rate": resolved / views if views > 0 else 0,
            "avg_dwell_sec": avg_dwell,
        }

    async def identify_underperforming_articles(
        self, threshold_ctr: float = 0.10
    ) -> list[int]:
        """Identify underperforming articles."""
        underperformers = []
        for article_id in self.interactions:
            metrics = await self.compute_article_metrics(article_id)
            if metrics["ctr"] < threshold_ctr:
                underperformers.append(article_id)
        return underperformers
