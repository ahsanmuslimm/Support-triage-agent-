"""Anomaly detection models and signal types."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class SignalType(str, Enum):
    """Types of anomalies detected."""

    CHURN_SPIKE = "churn_spike"
    FRAUD_PATTERN = "fraud_pattern"
    COMPLAINT_SURGE = "complaint_surge"
    RESPONSE_DELAY = "response_delay"
    VOLUME_SPIKE = "volume_spike"
    API_ERROR_RATE = "api_error_rate"


class AnomalySignal(BaseModel):
    """Signal representing an anomaly event."""

    signal_type: SignalType
    tenant_id: int
    timestamp: datetime
    value: float
    threshold: float
    deviation_sigma: float  # Standard deviations above baseline
    confidence: float  # 0.0 - 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    class Config:
        use_enum_values = False


@dataclass
class AnomalyMetrics:
    """Historical metrics for anomaly detection."""

    tenant_id: int
    signal_type: SignalType

    # Current values
    current_value: float
    smoothed_value: float  # EWMA

    # Baseline statistics
    baseline_mean: float
    baseline_std: float

    # Anomaly indicators
    deviation_sigma: float
    is_anomaly: bool
    anomaly_confidence: float

    updated_at: datetime = field(default_factory=datetime.utcnow)
