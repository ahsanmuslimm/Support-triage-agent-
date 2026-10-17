"""Lifecycle detection data models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class LifecycleStage(str, Enum):
    """Customer lifecycle stages."""

    NEW = "NEW"
    GROWTH = "GROWTH"
    MATURE = "MATURE"
    CHURNING = "CHURNING"
    CHURNED = "CHURNED"


class RFMDimensions(BaseModel):
    """RFM scoring dimensions (Recency, Frequency, Monetary)."""

    recency_score: int = Field(ge=0, le=5, description="Recency score 0-5")
    frequency_score: int = Field(ge=0, le=5, description="Frequency score 0-5")
    monetary_score: int = Field(ge=0, le=5, description="Monetary score 0-5")

    @property
    def composite_score(self) -> float:
        """Calculate composite RFM score (0-5 scale)."""
        return (self.recency_score + self.frequency_score + self.monetary_score) / 3.0


class CustomerRFMScore(BaseModel):
    """RFM score for a customer."""

    customer_id: int
    tenant_id: int
    rfm: RFMDimensions
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    valid_until: datetime


class CustomerLifecycleProfile(BaseModel):
    """Lifecycle stage profile for a customer."""

    customer_id: int
    tenant_id: int
    stage: LifecycleStage
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence 0-1")
    stage_reasons: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
