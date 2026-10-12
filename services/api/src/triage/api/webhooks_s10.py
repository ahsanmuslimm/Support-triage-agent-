"""Outbound webhooks with retry and dead-letter (S10.3)."""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, ClassVar

import httpx


class WebhookEventType(str, Enum):
    """Webhook event types."""

    CONVERSATION_CREATED = "conversation.created"
    MESSAGE_RECEIVED = "message.received"
    ESCALATION_TRIGGERED = "escalation.triggered"
    AUTONOMY_PROMOTED = "autonomy.promoted"
    POLICY_BLOCKED = "policy.blocked"


@dataclass
class WebhookEvent:
    """Webhook event to deliver."""

    event_type: WebhookEventType
    tenant_id: str
    resource_id: str
    timestamp: datetime
    data: dict[str, Any]
    attempt: int = 1
    next_retry: datetime | None = None

    def to_json(self) -> str:
        """Serialize event to JSON."""
        return json.dumps({
            "event_type": self.event_type.value,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        })


@dataclass
class WebhookEndpoint:
    """Registered webhook endpoint."""

    endpoint_id: str
    tenant_id: str
    url: str
    webhook_secret: str
    events: list[WebhookEventType]
    active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class WebhookDeliveryLog:
    """Record of webhook delivery attempt."""

    event_id: str
    endpoint_id: str
    attempt: int
    status_code: int | None
    success: bool
    error: str | None
    timestamp: datetime


class WebhookSignature:
    """Sign and verify webhook payloads."""

    @staticmethod
    def sign(payload: str, webhook_secret: str) -> str:
        """Sign webhook payload with HMAC-SHA256.

        Args:
            payload: JSON payload
            webhook_secret: Webhook secret

        Returns:
            Hex-encoded signature
        """
        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    @staticmethod
    def verify(payload: str, signature: str, webhook_secret: str) -> bool:
        """Verify webhook signature.

        Args:
            payload: JSON payload
            signature: Provided signature
            webhook_secret: Webhook secret

        Returns:
            True if signature valid
        """
        expected_signature = WebhookSignature.sign(payload, webhook_secret)
        return hmac.compare_digest(signature, expected_signature)


class WebhookRetryPolicy:
    """Exponential backoff retry policy."""

    # Retry intervals: 1s, 10s, 100s, 1000s (max 4 attempts)
    RETRY_INTERVALS: ClassVar[list[int]] = [1, 10, 100, 1000]
    MAX_ATTEMPTS = 4
    RETENTION_WINDOW_HOURS = 24

    @staticmethod
    def get_next_retry_time(attempt: int, base_time: datetime | None = None) -> datetime | None:
        """Get next retry time for attempt.

        Args:
            attempt: Attempt number (1-indexed). After attempt N, we use RETRY_INTERVALS[N]
            base_time: Base time for retry

        Returns:
            Datetime for next retry, or None if max attempts exceeded
        """
        if attempt >= WebhookRetryPolicy.MAX_ATTEMPTS:
            return None

        if base_time is None:
            base_time = datetime.utcnow()

        # Use attempt as index (0-indexed into RETRY_INTERVALS)
        if attempt < len(WebhookRetryPolicy.RETRY_INTERVALS):
            delay_seconds = WebhookRetryPolicy.RETRY_INTERVALS[attempt]
            return base_time + timedelta(seconds=delay_seconds)

        return None

    @staticmethod
    def should_retry(attempt: int, status_code: int) -> bool:
        """Determine if request should be retried.

        Args:
            attempt: Current attempt number
            status_code: HTTP status code

        Returns:
            True if should retry
        """
        if attempt >= WebhookRetryPolicy.MAX_ATTEMPTS:
            return False

        # Retry on 5xx errors and timeout
        return status_code >= 500 or status_code == 408


