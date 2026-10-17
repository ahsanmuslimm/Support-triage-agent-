"""Feedback loop extension for Sprint 4 signals."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FeedbackLoopS4:
    """Feedback ingestion and routing for Sprint 4 signals."""

    def __init__(self, db_session=None):
        """
        Initialize feedback loop.

        Args:
            db_session: Database session
        """
        self.db_session = db_session

    async def ingest_override_reason(self, override_reason) -> bool:
        """
        Ingest human override reason.

        Args:
            override_reason: OverrideReason object

        Returns:
            Success flag
        """
        try:
            logger.info(
                f"Ingested override: escalation={override_reason.escalation_id} "
                f"decision={override_reason.override_decision} "
                f"reason={override_reason.reason_text}"
            )

            # Route to escalation rules engine for model improvement
            await self._route_to_escalation_rules(override_reason)

            # Log to feedback_signals table
            await self._log_feedback_signal(
                tenant_id=override_reason.tenant_id,
                signal_type="override_reason",
                metadata=override_reason.dict(),
            )

            return True
        except Exception as e:
            logger.error(f"Failed to ingest override reason: {e}")
            return False

    async def ingest_sentiment_shift(
        self,
        customer_id: int,
        tenant_id: int,
        previous_sentiment: float,
        current_sentiment: float,
        delta: float,
    ) -> bool:
        """
        Ingest sentiment shift (CSAT delta).

        Args:
            customer_id: Customer ID
            tenant_id: Tenant ID
            previous_sentiment: Previous sentiment score
            current_sentiment: Current sentiment score
            delta: Difference

        Returns:
            Success flag
        """
        try:
            logger.info(
                f"Ingested sentiment shift: customer={customer_id} "
                f"delta={delta} ({previous_sentiment} -> {current_sentiment})"
            )

            # Route to health scorer for customer health recalculation
            await self._route_to_health_scorer(customer_id, tenant_id, delta)

            # Log to feedback_signals
            await self._log_feedback_signal(
                tenant_id=tenant_id,
                signal_type="sentiment_shift",
                metadata={
                    "customer_id": customer_id,
                    "previous": previous_sentiment,
                    "current": current_sentiment,
                    "delta": delta,
                },
            )

            return True
        except Exception as e:
            logger.error(f"Failed to ingest sentiment shift: {e}")
            return False

    async def ingest_retraining_trigger(
        self,
        trigger_type: str,
        model_name: str,
        metric_name: str,
        threshold: float,
        current_value: float,
    ) -> bool:
        """
        Ingest model retraining trigger.

        Args:
            trigger_type: 'accuracy', 'drift', 'coverage'
            model_name: Model being monitored
            metric_name: Metric that triggered
            threshold: Alert threshold
            current_value: Current metric value

        Returns:
            Success flag
        """
        try:
            logger.warning(
                f"Retraining trigger: model={model_name} "
                f"metric={metric_name} threshold={threshold} current={current_value}"
            )

            # Route to learning loop for model retraining
            await self._route_to_learning_loop(trigger_type, model_name, current_value)

            # Log to feedback_signals
            await self._log_feedback_signal(
                tenant_id=0,  # Global signal
                signal_type="retraining_trigger",
                metadata={
                    "trigger_type": trigger_type,
                    "model_name": model_name,
                    "metric_name": metric_name,
                    "threshold": threshold,
                    "current": current_value,
                },
            )

            return True
        except Exception as e:
            logger.error(f"Failed to ingest retraining trigger: {e}")
            return False

    async def _route_to_escalation_rules(self, override_reason) -> bool:
        """Route override reason to escalation rules engine."""
        try:
            # Would call EscalationRulesEngine to update rules based on feedback
            logger.debug(
                f"Routed override to escalation rules: {override_reason.override_decision}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to route to escalation rules: {e}")
            return False

    async def _route_to_health_scorer(
        self,
        customer_id: int,
        tenant_id: int,
        sentiment_delta: float,
    ) -> bool:
        """Route sentiment shift to health scorer."""
        try:
            # Would call health scorer to recalculate customer health
            logger.debug(
                f"Routed sentiment shift to health scorer: customer={customer_id} delta={sentiment_delta}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to route to health scorer: {e}")
            return False

    async def _route_to_learning_loop(
        self,
        trigger_type: str,
        model_name: str,
        current_value: float,
    ) -> bool:
        """Route retraining trigger to learning loop."""
        try:
            # Would initiate model retraining pipeline
            logger.debug(
                f"Routed retraining trigger to learning loop: "
                f"model={model_name} trigger={trigger_type}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to route to learning loop: {e}")
            return False

    async def _log_feedback_signal(
        self,
        tenant_id: int,
        signal_type: str,
        metadata: dict[str, Any],
    ) -> bool:
        """
        Log feedback signal to feedback_signals table.

        Args:
            tenant_id: Tenant ID
            signal_type: Type of signal
            metadata: Signal metadata

        Returns:
            Success flag
        """
        try:
            # In real implementation, insert into feedback_signals table
            logger.debug(
                f"Logged feedback signal: tenant={tenant_id} type={signal_type}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to log feedback signal: {e}")
            return False
