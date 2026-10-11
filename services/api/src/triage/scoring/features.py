"""Health features extraction for ML scoring."""

from dataclasses import dataclass, asdict
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class HealthFeatures:
    """15 health features for churn risk prediction."""

    # RFM (Recency, Frequency, Monetary)
    recency_days: int  # Days since last order
    frequency: int  # Orders in last 90 days
    monetary_value: float  # Total spend in last 90 days

    # Engagement
    support_contact_count: int  # Support interactions in last 90 days
    avg_resolution_days: float  # Average support ticket resolution time

    # Payment health
    failed_payments_90d: int  # Failed payments in last 90 days
    chargeback_count: int  # Chargebacks ever

    # Subscription
    subscription_age_days: int  # Days since subscription start
    subscription_status_active: bool  # Active subscription (binary)
    plan_value_usd: float  # Monthly plan value

    # Account
    account_age_days: int  # Days since account creation
    total_order_count: int  # Lifetime orders

    # Risk signals
    high_value_order_count: int  # Orders >$500
    return_rate: float  # Refund rate (0.0-1.0)
    sentiment_negative_ratio: float  # Ratio of negative sentiments (0.0-1.0)

    def to_array(self) -> list[float]:
        """Convert to feature array for model inference."""
        return [
            float(self.recency_days),
            float(self.frequency),
            float(self.monetary_value),
            float(self.support_contact_count),
            float(self.avg_resolution_days),
            float(self.failed_payments_90d),
            float(self.chargeback_count),
            float(self.subscription_age_days),
            float(self.subscription_status_active),
            float(self.plan_value_usd),
            float(self.account_age_days),
            float(self.total_order_count),
            float(self.high_value_order_count),
            float(self.return_rate),
            float(self.sentiment_negative_ratio),
        ]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @staticmethod
    def feature_names() -> list[str]:
        """Return feature names in order."""
        return [
            "recency_days",
            "frequency",
            "monetary_value",
            "support_contact_count",
            "avg_resolution_days",
            "failed_payments_90d",
            "chargeback_count",
            "subscription_age_days",
            "subscription_status_active",
            "plan_value_usd",
            "account_age_days",
            "total_order_count",
            "high_value_order_count",
            "return_rate",
            "sentiment_negative_ratio",
        ]

    @staticmethod
    def validate(features: "HealthFeatures") -> bool:
        """Validate feature ranges."""
        checks = [
            features.recency_days >= 0,
            features.frequency >= 0,
            features.monetary_value >= 0,
            features.support_contact_count >= 0,
            features.avg_resolution_days >= 0,
            features.failed_payments_90d >= 0,
            features.chargeback_count >= 0,
            features.subscription_age_days >= 0,
            features.plan_value_usd >= 0,
            features.account_age_days >= 0,
            features.total_order_count >= 0,
            features.high_value_order_count >= 0,
            0 <= features.return_rate <= 1,
            0 <= features.sentiment_negative_ratio <= 1,
        ]

        if not all(checks):
            logger.warning(f"Feature validation failed: {features}")
            return False

        return True
