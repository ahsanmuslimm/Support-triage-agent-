"""Transactional outbox for event durability."""

import asyncio
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from ..models.events import OutboxEvent


class OutboxWriter:
    """Writes events to outbox table (transactionally with domain objects)."""

    def __init__(self, db_session=None):
        """Initialize outbox writer.

        Args:
            db_session: Database session for writing outbox events
        """
        self.db_session = db_session
        self._in_memory_events: List[OutboxEvent] = []  # Demo mode

    async def write_event(
        self,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> OutboxEvent:
        """Write event to outbox (atomically with domain transaction).

        In production, this method would:
        1. Begin a database transaction
        2. INSERT message into messages table
        3. INSERT outbox event into outbox_events table in the SAME transaction
        4. Commit both atomically
        5. Return OutboxEvent

        This ensures durability and prevents message loss on server crash.

        Args:
            tenant_id: Tenant ID
            aggregate_type: Type of aggregate (message, conversation, etc.)
            aggregate_id: ID of aggregate
            event_type: Event type string
            payload: Event payload

        Returns:
            OutboxEvent written
        """
        event = OutboxEvent(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )

        # TODO: Write to database in same transaction as domain object
        # In production:
        # async with db_session.begin() as transaction:
        #     # INSERT message first
        #     stmt = insert(messages_table).values(...)
        #     await transaction.execute(stmt)
        #     
        #     # INSERT outbox event in same transaction
        #     stmt = insert(outbox_events_table).values(...)
        #     await transaction.execute(stmt)
        #     # transaction.commit() happens automatically on context exit
        #
        # For now, store in-memory (will be lost on restart)
        self._in_memory_events.append(event)

        return event

    def get_unpublished_events(self, limit: int = 100) -> List[OutboxEvent]:
        """Get unpublished events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of unpublished events
        """
        return self._in_memory_events[:limit]

    def mark_published(self, event_id: str) -> None:
        """Mark event as published.

        Args:
            event_id: Event ID
        """
        # TODO: Update database
        pass


class OutboxPoller:
    """Background task that polls outbox and delivers events."""

    def __init__(
        self,
        outbox_writer: OutboxWriter,
        handlers: Optional[Dict[str, Callable]] = None,
        poll_interval: int = 1,
    ):
        """Initialize poller.

        Args:
            outbox_writer: OutboxWriter instance
            handlers: Dict of event_type -> handler function
            poll_interval: Polling interval in seconds
        """
        self.outbox_writer = outbox_writer
        self.handlers = handlers or {}
        self.poll_interval = poll_interval
        self._running = False

    async def start(self) -> None:
        """Start polling loop."""
        self._running = True
        while self._running:
            try:
                await self.poll_once()
            except Exception as e:
                print(f"Poller error: {e}")

            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """Stop polling loop."""
        self._running = False

    async def poll_once(self) -> None:
        """Poll and process one batch of events."""
        events = self.outbox_writer.get_unpublished_events()

        for event in events:
            try:
                # Find handler for event type
                handler = self.handlers.get(event.event_type)
                if handler:
                    await handler(event) if asyncio.iscoroutinefunction(handler) else handler(event)

                # Mark as published
                self.outbox_writer.mark_published(event.id)
            except Exception as e:
                print(f"Error processing event {event.id}: {e}")
                # TODO: Implement retry logic and dead-letter queue

    def register_handler(
        self,
        event_type: str,
        handler: Callable,
    ) -> None:
        """Register event handler.

        Args:
            event_type: Event type pattern (e.g., "message.ingested")
            handler: Async or sync callable
        """
        self.handlers[event_type] = handler
