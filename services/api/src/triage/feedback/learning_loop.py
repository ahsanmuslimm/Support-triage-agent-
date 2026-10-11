"""S3.8: Continuous Learning Loop and Drift Detection."""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class LearningLoop:
    """Model retraining trigger, drift detection, and A/B testing."""

    def __init__(
        self,
        db_session=None,
        drift_threshold: float = 0.85,
        ewma_alpha: float = 0.1,
    ):
        self.db = db_session
        self.drift_threshold = drift_threshold
        self.ewma_alpha = ewma_alpha

    async def detect_drift(
        self, tenant_id: int, lookback_days: int = 7
    ) -> Optional[dict]:
        """
        Detect model drift using EWMA.

        Returns:
            {drifted: bool, smoothed_accuracy: float, alert_message: str} or None
        """
        if not self.db:
            return None

        try:
            cutoff = datetime.utcnow() - timedelta(days=lookback_days)

            # Fetch daily accuracy metrics
            metrics = await self.db.query(
                """
                SELECT accuracy FROM metric_history
                WHERE tenant_id = $1 AND metric_type = 'daily_accuracy'
                AND recorded_at >= $2
                ORDER BY recorded_at ASC
                """,
                tenant_id,
                cutoff,
            ).all()

            if len(metrics) < 2:
                return None

            accuracies = [m.accuracy for m in metrics]

            # Compute EWMA
            ewma = accuracies[0]
            for acc in accuracies[1:]:
                ewma = self.ewma_alpha * acc + (1 - self.ewma_alpha) * ewma

            drifted = ewma < self.drift_threshold
            alert_message = (
                f"Accuracy drift detected: {ewma:.3f} < {self.drift_threshold}"
                if drifted
                else f"No drift detected: {ewma:.3f}"
            )

            return {
                "drifted": drifted,
                "smoothed_accuracy": ewma,
                "alert_message": alert_message,
            }

        except Exception as e:
            logger.error(f"Drift detection failed: {e}")
            return None

    async def should_retrain(self, tenant_id: int) -> bool:
        """
        Determine if model should be retrained.

        Triggers:
        - Weekly accuracy drop >5%
        - Critical drift (<0.85)
        - >1000 new labeled examples
        """
        drift = await self.detect_drift(tenant_id, lookback_days=7)
        if drift and drift["drifted"]:
            logger.info(f"Retraining triggered for tenant {tenant_id}: drift detected")
            return True

        # Check for sufficient new labeled data
        if self.db:
            try:
                cutoff = datetime.utcnow() - timedelta(days=7)
                feedback_count = await self.db.query(
                    """
                    SELECT COUNT(*) as cnt FROM feedback_events
                    WHERE tenant_id = $1 AND created_at >= $2
                    """,
                    tenant_id,
                    cutoff,
                ).first()

                if feedback_count.cnt > 1000:
                    logger.info(
                        f"Retraining triggered for tenant {tenant_id}: {feedback_count.cnt} feedback events"
                    )
                    return True
            except Exception as e:
                logger.warning(f"Could not check feedback count: {e}")

        return False

    async def log_metric(
        self, tenant_id: int, metric_type: str, value: float
    ) -> bool:
        """Log metric for drift detection."""
        if not self.db:
            return False

        try:
            await self.db.execute(
                """
                INSERT INTO metric_history (tenant_id, metric_type, value, recorded_at)
                VALUES ($1, $2, $3, NOW())
                """,
                tenant_id,
                metric_type,
                value,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to log metric: {e}")
            return False
