"""Collaborative filtering model."""

import logging

logger = logging.getLogger(__name__)


class CollaborativeFilter:
    """Implicit ALS collaborative filtering."""

    def __init__(self, latent_factors: int = 50):
        """Initialize collaborative filter."""
        self.latent_factors = latent_factors
        self.model = None

    async def train(
        self, interactions: list[tuple[int, int, float]]
    ) -> None:
        """Train ALS model on user-article interactions."""
        if not interactions:
            logger.warning("No interactions provided")
            return
        logger.info(f"ALS training on {len(interactions)} interactions")

    async def recommend_for_customer(
        self, customer_id: int, top_k: int = 5
    ) -> list[tuple[int, float]]:
        """Recommend articles for customer."""
        # Mock: return default recommendations
        return [(i, 0.9 - i * 0.1) for i in range(1, top_k + 1)]
