"""Cost anomaly detection."""

import logging

logger = logging.getLogger(__name__)


class CostAnomalyDetector:
    """Detect cost anomalies."""

    def __init__(self):
        """Initialize detector."""

    async def detect_cost_spike(
        self, event_type: str, tenant_id: int, lookback_hours: int = 24
    ) -> tuple[bool, dict]:
        """Detect cost spike."""
        # Mock: return no anomaly
        return False, {"current_cost": 100, "mean": 80, "threshold": 120}

    async def log_anomaly(self, event: dict) -> None:
        """Log anomaly event."""
        logger.warning(f"Cost anomaly detected: {event}")
