"""RFM (Recency, Frequency, Monetary) scoring."""

from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

import numpy as np

from .models import RFMDimensions, CustomerRFMScore

logger = logging.getLogger(__name__)


class RFMCalculator:
    """Computes RFM scores using quantile-based binning (0-5 scale)."""

    def __init__(self):
        """Initialize RFM calculator."""
        self.recency_bin_days = [365, 180, 90, 30, 0]  # thresholds for 5->0
        self.frequency_bins = [100, 50, 20, 10, 0]  # order counts
        self.monetary_bins = [5000, 1000, 500, 100, 0]  # dollar amounts

    def _score_dimension(self, value: float, bins: list) -> int:
        """Bin value into 0-5 scale using thresholds."""
        # Simple linear scoring: map value to 0-5
        if len(bins) < 2:
            return 0
        min_val = bins[-1]
        max_val = bins[0]
        if max_val == min_val:
            return 2  # default middle value
        # Normalize value to 0-1, then map to 0-5
        normalized = (value - min_val) / (max_val - min_val)
        normalized = max(0.0, min(1.0, normalized))  # Clamp to [0, 1]
        score = int(round(normalized * 5))
        return max(0, min(5, score))

    async def calculate_rfm(
        self,
        tenant_id: int,
        customer_id: int,
        days_since_last_order: Optional[int] = None,
        days_since_last_ticket: Optional[int] = None,
        order_count_365d: int = 0,
        ticket_count_365d: int = 0,
        total_spend_365d: float = 0.0,
    ) -> RFMDimensions:
        """
        Calculate RFM dimensions for a customer.

        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            days_since_last_order: Days since last purchase (max 365)
            days_since_last_ticket: Days since last support ticket
            order_count_365d: Count of orders in last 365 days
            ticket_count_365d: Count of support tickets in last 365 days
            total_spend_365d: Total spend in last 365 days (USD)

        Returns:
            RFMDimensions with scores 0-5 per dimension
        """
        # Recency: prefer recent, cap at 365 days
        recency_days = min(
            365,
            min(
                [
                    d
                    for d in [days_since_last_order, days_since_last_ticket]
                    if d is not None
                ],
                default=365,
            ),
        )
        # Convert days since to recency score: 0 days = 5, 365 days = 0
        recency_score = 5 - int((recency_days / 365) * 5)
        recency_score = max(0, min(5, recency_score))

        # Frequency: count of orders + tickets combined
        frequency = order_count_365d + ticket_count_365d
        frequency_score = self._score_dimension(frequency, self.frequency_bins)

        # Monetary: total spend
        monetary_score = self._score_dimension(total_spend_365d, self.monetary_bins)

        return RFMDimensions(
            recency_score=recency_score,
            frequency_score=frequency_score,
            monetary_score=monetary_score,
        )

    async def batch_calculate_rfm(
        self,
        tenant_id: int,
        customers_data: Dict[int, Dict],
    ) -> Dict[int, RFMDimensions]:
        """
        Calculate RFM for multiple customers.

        Args:
            tenant_id: Tenant ID
            customers_data: Dict mapping customer_id -> {days_since_last_order, order_count, ...}

        Returns:
            Dict mapping customer_id -> RFMDimensions
        """
        results = {}
        for customer_id, data in customers_data.items():
            try:
                rfm = await self.calculate_rfm(tenant_id, customer_id, **data)
                results[customer_id] = rfm
            except Exception as e:
                logger.warning(f"Failed to calculate RFM for customer {customer_id}: {e}")
                continue
        return results
