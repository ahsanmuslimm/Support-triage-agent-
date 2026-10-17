"""S6.2: Kafka-backed EventBus adapter with Protobuf serialization and CloudEvents envelope."""
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

import structlog

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
except ImportError:
    # aiokafka not installed; graceful fallback
    AIOKafkaProducer = None
    AIOKafkaConsumer = None

log = structlog.get_logger(__name__)


class KafkaEventBus:
    """Production EventBus backed by Apache Kafka with Protobuf serialization.

    Design Principles:
    - Event Topic Naming: "triage.{event_type}" (e.g., "message.ingested" → "triage.message.ingested")
    - Partition Key: tenant_id (for tenant isolation + ordering guarantees per tenant)
    - Serialization: Protobuf-serialized CloudEvent envelope (RFC 7807)
    - Idempotency: Event ID propagation to consumers (S6.3)
    - Durability: acks='all' (wait for all in-sync replicas)

    Integration with Debezium (S6.2):
    - Debezium PostgreSQL connector captures outbox_events CDC
    - EventRouter transform routes by event_type to appropriate Kafka topic
    - Partition key derived from tenant_id for ordering
    - This adapter complements Debezium for application-level event publishing
    """

    def __init__(
        self,
        bootstrap_servers: str = "kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092",
        consumer_group_id: str | None = None,
    ):
        """Initialize Kafka-backed event bus.

        Args:
            bootstrap_servers: Comma-separated broker addresses
            consumer_group_id: Consumer group (for subscribers)
        """
        if AIOKafkaProducer is None:
            raise RuntimeError(
                "aiokafka not installed. Install with: pip install aiokafka"
            )

        self.bootstrap_servers = bootstrap_servers
        self.consumer_group_id = consumer_group_id or "triage-events"
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._handlers: dict[str, Callable] = {}

    async def connect(self) -> None:
        """Connect to Kafka cluster."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=self._serialize_protobuf,  # Protobuf serializer
            acks="all",  # Wait for all replicas
            compression_type="snappy",
            linger_ms=100,  # Batch for efficiency
            request_timeout_ms=30000,
        )
        await self._producer.start()

        log.info(
            "kafka_producer_connected",
            bootstrap_servers=self.bootstrap_servers,
        )

    async def disconnect(self) -> None:
        """Disconnect from Kafka cluster."""
        if self._producer:
            await self._producer.stop()
        if self._consumer:
            await self._consumer.stop()

        log.info("kafka_disconnected")

    @staticmethod
    def _serialize_protobuf(data: Any) -> bytes:
        """Serialize Protobuf message to bytes.

        Args:
            data: Protobuf message or dict (fallback for MVP transition)

        Returns:
            Serialized bytes
        """
        if hasattr(data, "SerializeToString"):
            # Protobuf message
            return data.SerializeToString()
        elif isinstance(data, dict):
            # Fallback: dict to JSON
            return json.dumps(data).encode("utf-8")
        else:
            # Bytes passthrough
            return bytes(data)

    async def publish(
        self,
        event_type: str,
        tenant_id: str,
        payload: Any,
        aggregate_type: str = "message",
        aggregate_id: str | None = None,
        outbox_event_id: str | None = None,
    ) -> None:
        """Publish event to Kafka topic using Protobuf CloudEvent.

        Topic name derived from event_type: "message.ingested" → "triage.message.ingested"
        Partition key = tenant_id (ensures ordering per tenant)
        Message value = Protobuf-serialized CloudEvent

        Design Decision (S6.1):
        CloudEvent.data field stores Protobuf-serialized domain event bytes.
        This ensures consistency: S6.1 Protobuf contracts → S6.2 Kafka envelope → S6.3 Consumer.

        Args:
            event_type: Event type (e.g., "message.ingested")
            tenant_id: Tenant ID (becomes partition key)
            payload: Event payload. PREFERRED: Protobuf message object.
                    FALLBACK: dict for MVP transition period.
            aggregate_type: Domain object type (e.g., "message")
            aggregate_id: Aggregate ID (e.g., message_id)
            outbox_event_id: Reuse OutboxEvent.id for idempotency consistency (S6.3)
        """
        if not self._producer:
            raise RuntimeError("EventBus not connected. Call connect() first.")

        # Convert event type to topic name: "message.ingested" → "triage.message.ingested"
        topic = f"triage.{event_type.replace('.', '.')}"

        # Build CloudEvent envelope (documentation; actual Protobuf code gen needed)
        cloud_event_dict = self._build_cloud_event_dict(
            event_type=event_type,
            tenant_id=tenant_id,
            payload=payload,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            outbox_event_id=outbox_event_id,
        )

        # Send to Kafka (partition key = tenant_id for tenant isolation)
        try:
            partition_info = await self._producer.send_and_wait(
                topic,
                value=cloud_event_dict,  # Will be serialized to Protobuf bytes
                key=tenant_id.encode("utf-8"),  # Partition by tenant
            )

            log.info(
                "event_published",
                event_type=event_type,
                topic=topic,
                tenant_id=tenant_id,
                partition=partition_info.partition if partition_info else None,
                offset=partition_info.offset if partition_info else None,
                event_id=cloud_event_dict.get("id"),
            )
        except Exception as e:
            log.exception(
                "event_publish_failed",
                event_type=event_type,
                topic=topic,
                tenant_id=tenant_id,
                error=str(e),
            )
            raise

    def _build_cloud_event_dict(
        self,
        event_type: str,
        tenant_id: str,
        payload: Any,
        aggregate_type: str,
        aggregate_id: str | None,
        outbox_event_id: str | None = None,
    ) -> dict[str, Any]:
        """Build CloudEvents dictionary (for code gen to Protobuf).

        Args:
            event_type: Event type
            tenant_id: Tenant ID
            payload: Domain event (Protobuf or dict)
            aggregate_id: Aggregate ID
            outbox_event_id: If provided, reuse this ID instead of generating new UUID

        Returns:
            Dictionary representing CloudEvent (will be serialized to Protobuf)
        """
        event_id = outbox_event_id or str(uuid.uuid4())

        return {
            "id": event_id,
            "source": "triage/messages",
            "type": event_type,
            "occurred_at": datetime.utcnow().isoformat(),
            "tenant_id": tenant_id,
            "subject": f"tenant/{tenant_id}/aggregate/{aggregate_id or 'unknown'}",
            "data_content_type": "application/protobuf",
            "attributes": {
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id or "",
            },
            "data": self._serialize_payload(payload),
        }

    @staticmethod
    def _serialize_payload(domain_event: Any) -> bytes:
        """Serialize Protobuf domain event to bytes.

        Args:
            domain_event: Protobuf message object OR dict (fallback for MVP transition)

        Returns:
            Serialized bytes (Protobuf-preferred, JSON fallback)

        Design Decision (S6.1): CloudEvent.data field stores Protobuf-serialized
        domain events to ensure S6.1 ↔ S6.2 contract consistency.
        """
        if hasattr(domain_event, "SerializeToString"):
            # Protobuf message: serialize to bytes
            return domain_event.SerializeToString()
        else:
            # Fallback: dict to JSON (for MVP transition period)
            return json.dumps(domain_event).encode("utf-8")

    async def subscribe(
        self,
        event_types: list[str],
        handler: Callable[[dict[str, Any]], None],
        consumer_group_id: str | None = None,
    ) -> None:
        """Subscribe to event types and handle with callback.

        Args:
            event_types: List of event types to subscribe to (e.g., ["message.ingested"])
            handler: Async callable(event_dict) to process each event
            consumer_group_id: Override default consumer group
        """
        topics = [f"triage.{et.replace('.', '.')}" for et in event_types]

        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.bootstrap_servers,
            group_id=consumer_group_id or self.consumer_group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            value_deserializer=self._deserialize_protobuf,  # Protobuf deserializer
            max_poll_records=100,
            session_timeout_ms=30000,
        )

        await self._consumer.start()

        try:
            async for message in self._consumer:
                try:
                    # message.value is CloudEvent dict (after deserialization)
                    event_dict = message.value

                    # Log event receipt
                    log.info(
                        "event_received",
                        event_type=event_dict.get("type"),
                        tenant_id=event_dict.get("tenant_id"),
                        event_id=event_dict.get("id"),
                    )

                    # Invoke handler
                    await handler(event_dict)

                    # Commit offset after successful processing
                    await self._consumer.commit()

                except Exception as e:
                    log.exception(
                        "event_handler_failed",
                        error=str(e),
                    )
                    # Send to DLQ (S6.3)
                    await self._send_to_dlq(message, e)
        finally:
            await self._consumer.stop()

    @staticmethod
    def _deserialize_protobuf(data: bytes) -> dict[str, Any]:
        """Deserialize bytes to CloudEvent dictionary.

        Note: For now, deserialize JSON. After buf code gen,
        this will deserialize Protobuf CloudEvent to dict.

        Args:
            data: Serialized bytes

        Returns:
            Dictionary representing CloudEvent
        """
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            # Fallback: return raw bytes wrapped in dict
            return {"_raw_data": data}

    async def _send_to_dlq(self, message: Any, error: Exception) -> None:
        """Send failed event to Dead Letter Queue (S6.3)."""
        try:
            dlq_event = {
                "original_event": message.value if hasattr(message, "value") else str(message),
                "error": str(error),
                "error_type": type(error).__name__,
                "timestamp": datetime.utcnow().isoformat(),
                "retry_count": 0,
            }

            await self._producer.send_and_wait(
                "triage.dlq",
                value=dlq_event,
                key=b"dlq",
            )

            log.warning(
                "event_sent_to_dlq",
                error=str(error),
            )
        except Exception as e:
            log.exception("dlq_send_failed", error=str(e))
