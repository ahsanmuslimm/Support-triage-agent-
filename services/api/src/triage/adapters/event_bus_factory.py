"""S6.2: Event bus factory for toggling between MVP (OutboxPoller) and production (Kafka)."""
import os

import structlog

log = structlog.get_logger(__name__)


class EventBusFactory:
    """Factory for instantiating EventBus adapter based on config.

    Design: Toggle between MVP (in-memory OutboxPoller) and production (Kafka)
    via environment variable USE_KAFKA_EVENTS.

    This enables gradual cutover from monolithic MVP to distributed event architecture.
    """

    @staticmethod
    def create_event_bus(use_kafka: bool | None = None) -> object:
        """Create appropriate event bus implementation.

        Args:
            use_kafka: If True, use Kafka adapter; if False, use MVP OutboxWriter.
                      If None, read from environment: USE_KAFKA_EVENTS (default: false)

        Returns:
            EventBus implementation (KafkaEventBus or OutboxWriter)

        Environment Variables:
            USE_KAFKA_EVENTS: "true" to enable Kafka (default: "false")
            KAFKA_BOOTSTRAP_SERVERS: Kafka brokers (default: "kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092")
        """
        if use_kafka is None:
            use_kafka = os.getenv("USE_KAFKA_EVENTS", "false").lower() == "true"

        if use_kafka:
            from .event_bus_kafka import KafkaEventBus

            kafka_servers = os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS",
                "kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092",
            )
            log.info("event_bus_kafka_enabled", bootstrap_servers=kafka_servers)
            return KafkaEventBus(bootstrap_servers=kafka_servers)
        else:
            # MVP: In-memory OutboxWriter (for backward compatibility)
            # In production sprint 3-5 implementation, this is located in triage.ingestion.outbox
            log.info("event_bus_mvp_enabled")
            # Return None for now; actual implementation uses triage.ingestion.outbox.OutboxWriter
            from triage.ingestion.outbox import OutboxWriter
            return OutboxWriter()
