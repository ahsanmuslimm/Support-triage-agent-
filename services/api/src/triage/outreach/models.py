"""Proactive outreach campaign models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class CampaignType(str, Enum):
    """Types of proactive campaigns."""

    HEALTH_CHECK = "health_check"
    ENGAGEMENT = "engagement"
    BILLING_WINBACK = "billing_winback"
    LOYALTY_REWARD = "loyalty_reward"


class CampaignTemplate(BaseModel):
    """Campaign template with messaging."""

    template_id: str
    campaign_type: CampaignType
    channels: List[str]  # ['email', 'in_app']
    subject_line: str
    body_template: str  # Jinja2 template
    cta_text: str
    
    class Config:
        use_enum_values = False


class Campaign(BaseModel):
    """Campaign instance for a specific customer."""

    id: Optional[str] = None
    tenant_id: int
    customer_id: int
    template_id: str
    campaign_type: CampaignType
    variant: str  # 'A' or 'B' for A/B testing
    created_at: datetime
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = False


class ABTestResult(BaseModel):
    """A/B test results for a campaign type."""

    campaign_type: CampaignType
    variant: str  # 'A' or 'B'
    open_rate: float
    click_rate: float
    conversion_rate: float
    sample_size: int
    
    class Config:
        use_enum_values = False


@dataclass
class CampaignContext:
    """Context used to trigger campaigns."""

    customer_id: int
    tenant_id: int
    
    # Health and engagement signals
    health_score: float
    is_active: bool
    last_support_contact: Optional[datetime] = None
    is_vip: bool = False
    
    # Billing signals
    payment_failed_count: int = 0
    churn_risk: float = 0.0
    
    # Order signals
    order_count: int = 0
    last_order_date: Optional[datetime] = None
