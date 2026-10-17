"""Incentive matrix generator."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class OfferTier(str, Enum):
    """Campaign offer tiers."""

    PERSONAL_CALL = "personal_call"
    DISCOUNT_20PCT = "discount_20pct"
    DISCOUNT_10PCT = "discount_10pct"
    FREE_SHIPPING = "free_shipping"


class IncentiveMatrixGenerator:
    """Generate offers based on LTV quartile and churn risk."""

    def __init__(self):
        """Initialize matrix."""
        self.matrix = self._build_matrix()

    def _build_matrix(self) -> dict[tuple[str, str], OfferTier]:
        """Build incentive matrix."""
        return {
            ("Q4", "LOW"): OfferTier.FREE_SHIPPING,
            ("Q4", "MEDIUM"): OfferTier.DISCOUNT_10PCT,
            ("Q4", "HIGH"): OfferTier.DISCOUNT_20PCT,
            ("Q3", "LOW"): OfferTier.FREE_SHIPPING,
            ("Q3", "MEDIUM"): OfferTier.DISCOUNT_10PCT,
            ("Q3", "HIGH"): OfferTier.DISCOUNT_20PCT,
            ("Q2", "LOW"): OfferTier.DISCOUNT_10PCT,
            ("Q2", "MEDIUM"): OfferTier.DISCOUNT_20PCT,
            ("Q2", "HIGH"): OfferTier.PERSONAL_CALL,
            ("Q1", "LOW"): OfferTier.DISCOUNT_10PCT,
            ("Q1", "MEDIUM"): OfferTier.DISCOUNT_20PCT,
            ("Q1", "HIGH"): OfferTier.PERSONAL_CALL,
        }

    async def select_offer(
        self, ltv: float = 0.0, churn_prob: float = 0.0
    ) -> OfferTier:
        """Select offer for customer."""
        # Map LTV to quartile
        ltv_quartile = "Q1"  # Mock: would compute from distribution
        if ltv > 75:
            ltv_quartile = "Q4"
        elif ltv > 50:
            ltv_quartile = "Q3"
        elif ltv > 25:
            ltv_quartile = "Q2"

        # Map churn_prob to risk level
        risk_level = "LOW"
        if churn_prob > 0.5:
            risk_level = "HIGH"
        elif churn_prob > 0.3:
            risk_level = "MEDIUM"

        return self.matrix.get((ltv_quartile, risk_level), OfferTier.FREE_SHIPPING)
