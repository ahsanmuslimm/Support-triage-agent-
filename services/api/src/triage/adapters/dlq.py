"""S6.3: Dead Letter Queue (DLQ) for failed events with retry policy."""
from datetime import datetime, timedelta
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class DeadLetterQueue:
    """Manage failed events with retry policy.

    Design (S6.3):
    - Captures events that fail after max retries
    - Stores with error context for manual inspection and replay
    - Supports exponential backoff retry policy
    - Integration with S6.2 Kafka topic: "triage.dlq"
    """

    MAX_RETRIES = 3
    RETRY_BACKOFF = [1, 10, 60]  # exponential backoff: 1s, 10s, 60s

    def __init__(self, event_bus: Any):
        self.event_bus = event_bus
        self.dlq_topic = "triage.dlq"

    async def send_to_dlq(
        self,
        event: dict[str, Any],
        error: Exception,
        retry_count: int = 0,
    ) -> None:
        """Send event to DLQ with error details.

        Args:
            event: Original event that failed
            error: Exception that was raised
            retry_count: Number of retries so far
        """
        dlq_event = {
            "original_event": event,
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": retry_count,
            "next_retry_at": self._calculate_next_retry(retry_count),
        }

        try:
            await self.event_bus.publish(
                event_type="dlq.event_failed",
                tenant_id=event.get("tenant_id", "unknown"),
                payload=dlq_event,
            )

            log.warning(
                "event_dlq_sent",
                event_id=event.get("id"),
                retry_count=retry_count,
                error=str(error),
            )
        except Exception as e:
            log.exception(
                "dlq_send_failed",
                event_id=event.get("id"),
                error=str(e),
            )

    def _calculate_next_retry(self, retry_count: int) -> str | None:
        """Calculate when event should be retried.

        Args:
            retry_count: Current retry count

        Returns:
            ISO 8601 timestamp for next retry, or None if max retries exceeded
        """
        if retry_count >= self.MAX_RETRIES:
            return None  # No more retries

        backoff_seconds = self.RETRY_BACKOFF[
            min(retry_count, len(self.RETRY_BACKOFF) - 1)
        ]
        next_retry = datetime.utcnow() + timedelta(seconds=backoff_seconds)
        return next_retry.isoformat()

    async def replay_from_dlq(
        self,
        dlq_event_id: str,
        handler_func: Any,
    ) -> bool:
        """Manually replay event from DLQ.

        Args:
            dlq_event_id: ID of DLQ event to replay
            handler_func: Async callable to handle event

        Returns:
            True if replay succeeded, False otherwise
        """
        try:
            # Fetch DLQ event from database
            # (implementation: query triage.dlq_events or retrieve from DLQ topic)

            # Re-invoke handler
            await handler_func(dlq_event_id)

            log.info("dlq_event_replayed", dlq_event_id=dlq_event_id)
            return True
        except Exception as e:
            log.exception(
                "dlq_replay_failed",
                dlq_event_id=dlq_event_id,
                error=str(e),
            )
            return False
