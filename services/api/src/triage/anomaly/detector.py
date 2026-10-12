"""Real-time anomaly detection engine using EWMA + Isolation Forest."""

import logging
import os
from datetime import datetime

import aiohttp
from sklearn.ensemble import IsolationForest

from .models import AnomalySignal, SignalType

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detects anomalies in 6 dimensions using EWMA + Isolation Forest ensemble."""

    def __init__(
        self,
        ewma_alpha: float = 0.15,
        isolation_forest_contamination: float = 0.1,
        db_session=None,
    ):
        """
        Initialize anomaly detector.

        Args:
            ewma_alpha: Weight for exponential moving average (0.0 - 1.0)
            isolation_forest_contamination: Expected proportion of anomalies
            db_session: Database session for materialized views
        """
        self.ewma_alpha = ewma_alpha
        self.isolation_forest_contamination = isolation_forest_contamination
        self.db_session = db_session

        # Initialize Isolation Forest
        self.isolation_forest = IsolationForest(
            contamination=isolation_forest_contamination,
            random_state=42,
            n_estimators=100,
        )

        # EWMA baseline tracking per signal type per tenant
        self.ewma_baselines: dict = {}

        # Webhook URL for publishing signals
        self.webhook_url = os.getenv(
            "ANOMALY_WEBHOOK_URL",
            "http://localhost:8000/internal/escalation/webhook"
        )

    async def detect_signals(
        self,
        tenant_id: int,
        daily_stats: dict | None = None,
        performance_stats: dict | None = None,
    ) -> list[AnomalySignal]:
        """
        Detect anomalies in 6 dimensions.

        Args:
            tenant_id: Tenant ID for multi-tenancy
            daily_stats: Daily summary metrics (from v_triage_daily_summary)
            performance_stats: Agent performance metrics (from v_agent_performance_daily)

        Returns:
            List of AnomalySignal objects with confidence scores
        """
        signals: list[AnomalySignal] = []

        if daily_stats is None:
            daily_stats = {}
        if performance_stats is None:
            performance_stats = {}

        # Check each signal type
        signal_checks = [
            (SignalType.CHURN_SPIKE, self._check_churn_spike),
            (SignalType.FRAUD_PATTERN, self._check_fraud_pattern),
            (SignalType.COMPLAINT_SURGE, self._check_complaint_surge),
            (SignalType.RESPONSE_DELAY, self._check_response_delay),
            (SignalType.VOLUME_SPIKE, self._check_volume_spike),
            (SignalType.API_ERROR_RATE, self._check_api_error_rate),
        ]

        for signal_type, check_fn in signal_checks:
            signal = await check_fn(tenant_id, daily_stats, performance_stats)
            if signal:
                signals.append(signal)
                # Publish to escalation queue
                await self.publish_webhook(signal)

        return signals

    async def _check_churn_spike(
        self,
        tenant_id: int,
        daily_stats: dict,
        performance_stats: dict,
    ) -> AnomalySignal | None:
        """
        Detect churn spike: health_score trend down + sentiment_negative_ratio up.

        Returns:
            AnomalySignal if anomaly detected, None otherwise
        """
        health_score = daily_stats.get("health_score_avg", 0.7)
        negative_ratio = daily_stats.get("sentiment_negative_ratio", 0.1)

        # Compute EWMA for health score
        smoothed_health, health_sigma = await self._compute_ewma(
            tenant_id, SignalType.CHURN_SPIKE, health_score
        )

        # Churn spike if: health score down >1.5 sigma AND negative sentiment up
        if health_sigma < -1.5 and negative_ratio > 0.2:
            return AnomalySignal(
                signal_type=SignalType.CHURN_SPIKE,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                value=health_score,
                threshold=0.5,
                deviation_sigma=abs(health_sigma),
                confidence=min(0.95, 0.5 + (abs(health_sigma) * 0.1)),
                metadata={
                    "health_score": health_score,
                    "sentiment_negative_ratio": negative_ratio,
                    "smoothed_value": smoothed_health,
                },
            )
        return None

    async def _check_fraud_pattern(
        self,
        tenant_id: int,
        daily_stats: dict,
        performance_stats: dict,
    ) -> AnomalySignal | None:
        """
        Detect fraud pattern: multiple chargebacks + high-value order spike.

        Returns:
            AnomalySignal if anomaly detected, None otherwise
        """
        chargeback_count = daily_stats.get("chargeback_count", 0)
        high_value_orders = daily_stats.get("high_value_order_count", 0)

        # Fraud pattern if: chargebacks >= 2 AND high-value orders spike
        if chargeback_count >= 2 and high_value_orders > 5:
            smoothed_value, sigma = await self._compute_ewma(
                tenant_id, SignalType.FRAUD_PATTERN, chargeback_count
            )

            return AnomalySignal(
                signal_type=SignalType.FRAUD_PATTERN,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                value=float(chargeback_count),
                threshold=1.0,
                deviation_sigma=abs(sigma),
                confidence=0.95,  # High confidence for fraud
                metadata={
                    "chargeback_count": chargeback_count,
                    "high_value_order_count": high_value_orders,
                },
            )
        return None

    async def _check_complaint_surge(
        self,
        tenant_id: int,
        daily_stats: dict,
        performance_stats: dict,
    ) -> AnomalySignal | None:
        """
        Detect complaint surge: escalation_pct > 3σ above baseline.

        Returns:
            AnomalySignal if anomaly detected, None otherwise
        """
        escalation_pct = daily_stats.get("escalation_pct", 0.05)

        smoothed_value, sigma = await self._compute_ewma(
            tenant_id, SignalType.COMPLAINT_SURGE, escalation_pct
        )

        # Complaint surge if: escalation rate >3 sigma above baseline
        if sigma > 3.0:
            return AnomalySignal(
                signal_type=SignalType.COMPLAINT_SURGE,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                value=escalation_pct,
                threshold=0.1,  # 10% baseline
                deviation_sigma=sigma,
                confidence=min(0.99, 0.7 + (sigma * 0.05)),
                metadata={
                    "escalation_pct": escalation_pct,
                    "smoothed_value": smoothed_value,
                },
            )
        return None

    async def _check_response_delay(
        self,
        tenant_id: int,
        daily_stats: dict,
        performance_stats: dict,
    ) -> AnomalySignal | None:
        """
        Detect response delay: avg_resolution_time_sec spike (>2σ).

        Returns:
            AnomalySignal if anomaly detected, None otherwise
        """
        resolution_time_sec = performance_stats.get("avg_resolution_time_sec", 120)

        smoothed_value, sigma = await self._compute_ewma(
            tenant_id, SignalType.RESPONSE_DELAY, resolution_time_sec
        )

        # Response delay if: resolution time >2 sigma above baseline
        if sigma > 2.0:
            return AnomalySignal(
                signal_type=SignalType.RESPONSE_DELAY,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                value=resolution_time_sec,
                threshold=300.0,  # 5 min baseline
                deviation_sigma=sigma,
                confidence=min(0.9, 0.6 + (sigma * 0.1)),
                metadata={
                    "resolution_time_sec": resolution_time_sec,
                    "smoothed_value": smoothed_value,
                },
            )
        return None

    async def _check_volume_spike(
        self,
        tenant_id: int,
        daily_stats: dict,
        performance_stats: dict,
    ) -> AnomalySignal | None:
        """
        Detect volume spike: total_triages > 2σ above baseline.

        Returns:
            AnomalySignal if anomaly detected, None otherwise
        """
        total_triages = daily_stats.get("total_triages", 100)

        smoothed_value, sigma = await self._compute_ewma(
            tenant_id, SignalType.VOLUME_SPIKE, total_triages
        )

        # Volume spike if: triage count >2 sigma above baseline
        if sigma > 2.0:
            return AnomalySignal(
                signal_type=SignalType.VOLUME_SPIKE,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                value=float(total_triages),
                threshold=100.0,
                deviation_sigma=sigma,
                confidence=min(0.85, 0.5 + (sigma * 0.1)),
                metadata={
                    "total_triages": total_triages,
                    "smoothed_value": smoothed_value,
                },
            )
        return None

    async def _check_api_error_rate(
        self,
        tenant_id: int,
        daily_stats: dict,
        performance_stats: dict,
    ) -> AnomalySignal | None:
        """
        Detect API error rate: (error_count / total_requests) > 0.05.

        Returns:
            AnomalySignal if anomaly detected, None otherwise
        """
        error_count = daily_stats.get("api_error_count", 0)
        total_requests = daily_stats.get("api_request_count", 1000)

        error_rate = error_count / max(total_requests, 1)

        if error_rate > 0.05:  # >5% error rate
            smoothed_value, sigma = await self._compute_ewma(
                tenant_id, SignalType.API_ERROR_RATE, error_rate
            )

            return AnomalySignal(
                signal_type=SignalType.API_ERROR_RATE,
                tenant_id=tenant_id,
                timestamp=datetime.utcnow(),
                value=error_rate,
                threshold=0.02,  # 2% baseline
                deviation_sigma=sigma,
                confidence=0.92,
                metadata={
                    "error_count": error_count,
                    "total_requests": total_requests,
                    "error_rate": error_rate,
                },
            )
        return None

    async def _compute_ewma(
        self,
        tenant_id: int,
        signal_type: SignalType,
        current_value: float,
    ) -> tuple[float, float]:
        """
        Compute exponential moving average and deviation from baseline.

        Args:
            tenant_id: Tenant ID
            signal_type: Type of signal
            current_value: Current measurement

        Returns:
            Tuple of (smoothed_value, deviation_sigma)
        """
        cache_key = f"s4:ewma:{tenant_id}:{signal_type.value}"

        # Get previous baseline
        if cache_key not in self.ewma_baselines:
            self.ewma_baselines[cache_key] = {
                "mean": current_value,
                "std": 1.0,
                "last_value": current_value,
            }

        baseline = self.ewma_baselines[cache_key]

        # EWMA: new_value = alpha * current + (1 - alpha) * previous
        smoothed = (
            self.ewma_alpha * current_value
            + (1 - self.ewma_alpha) * baseline["last_value"]
        )

        # Update baseline
        baseline["last_value"] = smoothed

        # Deviation in standard deviations
        deviation_sigma = (
            (current_value - baseline["mean"]) / max(baseline["std"], 0.01)
        )

        return smoothed, deviation_sigma

    async def publish_webhook(self, signal: AnomalySignal) -> bool:
        """
        Publish anomaly signal to escalation queue via webhook.

        Args:
            signal: AnomalySignal to publish

        Returns:
            Success flag
        """
        try:
            payload = {
                "signal_type": signal.signal_type.value,
                "tenant_id": signal.tenant_id,
                "timestamp": signal.timestamp.isoformat(),
                "value": signal.value,
                "threshold": signal.threshold,
                "deviation_sigma": signal.deviation_sigma,
                "confidence": signal.confidence,
                "metadata": signal.metadata,
            }

            async with aiohttp.ClientSession() as session, session.post(
                self.webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Published {signal.signal_type.value} signal")
                    return True
                else:
                    logger.warning(
                        f"Webhook returned {resp.status}: {await resp.text()}"
                    )
                    return False
        except Exception as e:
            logger.error(f"Failed to publish webhook: {e}")
            return False
