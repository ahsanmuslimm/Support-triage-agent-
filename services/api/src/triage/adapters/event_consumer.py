"""S6.3 + S6.4: Resilient event consumer with retry logic and priority routing."""
import asyncio
from collections.abc import Callable
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class ResilientEventConsumer:
    """Consume events with built-in retry logic and priority queue integration.

    Design (S6.3 + S6.4):
    - Retry logic: exponential backoff (1s, 10s, 60s)
    - Max retries: 3 attempts before DLQ
    - Idempotency: Redis fast path + Postgres slow path
    - Priority routing: enqueue to appropriate lane (chat/email)
    - Starvation prevention: chat lane always prioritized
    """

    def __init__(
        self,
        event_bus: Any,
        idempotency_store: Any,
        dlq: Any,
        priority_queue: Any = None,
        max_retries: int = 3,
    ):
        self.event_bus = event_bus
        self.idempotency = idempotency_store
        self.dlq = dlq
        self.priority_queue = priority_queue
        self.max_retries = max_retries

    async def consume_with_retry(
        self,
        event: dict[str, Any],
        handler_func: Callable,
        use_slow_path: bool = False,
    ) -> None:
        """Consume event with retry policy.

        Retry logic:
        1. Attempt handler (0ms)
        2. On failure, retry with exponential backoff (1s, 10s, 60s)
        3. After 3 failures, send to DLQ

        Args:
            event: Event dict (must have tenant_id, id, type)
            handler_func: Async callable(event) -> result
            use_slow_path: Use durable Postgres idempotency path
        """
        tenant_id = event.get("tenant_id")
        event_id = event.get("id")

        for attempt in range(self.max_retries + 1):
            try:
                # Check idempotency
                idempotency_result = await self.idempotency.check_or_record(
                    tenant_id=tenant_id,
                    event_id=event_id,
                    event_type=event.get("type"),
                    use_slow_path=use_slow_path,
                )

                if idempotency_result.is_duplicate:
                    log.info(
                        "event_already_processed",
                        event_id=event_id,
                    )
                    return

                # Execute handler
                result = await handler_func(event)

                log.info(
                    "event_processed",
                    event_id=event_id,
                    tenant_id=tenant_id,
                    attempt=attempt + 1,
                )
                return

            except Exception as e:
                if attempt < self.max_retries:
                    # Retry with backoff
                    backoff_seconds = self._get_backoff(attempt)
                    log.warning(
                        "event_processing_failed_retry",
                        event_id=event_id,
                        attempt=attempt + 1,
                        backoff_seconds=backoff_seconds,
                        error=str(e),
                    )
                    await asyncio.sleep(backoff_seconds)
                else:
                    # Max retries exceeded → send to DLQ
                    log.error(
                        "event_processing_failed_dlq",
                        event_id=event_id,
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    await self.dlq.send_to_dlq(event, e, retry_count=attempt)
                    return

    async def consume_with_priority_routing(
        self,
        event: dict[str, Any],
        handler_func: Callable,
    ) -> None:
        """Consume event with priority-based routing to worker lanes.

        Design (S6.4):
        Routes event to appropriate priority queue based on channel.
        Chat/Web → high-priority lane (10 workers, 1-min SLA)
        Email → low-priority lane (3 workers, 8-hour SLA)

        Args:
            event: Event dict (must have channel, tenant_id)
            handler_func: Async callable(event) -> result
        """
        if not self.priority_queue:
            log.warning("priority_queue_not_configured")
            await self.consume_with_retry(event, handler_func)
            return

        try:
            # Enqueue to appropriate lane
            channel = event.get("channel", "email")
            queue_name = await self.priority_queue.enqueue_message(
                message_id=event.get("id"),
                tenant_id=event.get("tenant_id"),
                channel=channel,
                payload=event,
            )

            log.info(
                "event_enqueued_priority",
                event_id=event.get("id"),
                channel=channel,
                queue=queue_name,
            )

            # Handler will be invoked by worker pool (not here)

        except Exception as e:
            log.exception(
                "priority_routing_failed",
                event_id=event.get("id"),
                error=str(e),
            )
            # Fallback: process immediately without priority queuing
            await self.consume_with_retry(event, handler_func)

    @staticmethod
    def _get_backoff(attempt: int) -> float:
        """Calculate exponential backoff duration.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Backoff duration in seconds
        """
        backoff_values = [1, 10, 60]
        return float(backoff_values[min(attempt, len(backoff_values) - 1)])
