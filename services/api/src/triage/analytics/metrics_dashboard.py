"""S3.9: Business Intelligence & Analytics Dashboards."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class MetricsDashboard:
    """Analytics and metrics for dashboard display."""

    def __init__(self, db_session=None):
        self.db = db_session

    async def get_summary_metrics(self, tenant_id: int) -> Optional[Dict]:
        """
        Get summary metrics for dashboard.

        Returns:
            {triage_rate, escalation_pct, avg_resolution_time_sec, csat_score, cost_per_resolution}
        """
        if not self.db:
            return None

        try:
            # Fetch from materialized view
            result = await self.db.query(
                """
                SELECT * FROM v_triage_daily_summary
                WHERE tenant_id = $1
                ORDER BY recorded_at DESC
                LIMIT 1
                """,
                tenant_id,
            ).first()

            if result:
                return {
                    "triage_rate": result.triage_rate,
                    "escalation_pct": result.escalation_pct,
                    "avg_resolution_time_sec": result.avg_resolution_time_sec,
                    "csat_score": result.csat_score,
                    "cost_per_resolution": result.cost_per_resolution,
                    "recorded_at": result.recorded_at,
                }

            return None
        except Exception as e:
            logger.error(f"Failed to fetch summary metrics: {e}")
            return None

    async def get_agent_performance(
        self, tenant_id: int, days: int = 7
    ) -> Optional[List[Dict]]:
        """
        Get agent performance metrics.

        Returns:
            List of {agent_id, autonomy_rate, avg_resolution_time, csat_score}
        """
        if not self.db:
            return None

        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            results = await self.db.query(
                """
                SELECT * FROM v_agent_performance_daily
                WHERE tenant_id = $1 AND recorded_at >= $2
                """,
                tenant_id,
                cutoff,
            ).all()

            return [
                {
                    "agent_id": r.agent_id,
                    "autonomy_rate": r.autonomy_rate,
                    "avg_resolution_time": r.avg_resolution_time,
                    "csat_score": r.csat_score,
                    "recorded_at": r.recorded_at,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to fetch agent performance: {e}")
            return None

    async def get_customer_outcomes(
        self, tenant_id: int, days: int = 7
    ) -> Optional[List[Dict]]:
        """
        Get customer outcome metrics by segment.

        Returns:
            List of {segment, resolution_rate, escalation_count, churn_rate}
        """
        if not self.db:
            return None

        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            results = await self.db.query(
                """
                SELECT * FROM v_customer_outcomes_daily
                WHERE tenant_id = $1 AND recorded_at >= $2
                """,
                tenant_id,
                cutoff,
            ).all()

            return [
                {
                    "segment": r.segment,
                    "resolution_rate": r.resolution_rate,
                    "escalation_count": r.escalation_count,
                    "churn_rate": r.churn_rate,
                    "recorded_at": r.recorded_at,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to fetch customer outcomes: {e}")
            return None

    async def detect_anomalies(self, tenant_id: int) -> Optional[List[Dict]]:
        """
        Detect metric anomalies using EWMA.

        Returns:
            List of {metric_name, current_value, expected_value, deviation_sigma}
        """
        if not self.db:
            return None

        try:
            results = await self.db.query(
                """
                SELECT * FROM v_anomalies
                WHERE tenant_id = $1 AND recorded_at >= NOW() - INTERVAL '1 day'
                ORDER BY deviation_sigma DESC
                LIMIT 10
                """,
                tenant_id,
            ).all()

            return [
                {
                    "metric_name": r.metric_name,
                    "current_value": r.current_value,
                    "expected_value": r.expected_value,
                    "deviation_sigma": r.deviation_sigma,
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to detect anomalies: {e}")
            return None
