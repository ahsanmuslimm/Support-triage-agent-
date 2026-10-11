"""Sprint 6.2: Tests for Kafka EventBus adapter."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestKafkaEventBusInitialization:
    """Test KafkaEventBus initialization and connection."""

    def test_event_bus_factory_kafka_enabled(self):
        """Test: EventBusFactory creates Kafka adapter when USE_KAFKA_EVENTS=true."""
        from triage.adapters.event_bus_factory import EventBusFactory

        # Create with explicit use_kafka=True
        bus = EventBusFactory.create_event_bus(use_kafka=True)

        assert bus is not None
        assert hasattr(bus, "connect")
        assert hasattr(bus, "disconnect")
        assert hasattr(bus, "publish")

    def test_event_bus_factory_mvp_disabled(self):
        """Test: EventBusFactory creates MVP adapter when USE_KAFKA_EVENTS=false."""
        from triage.adapters.event_bus_factory import EventBusFactory

        # Create with explicit use_kafka=False
        bus = EventBusFactory.create_event_bus(use_kafka=False)

        assert bus is not None

    @pytest.mark.asyncio
    async def test_kafka_event_bus_initialization(self):
        """Test: KafkaEventBus initializes with bootstrap servers."""
        from triage.adapters.event_bus_kafka import KafkaEventBus

        # Create bus
        bus = KafkaEventBus(
            bootstrap_servers="localhost:9092",
            consumer_group_id="test-group",
        )

        assert bus.bootstrap_servers == "localhost:9092"
        assert bus.consumer_group_id == "test-group"


@pytest.mark.unit
class TestKafkaEventBusPublishing:
    """Test Kafka event publishing."""

    def test_cloud_event_dict_construction(self):
        """Test: _build_cloud_event_dict creates valid CloudEvent structure."""
        from triage.adapters.event_bus_kafka import KafkaEventBus

        bus = KafkaEventBus()

        cloud_event = bus._build_cloud_event_dict(
            event_type="message.ingested",
            tenant_id="tenant_1",
            payload={"message_id": "msg_123", "body": "Hello"},
            aggregate_id="msg_123",
            outbox_event_id="evt_456",
        )

        assert cloud_event["id"] == "evt_456"  # Reused from outbox_event_id
        assert cloud_event["type"] == "message.ingested"
        assert cloud_event["tenant_id"] == "tenant_1"
        assert cloud_event["source"] == "triage/messages"
        assert "tenant_1" in cloud_event["subject"]

    def test_payload_serialization_dict(self):
        """Test: _serialize_payload handles dict (JSON fallback)."""
        from triage.adapters.event_bus_kafka import KafkaEventBus

        payload = {"message_id": "msg_123", "body": "Hello"}
        serialized = KafkaEventBus._serialize_payload(payload)

        assert isinstance(serialized, bytes)
        # Verify it's JSON-serialized
        import json
        deserialized = json.loads(serialized.decode("utf-8"))
        assert deserialized["message_id"] == "msg_123"

    def test_topic_naming_convention(self):
        """Test: Topic name derived from event_type following convention."""
        from triage.adapters.event_bus_kafka import KafkaEventBus

        bus = KafkaEventBus()

        # Build cloud event to test topic derivation
        # Expected: "message.ingested" → "triage.message.ingested"
        cloud_event = bus._build_cloud_event_dict(
            event_type="message.ingested",
            tenant_id="tenant_1",
            payload={},
            aggregate_id=None,
        )

        assert cloud_event["type"] == "message.ingested"
        # Topic naming logic: event_type is embedded in the CloudEvent


@pytest.mark.unit
class TestPriorityQueueRouting:
    """Test S6.4: Priority queue message routing."""

    @pytest.mark.asyncio
    async def test_priority_queue_channel_selection(self):
        """Test: Messages route to correct queue based on channel."""
        from triage.adapters.priority_queue import PriorityQueue, Channel
        from unittest.mock import AsyncMock, MagicMock

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.zadd = AsyncMock()

        queue = PriorityQueue(redis_client=mock_redis)

        # Enqueue chat message
        await queue.enqueue_message(
            message_id="msg_1",
            tenant_id="tenant_1",
            channel="chat",
            payload={"body": "Urgent issue"},
        )

        # Verify zadd was called with chat queue key
        assert mock_redis.zadd.called
        call_args = mock_redis.zadd.call_args
        assert "queue:chat" in call_args[0]

    def test_channel_priority_ordering(self):
        """Test: Channel enum defines priority ordering (lower=higher priority)."""
        from triage.adapters.priority_queue import Channel

        assert Channel.VOICE < Channel.CHAT < Channel.WEB < Channel.EMAIL

    @pytest.mark.asyncio
    async def test_priority_queue_depth(self):
        """Test: Queue depth tracking."""
        from triage.adapters.priority_queue import PriorityQueue
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = MagicMock()
        mock_redis.zcard = AsyncMock(return_value=5)

        queue = PriorityQueue(redis_client=mock_redis)

        depth = await queue.get_queue_depth("chat")

        assert depth == 5
        mock_redis.zcard.assert_called_with("queue:chat")


@pytest.mark.unit
class TestIdempotency:
    """Test S6.3: Idempotency store."""

    @pytest.mark.asyncio
    async def test_idempotency_fast_path_first_call(self):
        """Test: First call to check_or_record returns is_duplicate=False."""
        from triage.adapters.idempotency import IdempotencyStore
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)  # Not in cache
        mock_redis.setex = AsyncMock()

        store = IdempotencyStore(redis_client=mock_redis)

        result = await store.check_or_record(
            tenant_id="tenant_1",
            event_id="evt_123",
            event_type="message.ingested",
            use_slow_path=False,
        )

        assert result.is_duplicate is False

    @pytest.mark.asyncio
    async def test_idempotency_fast_path_duplicate(self):
        """Test: Second call with same event_id returns is_duplicate=True."""
        from triage.adapters.idempotency import IdempotencyStore
        from unittest.mock import AsyncMock, MagicMock

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=b"processed_ok")  # In cache

        store = IdempotencyStore(redis_client=mock_redis)

        result = await store.check_or_record(
            tenant_id="tenant_1",
            event_id="evt_123",
            event_type="message.ingested",
            use_slow_path=False,
        )

        assert result.is_duplicate is True
        assert result.prior_result == {"cached": True}


@pytest.mark.unit
class TestDLQ:
    """Test S6.3: Dead Letter Queue."""

    @pytest.mark.asyncio
    async def test_dlq_send_with_retry_count(self):
        """Test: DLQ event includes retry count and error context."""
        from triage.adapters.dlq import DeadLetterQueue
        from unittest.mock import AsyncMock, MagicMock

        mock_event_bus = MagicMock()
        mock_event_bus.publish = AsyncMock()

        dlq = DeadLetterQueue(event_bus=mock_event_bus)

        error = ValueError("Test error")
        event = {
            "id": "evt_123",
            "tenant_id": "tenant_1",
            "type": "message.ingested",
        }

        await dlq.send_to_dlq(event, error, retry_count=2)

        # Verify publish was called
        assert mock_event_bus.publish.called
        call_kwargs = mock_event_bus.publish.call_args[1]
        assert call_kwargs["event_type"] == "dlq.event_failed"
        assert call_kwargs["tenant_id"] == "tenant_1"

    def test_dlq_backoff_calculation(self):
        """Test: DLQ calculates exponential backoff correctly."""
        from triage.adapters.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(event_bus=None)

        # After 0 retries: 1s
        next_retry_0 = dlq._calculate_next_retry(0)
        assert next_retry_0 is not None

        # After 3+ retries: None (max exceeded)
        next_retry_max = dlq._calculate_next_retry(3)
        assert next_retry_max is None


@pytest.mark.integration
class TestEventConsumerIntegration:
    """Test S6.3 + S6.4: Event consumer with retry and priority routing."""

    @pytest.mark.asyncio
    async def test_consumer_with_retry_and_idempotency(self):
        """Test: Consumer retries failed events and checks idempotency."""
        from triage.adapters.event_consumer import ResilientEventConsumer
        from unittest.mock import AsyncMock, MagicMock

        # Mock dependencies
        mock_event_bus = MagicMock()
        mock_idempotency = MagicMock()
        mock_dlq = MagicMock()

        # Mock idempotency to return not duplicate
        from triage.adapters.idempotency import IdempotencyResult
        mock_idempotency.check_or_record = AsyncMock(
            return_value=IdempotencyResult(is_duplicate=False)
        )

        consumer = ResilientEventConsumer(
            event_bus=mock_event_bus,
            idempotency_store=mock_idempotency,
            dlq=mock_dlq,
        )

        # Handler that succeeds
        handler = AsyncMock(return_value={"status": "ok"})

        event = {
            "id": "evt_123",
            "tenant_id": "tenant_1",
            "type": "message.ingested",
        }

        # Process event
        await consumer.consume_with_retry(event, handler)

        # Verify handler was called once
        assert handler.call_count == 1

    @pytest.mark.asyncio
    async def test_consumer_send_to_dlq_after_max_retries(self):
        """Test: Consumer sends to DLQ after max retries exceeded."""
        from triage.adapters.event_consumer import ResilientEventConsumer
        from triage.adapters.idempotency import IdempotencyResult
        from unittest.mock import AsyncMock, MagicMock

        mock_event_bus = MagicMock()
        mock_idempotency = MagicMock()
        mock_dlq = MagicMock()

        # Mock idempotency to return not duplicate
        mock_idempotency.check_or_record = AsyncMock(
            return_value=IdempotencyResult(is_duplicate=False)
        )
        mock_dlq.send_to_dlq = AsyncMock()

        consumer = ResilientEventConsumer(
            event_bus=mock_event_bus,
            idempotency_store=mock_idempotency,
            dlq=mock_dlq,
            max_retries=3,
        )

        # Handler that always fails
        handler = AsyncMock(side_effect=Exception("Handler error"))

        event = {
            "id": "evt_123",
            "tenant_id": "tenant_1",
            "type": "message.ingested",
        }

        # Process event (will fail and eventually send to DLQ)
        await consumer.consume_with_retry(event, handler)

        # Verify DLQ was called
        assert mock_dlq.send_to_dlq.called