class WebhookDeliveryQueue:
    """Queue for webhook deliveries with retry logic."""

    def __init__(self):
        self.pending_events: dict[str, WebhookEvent] = {}
        self.delivery_log: list[WebhookDeliveryLog] = []
        self.dlq: list[tuple[WebhookEvent, WebhookEndpoint]] = []  # Dead-letter queue
        self.endpoints: dict[str, WebhookEndpoint] = {}

    async def register_endpoint(
        self,
        endpoint_id: str,
        tenant_id: str,
        url: str,
        webhook_secret: str,
        events: list[WebhookEventType],
    ) -> WebhookEndpoint:
        """Register webhook endpoint.

        Args:
            endpoint_id: Unique endpoint ID
            tenant_id: Tenant ID
            url: Webhook URL
            webhook_secret: Secret for signing
            events: List of event types to subscribe to

        Returns:
            WebhookEndpoint
        """
        endpoint = WebhookEndpoint(
            endpoint_id=endpoint_id,
            tenant_id=tenant_id,
            url=url,
            webhook_secret=webhook_secret,
            events=events,
        )
        self.endpoints[endpoint_id] = endpoint
        return endpoint

    async def queue_event(self, event: WebhookEvent):
        """Queue event for delivery.

        Args:
            event: WebhookEvent to deliver
        """
        event_id = f"{event.tenant_id}:{event.resource_id}:{int(time.time() * 1000)}"
        self.pending_events[event_id] = event

    async def process_deliveries(self):
        """Process pending webhook deliveries with retries."""
        now = datetime.utcnow()

        for endpoint_id, endpoint in self.endpoints.items():
            if not endpoint.active:
                continue

            for event_id, event in list(self.pending_events.items()):
                # Check if endpoint subscribes to this event type
                if event.event_type not in endpoint.events:
                    continue

                # Check if it's time to retry
                if event.next_retry and event.next_retry > now:
                    continue

                # Deliver webhook
                success, status_code = await self._deliver_webhook(event, endpoint)

                # Log delivery
                self.delivery_log.append(WebhookDeliveryLog(
                    event_id=event_id,
                    endpoint_id=endpoint_id,
                    attempt=event.attempt,
                    status_code=status_code,
                    success=success,
                    error=None if success else f"Status {status_code}",
                    timestamp=now,
                ))

                if success:
                    # Remove from pending
                    del self.pending_events[event_id]
                else:
                    # Check if should retry
                    if WebhookRetryPolicy.should_retry(event.attempt, status_code or 500):
                        # Schedule retry
                        event.attempt += 1
                        event.next_retry = WebhookRetryPolicy.get_next_retry_time(event.attempt)
                    else:
                        # Max retries exceeded, move to DLQ
                        self.dlq.append((event, endpoint))
                        del self.pending_events[event_id]

    async def _deliver_webhook(
        self,
        event: WebhookEvent,
        endpoint: WebhookEndpoint,
    ) -> tuple[bool, int | None]:
        """Deliver webhook to endpoint.

        Args:
            event: Event to deliver
            endpoint: Endpoint to deliver to

        Returns:
            (success: bool, status_code: Optional[int])
        """
        try:
            payload = event.to_json()
            signature = WebhookSignature.sign(payload, endpoint.webhook_secret)

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    endpoint.url,
                    content=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Triage-Event": event.event_type.value,
                        "X-Triage-Signature": signature,
                    },
                )
                return response.status_code == 200, response.status_code
        except Exception:
            return False, None

    async def replay_webhook(
        self,
        event_id: str,
        endpoint_id: str,
    ) -> bool:
        """Replay webhook to endpoint (admin operation).

        Args:
            event_id: Event to replay
            endpoint_id: Endpoint to replay to

        Returns:
            True if successful
        """
        if event_id not in self.pending_events:
            return False

        event = self.pending_events[event_id]
        if endpoint_id not in self.endpoints:
            return False

        endpoint = self.endpoints[endpoint_id]

        # Reset attempt counter
        event.attempt = 1
        event.next_retry = None

        success, _ = await self._deliver_webhook(event, endpoint)
        return success

    def get_dlq_events(self, tenant_id: str) -> list[tuple[WebhookEvent, WebhookEndpoint]]:
        """Get dead-lettered events for inspection.

        Args:
            tenant_id: Tenant ID

        Returns:
            List of (event, endpoint) tuples
        """
        return [(e, ep) for e, ep in self.dlq if e.tenant_id == tenant_id]
