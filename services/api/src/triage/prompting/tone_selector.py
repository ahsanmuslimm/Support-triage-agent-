"""S3.7: Tone Selection Logic."""

import logging

logger = logging.getLogger(__name__)


class ToneSelector:
    """Deterministic tone selection based on customer context."""

    @staticmethod
    def select_tone(
        health_score: float,
        is_vip: bool,
        order_count: int,
        total_spent: float,
        account_type: str = "standard",
    ) -> str:
        """
        Select tone deterministically.

        Priority:
        1. High churn risk (health_score < 0.35) → 'empathy'
        2. High-value customer (order_count > 20 OR total_spent > 5000) → 'urgency'
        3. Enterprise account → 'formal'
        4. Otherwise → 'neutral'
        """
        # Churn risk (high priority)
        if health_score < 0.35:
            return "empathy"

        # High-value customer
        if order_count > 20 or total_spent > 5000:
            return "urgency"

        # Enterprise or VIP
        if account_type == "enterprise" or is_vip:
            return "formal"

        # Default
        return "neutral"
