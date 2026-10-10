"""Unit tests for fake implementations."""

import pytest

from py_core.testing import FakeClock, FakeLLM, InMemoryEventBus


@pytest.mark.unit
async def test_fake_llm_returns_scripted_output() -> None:
    """Test that FakeLLM returns registered responses."""
    responses = {"test_prompt": "Hello, world!"}
    llm = FakeLLM(responses)

    result = await llm.complete("test_prompt")
    assert result == "Hello, world!"


@pytest.mark.unit
async def test_fake_llm_raises_on_unknown_prompt() -> None:
    """Test that FakeLLM raises KeyError on unknown prompt."""
    llm = FakeLLM({"registered": "response"})

    with pytest.raises(KeyError, match="Unknown prompt"):
        await llm.complete("unknown_prompt")


@pytest.mark.unit
async def test_fake_llm_records_calls() -> None:
    """Test that FakeLLM records all calls."""
    responses = {"prompt1": "response1"}
    llm = FakeLLM(responses)

    await llm.complete("prompt1", arg1="value1")
    await llm.complete("prompt1", arg2="value2")

    assert len(llm.calls) == 2
    assert llm.calls[0]["kwargs"]["arg1"] == "value1"
    assert llm.calls[1]["kwargs"]["arg2"] == "value2"


@pytest.mark.unit
async def test_fake_llm_reset() -> None:
    """Test that FakeLLM.reset() clears call log."""
    responses = {"prompt": "response"}
    llm = FakeLLM(responses)

    await llm.complete("prompt")
    assert len(llm.calls) == 1

    await llm.reset()
    assert len(llm.calls) == 0


@pytest.mark.unit
def test_fake_clock_returns_same_time() -> None:
    """Test that FakeClock returns same time on repeated calls."""
    clock = FakeClock()
    time1 = clock.now()
    time2 = clock.now()
    assert time1 == time2


@pytest.mark.unit
def test_fake_clock_advances_by_seconds() -> None:
    """Test that FakeClock.advance() changes time."""
    clock = FakeClock()
    time1 = clock.now()
    clock.advance(30)
    time2 = clock.now()

    assert (time2 - time1).total_seconds() == 30


@pytest.mark.unit
async def test_in_memory_event_bus_publishes_events() -> None:
    """Test that InMemoryEventBus stores events."""
    bus = InMemoryEventBus()

    await bus.publish("test_event", "tenant1", {"key": "value"})
    events = bus.published_events()

    assert len(events) == 1
    assert events[0]["event_type"] == "test_event"
    assert events[0]["payload"]["key"] == "value"


@pytest.mark.unit
async def test_in_memory_event_bus_filters_by_type() -> None:
    """Test that InMemoryEventBus filters events by type."""
    bus = InMemoryEventBus()

    await bus.publish("event_a", "tenant1", {})
    await bus.publish("event_b", "tenant1", {})
    await bus.publish("event_a", "tenant2", {})

    a_events = bus.published_events("event_a")
    assert len(a_events) == 2

    b_events = bus.published_events("event_b")
    assert len(b_events) == 1


@pytest.mark.unit
async def test_in_memory_event_bus_assert_published() -> None:
    """Test that InMemoryEventBus.assert_published() works."""
    bus = InMemoryEventBus()

    await bus.publish("order_created", "tenant1", {"order_id": "123", "amount": 100})

    bus.assert_published("order_created", {"order_id": "123"})


@pytest.mark.unit
async def test_in_memory_event_bus_assert_published_fails() -> None:
    """Test that InMemoryEventBus.assert_published() raises on mismatch."""
    bus = InMemoryEventBus()

    await bus.publish("order_created", "tenant1", {"order_id": "123"})

    with pytest.raises(AssertionError):
        bus.assert_published("order_created", {"order_id": "456"})


@pytest.mark.unit
async def test_in_memory_event_bus_reset() -> None:
    """Test that InMemoryEventBus.reset() clears events."""
    bus = InMemoryEventBus()

    await bus.publish("event", "tenant1", {})
    assert len(bus.published_events()) == 1

    bus.reset()
    assert len(bus.published_events()) == 0
