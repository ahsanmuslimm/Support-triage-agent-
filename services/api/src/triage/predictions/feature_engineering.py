"""Feature engineering for predictive models."""

import logging

from sklearn.preprocessing import MinMaxScaler

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Extract and engineer features for ML models."""

    def __init__(self):
        """Initialize feature engineer with scalers."""
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.feature_names = [
            "lifecycle_stage_numeric",
            "days_since_last_issue",
            "issue_frequency_30d",
            "avg_resolution_time_hours",
            "escalation_ratio_30d",
            "account_age_days",
            "total_lifetime_spend",
            "support_sentiment_avg",
            "health_score",
            "account_active",
            "subscription_plan_value",
            "chargeback_count_90d",
        ]

    async def extract_features(
        self,
        customer_id: int,
        tenant_id: int,
        lifecycle_stage: str | None = None,
        days_since_last_issue: int = 999,
        issue_frequency_30d: int = 0,
        avg_resolution_time_hours: float = 0.0,
        escalation_count_30d: int = 0,
        total_issues_30d: int = 1,
        account_age_days: int = 30,
        total_lifetime_spend: float = 0.0,
        support_sentiment_avg: float = 0.5,
        health_score: float = 0.5,
        account_active: bool = True,
        subscription_plan_value: float = 0.0,
        chargeback_count_90d: int = 0,
    ) -> dict[str, float]:
        """
        Extract features for a customer.

        Args:
            customer_id: Customer ID
            tenant_id: Tenant ID
            lifecycle_stage: Current lifecycle stage (NEW, GROWTH, MATURE, CHURNING, CHURNED)
            days_since_last_issue: Days since last support issue
            issue_frequency_30d: Count of issues in last 30 days
            avg_resolution_time_hours: Average time to resolve issues
            escalation_count_30d: Count of escalations in last 30 days
            total_issues_30d: Total issues in last 30 days
            account_age_days: Account age in days
            total_lifetime_spend: Total spend in USD
            support_sentiment_avg: Average sentiment (0-1)
            health_score: Account health score (0-1)
            account_active: Whether account is active
            subscription_plan_value: Monthly subscription value in USD
            chargeback_count_90d: Count of chargebacks in last 90 days

        Returns:
            Dict mapping feature_name -> normalized value (0-1)
        """
        # Map lifecycle stage to numeric value
        stage_map = {
            "NEW": 0.2,
            "GROWTH": 0.4,
            "MATURE": 0.6,
            "CHURNING": 0.8,
            "CHURNED": 1.0,
            None: 0.5,
        }
        lifecycle_numeric = stage_map.get(lifecycle_stage, 0.5)

        # Calculate escalation ratio
        escalation_ratio = (
            escalation_count_30d / total_issues_30d if total_issues_30d > 0 else 0.0
        )

        # Raw features
        raw_features = {
            "lifecycle_stage_numeric": lifecycle_numeric,
            "days_since_last_issue": min(days_since_last_issue / 365.0, 1.0),  # normalize to [0,1]
            "issue_frequency_30d": min(issue_frequency_30d / 50.0, 1.0),  # assume max 50
            "avg_resolution_time_hours": min(
                avg_resolution_time_hours / 168.0, 1.0
            ),  # max 1 week
            "escalation_ratio_30d": escalation_ratio,
            "account_age_days": min(account_age_days / 1825.0, 1.0),  # 5 years
            "total_lifetime_spend": min(total_lifetime_spend / 10000.0, 1.0),  # $10k max
            "support_sentiment_avg": support_sentiment_avg,
            "health_score": health_score,
            "account_active": float(account_active),
            "subscription_plan_value": min(subscription_plan_value / 1000.0, 1.0),  # $1k max
            "chargeback_count_90d": min(chargeback_count_90d / 5.0, 1.0),  # max 5
        }

        # Ensure all values in [0, 1]
        normalized = {}
        for name in self.feature_names:
            value = raw_features.get(name, 0.0)
            normalized[name] = max(0.0, min(1.0, value))

        return normalized

    async def batch_extract_features(
        self,
        tenant_id: int,
        customers_data: dict[int, dict],
    ) -> dict[int, dict[str, float]]:
        """
        Extract features for multiple customers.

        Args:
            tenant_id: Tenant ID
            customers_data: Dict mapping customer_id -> {feature_params}

        Returns:
            Dict mapping customer_id -> {feature_name -> value}
        """
        results = {}
        for customer_id, data in customers_data.items():
            try:
                features = await self.extract_features(
                    customer_id=customer_id,
                    tenant_id=tenant_id,
                    **data,
                )
                results[customer_id] = features
            except Exception as e:
                logger.warning(f"Failed to extract features for customer {customer_id}: {e}")
                continue
        return results

    def get_feature_names(self) -> list:
        """Get list of feature names."""
        return self.feature_names
