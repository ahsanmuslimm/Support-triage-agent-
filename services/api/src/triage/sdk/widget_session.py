"""Widget session management and SSE streaming."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

import structlog

log = structlog.get_logger()


class WidgetSession:
    """Represents an active widget session for a customer."""

    def __init__(
        self,
        session_id: str,
        tenant_id: str,
        customer_id: str,
        widget_id: str,
    ) -> None:
        """Initialize widget session.

        Args:
            session_id: Unique session identifier.
            tenant_id: Tenant ID.
            customer_id: Customer ID.
            widget_id: Widget target element ID (e.g., '#chat-widget').
        """
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.widget_id = widget_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.is_active = True
        self.event_queue: list[dict[str, Any]] = []

    def record_activity(self) -> None:
        """Record user activity to track session lifetime."""
        self.last_activity = datetime.utcnow()

    def is_expired(self, ttl: timedelta = timedelta(hours=1)) -> bool:
        """Check if session is expired.

        Args:
            ttl: Time-to-live duration.

        Returns:
            bool: True if session is expired.
        """
        return datetime.utcnow() - self.last_activity > ttl

    def close(self) -> None:
        """Close the session."""
        self.is_active = False
        log.info(
            "session_closed",
            session_id=self.session_id,
            customer_id=self.customer_id,
            duration_seconds=(datetime.utcnow() - self.created_at).total_seconds(),
        )

    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Add event to stream queue.

        Args:
            event_type: Type of event (e.g., 'message', 'status').
            data: Event payload.
        """
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        }
        self.event_queue.append(event)
        self.record_activity()
        log.debug(
            "event_queued",
            session_id=self.session_id,
            event_type=event_type,
        )

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        """Stream events as Server-Sent Events.

        Yields:
            Dict[str, Any]: Event in SSE format.
        """
        try:
            last_event_id = 0
            while self.is_active:
                # Get new events
                if len(self.event_queue) > last_event_id:
                    event = self.event_queue[last_event_id]
                    last_event_id += 1

                    # Format as SSE
                    sse_event = {
                        "id": event["id"],
                        "event": event["type"],
                        "data": event["data"],
                        "timestamp": event["timestamp"],
                    }
                    yield sse_event
                else:
                    # Keep-alive ping
                    import asyncio
                    await asyncio.sleep(1)

                # Check if session expired
                if self.is_expired():
                    log.info("session_expired", session_id=self.session_id)
                    self.close()
                    break

        except Exception as e:
            log.error("stream_error", error=str(e), session_id=self.session_id)
            raise

    def to_dict(self) -> dict[str, Any]:
        """Serialize session to dictionary.

        Returns:
            Dict[str, Any]: Session data.
        """
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "customer_id": self.customer_id,
            "widget_id": self.widget_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "is_active": self.is_active,
            "event_count": len(self.event_queue),
        }


class SessionManager:
    """Manage widget sessions lifecycle."""

    def __init__(self, session_ttl: timedelta = timedelta(hours=1)) -> None:
        """Initialize session manager.

        Args:
            session_ttl: Time-to-live for inactive sessions.
        """
        self.session_ttl = session_ttl
        self.sessions: dict[str, WidgetSession] = {}  # session_id -> WidgetSession
        self.customer_sessions: dict[str, list[str]] = {}  # customer_id -> [session_ids]

    def create_session(
        self,
        tenant_id: str,
        customer_id: str,
        widget_id: str,
    ) -> WidgetSession:
        """Create a new widget session.

        Args:
            tenant_id: Tenant ID.
            customer_id: Customer ID.
            widget_id: Widget target element ID.

        Returns:
            WidgetSession: New session.
        """
        session_id = str(uuid.uuid4())
        session = WidgetSession(session_id, tenant_id, customer_id, widget_id)

        self.sessions[session_id] = session

        if customer_id not in self.customer_sessions:
            self.customer_sessions[customer_id] = []
        self.customer_sessions[customer_id].append(session_id)

        log.info(
            "session_created",
            session_id=session_id,
            customer_id=customer_id,
            tenant_id=tenant_id,
        )

        return session

    def get_session(self, session_id: str) -> WidgetSession | None:
        """Get session by ID.

        Args:
            session_id: Session ID.

        Returns:
            Optional[WidgetSession]: Session or None if not found.
        """
        session = self.sessions.get(session_id)
        if session and not session.is_expired(self.session_ttl):
            session.record_activity()
            return session
        elif session:
            self._remove_session(session_id)
        return None

    def get_customer_sessions(self, customer_id: str) -> list[WidgetSession]:
        """Get all sessions for a customer.

        Args:
            customer_id: Customer ID.

        Returns:
            list[WidgetSession]: Active sessions.
        """
        session_ids = self.customer_sessions.get(customer_id, [])
        active = []
        expired = []

        for session_id in session_ids:
            session = self.sessions.get(session_id)
            if session and not session.is_expired(self.session_ttl):
                active.append(session)
            else:
                expired.append(session_id)

        # Clean up expired
        for session_id in expired:
            self._remove_session(session_id)

        return active

    def close_session(self, session_id: str) -> bool:
        """Close a session.

        Args:
            session_id: Session ID.

        Returns:
            bool: True if session was closed.
        """
        session = self.sessions.get(session_id)
        if session:
            session.close()
            self._remove_session(session_id)
            return True
        return False

    def cleanup_expired(self) -> int:
        """Clean up all expired sessions.

        Returns:
            int: Number of sessions removed.
        """
        expired = [
            sid
            for sid, session in self.sessions.items()
            if session.is_expired(self.session_ttl)
        ]

        for session_id in expired:
            self._remove_session(session_id)

        if expired:
            log.info("sessions_cleaned", count=len(expired))

        return len(expired)

    def _remove_session(self, session_id: str) -> None:
        """Remove session from all registries.

        Args:
            session_id: Session ID.
        """
        session = self.sessions.pop(session_id, None)
        if session:
            customer_id = session.customer_id
            if customer_id in self.customer_sessions:
                self.customer_sessions[customer_id] = [
                    s for s in self.customer_sessions[customer_id] if s != session_id
                ]
                if not self.customer_sessions[customer_id]:
                    del self.customer_sessions[customer_id]

    def get_stats(self) -> dict[str, Any]:
        """Get session manager statistics.

        Returns:
            Dict[str, Any]: Statistics.
        """
        total_sessions = len(self.sessions)
        total_customers = len(self.customer_sessions)

        # Clean expired
        self.cleanup_expired()

        return {
            "total_sessions": total_sessions,
            "total_customers": total_customers,
            "session_ttl_minutes": int(self.session_ttl.total_seconds() / 60),
        }
