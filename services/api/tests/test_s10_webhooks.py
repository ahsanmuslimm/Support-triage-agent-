"""Tests for S10.3 - Outbound Webhooks."""

from datetime import datetime

import pytest
from triage.api.webhooks_s10 import (
    WebhookDeliveryQueue,
    WebhookEvent,
    WebhookEventType,
    WebhookRetryPolicy,
    WebhookSignature,
)


class TestWebhookSignature:
    """Test webhook signature generation and verification."""

    def test_sign_payload(self):
        """Test signing webhook payload."""
        payload = '{"event":"test"}'
        secret = "my_webhook_secret"

        signature = WebhookSignature.sign(payload, secret)

        assert isinstance(signature, str)
        assert len(signature) > 0

    def test_verify_valid_signature(self):
        """Test verifying valid signature."""
        payload = '{"event":"test"}'
        secret = "my_webhook_secret"

        signature = WebhookSignature.sign(payload, secret)
        valid = WebhookSignature.verify(payload, signature, secret)

        assert valid

    def test_verify_invalid_signature(self):
        """Test verifying invalid signature."""
        payload = '{"event":"test"}'
        secret = "my_webhook_secret"
        wrong_secret = "wrong_secret"

        signature = WebhookSignature.sign(payload, secret)
        valid = WebhookSignature.verify(payload, signature, wrong_secret)

        assert not valid

    def test_signature_tampering_detected(self):
        """Test tampering is detected."""
        payload = '{"event":"test"}'
        secret = "my_webhook_secret"

        signature = WebhookSignature.sign(payload, secret)
        tampered_payload = '{"event":"tampered"}'
        valid = WebhookSignature.verify(tampered_payload, signature, secret)

        assert not valid


class TestRetryPolicy:
    """Test webhook retry policy."""

    def test_retry_intervals(self):
        """Test retry interval progression."""
        assert WebhookRetryPolicy.RETRY_INTERVALS == [1, 10, 100, 1000]
        assert WebhookRetryPolicy.MAX_ATTEMPTS == 4

    def test_get_next_retry_time(self):
        """Test computing next retry time."""
        base = datetime.utcnow()

        # Attempt 0 (after first failed request) -> retry after 1s
        next_time = WebhookRetryPolicy.get_next_retry_time(0, base)
        assert next_time is not None
        delay = (next_time - base).total_seconds()
        assert delay >= 0.9 and delay <= 1.1  # Allow some tolerance

        # Attempt 1 (after second failed request) -> retry after 10s
        next_time = WebhookRetryPolicy.get_next_retry_time(1, base)
        delay = (next_time - base).total_seconds()
        assert delay >= 9.9 and delay <= 10.1

    def test_max_retries_exceeded(self):
        """Test max retries returns None."""
        next_time = WebhookRetryPolicy.get_next_retry_time(5)
        assert next_time is None

    def test_should_retry_5xx(self):
        """Test 5xx errors trigger retry."""
        assert WebhookRetryPolicy.should_retry(1, 500)
        assert WebhookRetryPolicy.should_retry(1, 503)

    def test_should_not_retry_4xx(self):
        """Test 4xx errors don't retry."""
        assert not WebhookRetryPolicy.should_retry(1, 400)
        assert not WebhookRetryPolicy.should_retry(1, 404)

    def test_should_not_retry_max_attempts(self):
        """Test max attempts stops retry."""
        assert not WebhookRetryPolicy.should_retry(4, 500)


class TestWebhookEvent:
    """Test webhook event creation and serialization."""

    def test_create_event(self):
        """Test creating webhook event."""
        event = WebhookEvent(
            event_type=WebhookEventType.MESSAGE_RECEIVED,
            tenant_id="tenant_1",
            resource_id="msg_123",
            timestamp=datetime.utcnow(),
            data={"body": "test message"},
        )

        assert event.event_type == WebhookEventType.MESSAGE_RECEIVED
        assert event.attempt == 1

    def test_event_to_json(self):
        """Test event JSON serialization."""
        now = datetime.utcnow()
        event = WebhookEvent(
            event_type=WebhookEventType.ESCALATION_TRIGGERED,
            tenant_id="tenant_2",
            resource_id="conv_xyz",
            timestamp=now,
            data={"reason": "sentiment_spike"},
        )

        json_str = event.to_json()
        assert "escalation.triggered" in json_str
        assert "tenant_2" in json_str


class TestWebhookDeliveryQueue:
    """Test webhook delivery queue."""

    @pytest.mark.asyncio
    async def test_register_endpoint(self):
        """Test registering webhook endpoint."""
        queue = WebhookDeliveryQueue()

        endpoint = await queue.register_endpoint(
            endpoint_id="ep_123",
            tenant_id="tenant_1",
            url="https://example.com/webhook",
            webhook_secret="secret123",
            events=[WebhookEventType.MESSAGE_RECEIVED],
        )

        assert endpoint.endpoint_id == "ep_123"
        assert endpoint.active

    @pytest.mark.asyncio
    async def test_queue_event(self):
        """Test queueing event."""
        queue = WebhookDeliveryQueue()

        event = WebhookEvent(
            event_type=WebhookEventType.CONVERSATION_CREATED,
            tenant_id="tenant_1",
            resource_id="conv_123",
            timestamp=datetime.utcnow(),
            data={"customer_id": "cust_1"},
        )

        await queue.queue_event(event)

        assert len(queue.pending_events) == 1

    @pytest.mark.asyncio
    async def test_get_dlq_events(self):
        """Test getting dead-letter queue events."""
        queue = WebhookDeliveryQueue()

        # Create endpoint
        await queue.register_endpoint(
            "ep_test",
            "tenant_1",
            "https://example.com/webhook",
            "secret",
            [WebhookEventType.MESSAGE_RECEIVED],
        )

        # Create event
        event = WebhookEvent(
            event_type=WebhookEventType.MESSAGE_RECEIVED,
            tenant_id="tenant_1",
            resource_id="msg_123",
            timestamp=datetime.utcnow(),
            data={},
        )

        endpoint = queue.endpoints["ep_test"]

        # Manually add to DLQ
        queue.dlq.append((event, endpoint))

        dlq_events = queue.get_dlq_events("tenant_1")
        assert len(dlq_events) == 1
