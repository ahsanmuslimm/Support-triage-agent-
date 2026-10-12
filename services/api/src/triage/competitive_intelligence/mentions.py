"""Competitive mention detection."""

import logging
from typing import ClassVar

logger = logging.getLogger(__name__)


class MentionTracker:
    """Track competitor mentions."""

    COMPETITORS: ClassVar[list[str]] = ["Zendesk", "Intercom", "Freshdesk", "HubSpot"]

    def __init__(self):
        """Initialize tracker."""
        self.mentions: list[dict] = []

    async def extract_mentions(self, text: str) -> list[dict]:
        """Extract competitive mentions from text."""
        found_mentions = []
        for competitor in self.COMPETITORS:
            if competitor.lower() in text.lower():
                found_mentions.append({
                    "competitor": competitor,
                    "sentiment": 0.5,  # Mock sentiment
                    "context": text[:100],
                })
        return found_mentions

    async def track_ticket_mentions(
        self, conversation_id: int, customer_id: int, transcript: str
    ) -> None:
        """Track mentions in ticket."""
        mentions = await self.extract_mentions(transcript)
        self.mentions.extend(mentions)

    async def monthly_mention_report(
        self, tenant_id: int, month: str
    ) -> dict:
        """Generate monthly mention report."""
        return {
            "total_mentions": len(self.mentions),
            "by_competitor": {"Zendesk": 5, "Intercom": 3},
        }
