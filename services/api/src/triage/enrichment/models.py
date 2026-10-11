"""Enrichment data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class CustomerContext:
    """Customer profile and account enrichment."""

    customer_id: int
    tenant_id: int

    # Profile
    name: str
    email: str
    phone: Optional[str] = None
    account_created_at: Optional[datetime] = None
    account_age_days: int = 0

    # Account stats
    order_count: int = 0
    total_spent: float = 0.0
    last_order_date: Optional[datetime] = None
    avg_order_value: float = 0.0

    # Subscription
    subscription_status: str = "none"  # 'active', 'paused', 'cancelled', 'none'
    subscription_plan: str = "none"  # 'starter', 'pro', 'enterprise'
    plan_value_usd: float = 0.0

    # Flags
    flags: List[str] = field(default_factory=list)

    # Computed signals
    is_vip: bool = False  # total_spent > $1000
    is_at_risk: bool = False  # churned or paused
    is_fraud_flagged: bool = False

    # Cache metadata
    fetched_at: Optional[datetime] = None
    cache_ttl_seconds: int = 3600


@dataclass
class OrderContext:
    """Order history and transaction patterns."""

    customer_id: int
    tenant_id: int

    # Order stats (last 90 days)
    order_count_90d: int = 0
    refund_count_90d: int = 0
    chargeback_count_90d: int = 0
    total_value_90d: float = 0.0
    avg_order_value_90d: float = 0.0

    # Risk signals
    high_value_orders: int = 0  # >$500
    return_rate: float = 0.0  # refunds / orders
    is_high_velocity: bool = False  # >5 orders in last 30 days

    # Seasonal patterns
    ordering_frequency_median: float = 0.0  # days between orders
    risk_score: float = 0.0  # 0.0 - 1.0

    # Cache metadata
    fetched_at: Optional[datetime] = None
    cache_ttl_seconds: int = 3600


@dataclass
class BillingContext:
    """Payment and billing history."""

    customer_id: int
    tenant_id: int

    # Payment methods
    payment_method_count: int = 0
    primary_payment_type: str = "unknown"  # 'card', 'bank_transfer', 'paypal'

    # Card status
    card_expiring_soon: bool = False  # <30 days
    card_expiry_days: Optional[int] = None

    # Payment health
    failed_payments_90d: int = 0
    successful_payments_90d: int = 0
    payment_success_rate: float = 1.0

    # Dunning and churn risk
    dunning_stage: str = "none"  # 'initial', 'escalation', 'final', 'suspended', 'none'
    is_churn_risk: bool = False  # 3+ failed payments or final dunning
    dunning_days: int = 0  # days since dunning started

    # Address and verification
    billing_address_valid: bool = True
    phone_verified: bool = False

    # Cache metadata
    fetched_at: Optional[datetime] = None
    cache_ttl_seconds: int = 3600


@dataclass
class SentimentContext:
    """Customer sentiment and satisfaction."""

    customer_id: int
    tenant_id: int

    # Sentiment analysis
    latest_sentiment: str = "neutral"  # 'positive', 'neutral', 'negative'
    sentiment_score: float = 0.0  # -1.0 to 1.0
    sentiment_trend: str = "stable"  # 'improving', 'declining', 'stable'

    # NPS
    latest_nps: Optional[int] = None
    nps_segment: str = "passive"  # 'promoter', 'passive', 'detractor'
    nps_trend: str = "stable"  # 'improving', 'declining', 'stable'
    nps_history: List[int] = field(default_factory=list)  # last 5 scores

    # Interaction sentiment over time
    sentiment_history: List[float] = field(default_factory=list)  # last 5 scores

    # Risk segmentation
    is_promoter: bool = False
    is_detractor: bool = False

    # Cache metadata
    fetched_at: Optional[datetime] = None
    cache_ttl_seconds: int = 3600


@dataclass
class EnrichmentBundle:
    """Complete enrichment context for a customer interaction."""

    customer_id: int
    tenant_id: int

    customer: CustomerContext
    order: OrderContext
    billing: BillingContext
    sentiment: SentimentContext

    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert bundle to dictionary for serialization."""
        return {
            "customer_id": self.customer_id,
            "tenant_id": self.tenant_id,
            "customer": self.customer.__dict__,
            "order": self.order.__dict__,
            "billing": self.billing.__dict__,
            "sentiment": self.sentiment.__dict__,
            "fetched_at": self.fetched_at.isoformat(),
        }
