"""Campaign performance tracking."""

import logging

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Track campaign performance metrics."""

    def __init__(self):
        """Initialize monitor."""
        self.events: dict[str, list] = {}
        self.metrics_store: dict[str, dict] = {}

    async def track_campaign_event(
        self, campaign_id: str, customer_id: int, event_type: str
    ) -> None:
        """Track campaign event."""
        key = f"{campaign_id}:{event_type}"
        if key not in self.events:
            self.events[key] = []
        self.events[key].append({"customer_id": customer_id})

    async def compute_metrics(self, campaign_id: str) -> dict[str, float]:
        """Compute campaign metrics."""
        sent_key = f"{campaign_id}:sent"
        clicked_key = f"{campaign_id}:clicked"
        converted_key = f"{campaign_id}:converted"

        sent = len(self.events.get(sent_key, []))
        clicked = len(self.events.get(clicked_key, []))
        converted = len(self.events.get(converted_key, []))

        ctr = (clicked / sent) if sent > 0 else 0.0
        conversion = (converted / sent) if sent > 0 else 0.0

        return {
            "ctr": ctr,
            "conversion_rate": conversion,
            "sent_count": sent,
            "click_count": clicked,
        }

    async def check_auto_pause(self, campaign_id: str) -> bool:
        """Check if campaign should auto-pause."""
        metrics = await self.compute_metrics(campaign_id)
        ctr = metrics.get("ctr", 0)
        conversion = metrics.get("conversion_rate", 0)

        return ctr < 0.01 or conversion < 0.005

    async def pause_campaign(self, campaign_id: str) -> None:
        """Pause campaign."""
        logger.info(f"Pausing campaign {campaign_id}")
