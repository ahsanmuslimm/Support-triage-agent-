"""Fake implementations for testing."""

from datetime import datetime, timezone
from typing import Any, AsyncIterator


class FakeLLM:
    """Fake LLM for deterministic testing."""

    def __init__(self, scripted_responses: dict[str, Any] | None = None) -> None:
        """Initialize FakeLLM with scripted responses.

        Args:
            scripted_responses: Dict mapping prompt_name to response.
        """
        self.scripted_responses = scripted_responses or {}
        self.calls: list[dict[str, Any]] = []

    async def complete(self, prompt_name: str, **kwargs: Any) -> Any:
        """Return scripted response or raise KeyError.

        Args:
            prompt_name: Name of the prompt template.
            **kwargs: Additional arguments (recorded in call log).

        Returns:
            Scripted response.

        Raises:
            KeyError: If prompt_name is not registered.
        """
        if prompt_name not in self.scripted_responses:
            raise KeyError(
                f"Unknown prompt: {prompt_name}. Registered prompts: {list(self.scripted_responses.keys())}"
            )

        self.calls.append({"prompt": prompt_name, "kwargs": kwargs})
        return self.scripted_responses[prompt_name]

    async def stream(self, prompt_name: str, **kwargs: Any) -> AsyncIterator[str]:
        """Stream scripted response as strings.

        Args:
            prompt_name: Name of the prompt template.
            **kwargs: Additional arguments.

        Yields:
            Character chunks of the response.

        Raises:
            KeyError: If prompt_name is not registered.
        """
        if prompt_name not in self.scripted_responses:
            raise KeyError(
                f"Unknown prompt: {prompt_name}. Registered prompts: {list(self.scripted_responses.keys())}"
            )

        response = self.scripted_responses[prompt_name]
        self.calls.append({"prompt": prompt_name, "kwargs": kwargs, "stream": True})

        for chunk in response:
            yield chunk

    async def reset(self) -> None:
        """Clear call log."""
        self.calls = []


class FakeClock:
    """Fake clock for testing time-dependent code."""

    def __init__(self, start: datetime | None = None) -> None:
        """Initialize FakeClock.

        Args:
            start: Initial datetime; defaults to now.
        """
        self._current_time = start or datetime.now(timezone.utc)

    def now(self) -> datetime:
        """Return current frozen time.

        Returns:
            datetime: Current time.
        """
        return self._current_time

    def advance(self, seconds: float) -> None:
        """Advance time by seconds.

        Args:
            seconds: Seconds to advance.
        """
        from datetime import timedelta

        self._current_time += timedelta(seconds=seconds)


class InMemoryEventBus:
    """In-memory event bus for testing."""

    def __init__(self) -> None:
        """Initialize empty event bus."""
        self._events: list[dict[str, Any]] = []

    async def publish(self, event_type: str, tenant_id: str, payload: dict[str, Any]) -> None:
        """Publish an event.

        Args:
            event_type: Type of event.
            tenant_id: Tenant ID.
            payload: Event payload.
        """
        self._events.append({"event_type": event_type, "tenant_id": tenant_id, "payload": payload})

    def published_events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        """Get published events, optionally filtered by type.

        Args:
            event_type: Optional filter by event type.

        Returns:
            List of events.
        """
        if event_type is None:
            return self._events
        return [e for e in self._events if e["event_type"] == event_type]

    def assert_published(self, event_type: str, payload_subset: dict[str, Any]) -> None:
        """Assert that an event was published with matching payload.

        Args:
            event_type: Expected event type.
            payload_subset: Subset of payload that must match.

        Raises:
            AssertionError: If no matching event found.
        """
        for event in self.published_events(event_type):
            if all(event["payload"].get(k) == v for k, v in payload_subset.items()):
                return

        raise AssertionError(
            f"Event {event_type} with payload {payload_subset} not found. "
            f"Published events: {self.published_events(event_type)}"
        )

    def reset(self) -> None:
        """Clear event log."""
        self._events = []
