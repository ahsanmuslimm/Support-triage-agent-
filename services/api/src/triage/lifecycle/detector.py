"""Lifecycle stage detector orchestrator."""

from datetime import datetime
from typing import Dict, List, Optional
import logging

from .models import (
    CustomerLifecycleProfile,
    LifecycleStage,
    RFMDimensions,
)
from .rfm import RFMCalculator
from .clustering import LifecycleClusterer

logger = logging.getLogger(__name__)


class LifecycleDetector:
    """Main orchestrator for lifecycle stage detection."""

    def __init__(self):
        """Initialize detector with RFM calculator and clusterer."""
        self.rfm_calculator = RFMCalculator()
        self.clusterer = LifecycleClusterer()

    async def detect_customer_stage(
        self,
        tenant_id: int,
        customer_id: int,
        days_since_last_order: Optional[int] = None,
        days_since_last_ticket: Optional[int] = None,
        order_count_365d: int = 0,
        ticket_count_365d: int = 0,
        total_spend_365d: float = 0.0,
    ) -> CustomerLifecycleProfile:
        """
        Detect lifecycle stage for a single customer.

        Args:
            tenant_id: Tenant ID
            customer_id: Customer ID
            days_since_last_order: Days since last order
            days_since_last_ticket: Days since last ticket
            order_count_365d: Orders in last 365 days
            ticket_count_365d: Tickets in last 365 days
            total_spend_365d: Total spend in last 365 days

        Returns:
            CustomerLifecycleProfile
        """
        # Calculate RFM
        rfm = await self.rfm_calculator.calculate_rfm(
            tenant_id=tenant_id,
            customer_id=customer_id,
            days_since_last_order=days_since_last_order,
            days_since_last_ticket=days_since_last_ticket,
            order_count_365d=order_count_365d,
            ticket_count_365d=ticket_count_365d,
            total_spend_365d=total_spend_365d,
        )

        # Predict stage (clustering auto-fits if needed)
        stage, confidence = await self.clusterer.predict_stage(rfm)

        # Build stage reasons
        reasons = []
        if rfm.recency_score <= 2:
            reasons.append("low recency")
        if rfm.frequency_score >= 4:
            reasons.append("high frequency")
        if rfm.monetary_score <= 2:
            reasons.append("low monetary value")
        if stage == LifecycleStage.CHURNING:
            reasons.append("churning trend detected")

        return CustomerLifecycleProfile(
            customer_id=customer_id,
            tenant_id=tenant_id,
            stage=stage,
            confidence=confidence,
            stage_reasons=reasons,
            updated_at=datetime.utcnow(),
        )

    async def detect_lifecycle_for_tenant(
        self, tenant_id: int, customers_data: Dict[int, Dict]
    ) -> Dict[int, CustomerLifecycleProfile]:
        """
        Batch detect lifecycle for all customers in tenant.

        Args:
            tenant_id: Tenant ID
            customers_data: Dict mapping customer_id -> {rfm_params}

        Returns:
            Dict mapping customer_id -> CustomerLifecycleProfile
        """
        # Batch RFM calculation
        rfm_scores = await self.rfm_calculator.batch_calculate_rfm(
            tenant_id, customers_data
        )

        # Fit clustering model on RFM scores
        if rfm_scores:
            await self.clusterer.fit_kmeans(list(rfm_scores.values()))

        # Predict stages
        stage_assignments = await self.clusterer.assign_stages_batch(rfm_scores)

        # Build profiles
        profiles = {}
        for customer_id, (stage, confidence) in stage_assignments.items():
            rfm = rfm_scores[customer_id]
            reasons = []
            if rfm.recency_score <= 2:
                reasons.append("low recency")
            if rfm.frequency_score >= 4:
                reasons.append("high frequency")
            if rfm.monetary_score <= 2:
                reasons.append("low monetary value")

            profiles[customer_id] = CustomerLifecycleProfile(
                customer_id=customer_id,
                tenant_id=tenant_id,
                stage=stage,
                confidence=confidence,
                stage_reasons=reasons,
                updated_at=datetime.utcnow(),
            )

        return profiles

    async def get_engagement_strategy(
        self, stage: LifecycleStage
    ) -> Dict[str, float]:
        """
        Get engagement strategy for lifecycle stage.

        Args:
            stage: LifecycleStage

        Returns:
            Strategy dict with priority, sla_multiplier, retention_offer
        """
        strategies = {
            LifecycleStage.NEW: {
                "priority": 0.7,
                "sla_multiplier": 1.5,
                "retention_offer": 0.10,  # 10% discount
            },
            LifecycleStage.GROWTH: {
                "priority": 0.6,
                "sla_multiplier": 1.2,
                "retention_offer": 0.05,
            },
            LifecycleStage.MATURE: {
                "priority": 0.4,
                "sla_multiplier": 1.0,
                "retention_offer": 0.0,
            },
            LifecycleStage.CHURNING: {
                "priority": 0.9,
                "sla_multiplier": 2.0,
                "retention_offer": 0.20,  # 20% discount
            },
            LifecycleStage.CHURNED: {
                "priority": 0.5,
                "sla_multiplier": 0.5,
                "retention_offer": 0.30,  # Win-back offer
            },
        }
        return strategies.get(stage, {})
