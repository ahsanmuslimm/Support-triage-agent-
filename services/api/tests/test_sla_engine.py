"""Tests for SLA engine with temporal timers and breach prediction."""

from datetime import datetime, timedelta

import pytest
from triage.sla import (
    BusinessCalendar,
    SLAEngine,
    SLAEventType,
    SLAPolicy,
)


@pytest.fixture
def business_calendar():
    """Create test business calendar."""
    return BusinessCalendar.create_default(timezone="UTC")


@pytest.fixture
def sla_engine(business_calendar):
    """Create test SLA engine."""
    return SLAEngine(business_calendar)


class TestSLAPolicyMatching:
    """Test SLA policy matching."""

    def test_match_policy_by_priority(self, sla_engine):
        """Test matching policy by priority."""
        ticket_props = {"priority": "p0"}
        policy = sla_engine.match_policy(ticket_props)

        assert policy is not None
        assert policy.priority == "p0"
        assert policy.response_time_minutes == 15

    def test_match_all_priorities(self, sla_engine):
        """Test matching all priority levels."""
        for priority in ["p0", "p1", "p2", "p3"]:
            policy = sla_engine.match_policy({"priority": priority})
            assert policy is not None
            assert policy.priority == priority


class TestSLATimerCreation:
    """Test SLA timer creation and tracking."""

    def test_create_timer(self, sla_engine):
        """Test creating SLA timer."""
        ticket_props = {"priority": "p1"}
        timer = sla_engine.create_timer("ticket_123", ticket_props)

        assert timer is not None
        assert timer.ticket_id == "ticket_123"
        assert timer.policy.priority == "p1"
        assert timer.deadline > datetime.utcnow()

    def test_timer_deadline_calculation(self, sla_engine, business_calendar):
        """Test deadline is calculated with business hours."""
        ticket_props = {"priority": "p2"}
        timer = sla_engine.create_timer("ticket_456", ticket_props)

        # P2 = 240 minutes (4 hours) business time
        # Deadline should be > 4 hours away
        time_to_deadline = (timer.deadline - datetime.utcnow()).total_seconds() / 3600
        assert time_to_deadline > 3  # At least 3 hours (accounting for business hours)

    def test_warning_threshold(self, sla_engine):
        """Test warning threshold is at 75% of deadline."""
        ticket_props = {"priority": "p2"}
        timer = sla_engine.create_timer("ticket_789", ticket_props)

        # Warning should be at 75% of resolution time
        warning_offset = (timer.warning_threshold - timer.created_at).total_seconds() / 60
        deadline_offset = (timer.deadline - timer.created_at).total_seconds() / 60

        # Warning should be roughly 75% of deadline
        ratio = warning_offset / deadline_offset
        assert 0.7 < ratio < 0.8


class TestBusinessHoursCalculation:
    """Test business hours math for SLA."""

    def test_business_time_within_hours(self, business_calendar):
        """Test time calculation within business hours."""
        # 9 AM Monday
        start = datetime(2024, 1, 15, 9, 0)  # Monday
        end = datetime(2024, 1, 15, 10, 0)   # 1 hour later

        elapsed = business_calendar.calculate_business_time_elapsed(start, end)

        assert elapsed == timedelta(hours=1)

    def test_business_time_crosses_weekend(self, business_calendar):
        """Test time calculation across weekend."""
        # Friday 5 PM to Monday 9 AM (0 business hours)
        start = datetime(2024, 1, 12, 17, 0)  # Friday
        end = datetime(2024, 1, 15, 9, 0)      # Monday

        elapsed = business_calendar.calculate_business_time_elapsed(start, end)

        assert elapsed == timedelta(0)

    def test_deadline_with_holidays(self, business_calendar):
        """Test deadline calculation with holidays."""
        # Add holiday
        holiday = datetime(2024, 1, 15)  # Monday
        business_calendar.add_holiday(holiday)

        # Start Monday before business
        start = datetime(2024, 1, 15, 8, 0)

        # Calculate 8 business hours
        deadline = business_calendar.calculate_deadline(start, 480)  # 8 hours

        # Deadline should be Tuesday 5 PM (skipping Monday holiday)
        assert deadline.day == 16


class TestSLATimerState:
    """Test SLA timer state transitions."""

    def test_timer_pause_resume(self, sla_engine):
        """Test pausing and resuming timer."""
        timer = sla_engine.create_timer("ticket_pause", {"priority": "p1"})
        original_deadline = timer.deadline

        # Pause timer
        sla_engine.pause_timer(timer.timer_id)
        assert timer.paused_at is not None

        # Resume timer
        sla_engine.resume_timer(timer.timer_id)
        assert timer.paused_at is None
        # Deadline should have extended
        assert timer.deadline > original_deadline

    def test_timer_is_breached(self, sla_engine):
        """Test checking if timer is breached."""
        timer = sla_engine.create_timer("ticket_breach", {"priority": "p0"})

        # Newly created timer should not be breached
        assert not timer.is_breached()

        # Manually set deadline to past
        timer.deadline = datetime.utcnow() - timedelta(minutes=1)
        assert timer.is_breached()


class TestSLAEvents:
    """Test SLA event generation."""

    def test_warning_event_generation(self, sla_engine):
        """Test warning event is emitted at 75% threshold."""
        timer = sla_engine.create_timer("ticket_warn", {"priority": "p1"})

        # Manually advance to warning threshold
        timer.warning_threshold = datetime.utcnow() - timedelta(seconds=1)

        events = sla_engine.check_timers()

        warning_events = [e for e in events if e.event_type == SLAEventType.ESCALATION_WARNING]
        assert len(warning_events) > 0

    def test_breach_event_generation(self, sla_engine):
        """Test breach event is emitted at deadline."""
        timer = sla_engine.create_timer("ticket_breach_event", {"priority": "p0"})

        # Manually set deadline to past
        timer.deadline = datetime.utcnow() - timedelta(seconds=1)

        events = sla_engine.check_timers()

        breach_events = [e for e in events if e.event_type == SLAEventType.ESCALATION_BREACH]
        assert len(breach_events) > 0

    def test_events_not_duplicated(self, sla_engine):
        """Test warning/breach events only emitted once."""
        timer = sla_engine.create_timer("ticket_dup", {"priority": "p1"})
        timer.deadline = datetime.utcnow() - timedelta(seconds=1)

        # Check twice
        events1 = sla_engine.check_timers()
        events2 = sla_engine.check_timers()

        # Second check should have no events (already emitted)
        assert len([e for e in events2 if e.ticket_id == "ticket_dup"]) == 0


class TestDSTHandling:
    """Test Daylight Saving Time handling."""

    def test_dst_transition(self, business_calendar):
        """Test DST transition is handled correctly."""
        # This is a placeholder test; real implementation would need
        # timezone-aware datetime objects and proper DST handling

        # Verify business_calendar has timezone
        assert business_calendar.business_hours.timezone is not None


class TestMultiplePolicies:
    """Test custom SLA policies."""

    def test_add_custom_policy(self, sla_engine):
        """Test adding custom SLA policy."""
        custom_policy = SLAPolicy(
            name="Premium Support",
            priority="p2",
            category="billing",
            response_time_minutes=30,
            resolution_time_minutes=120,
        )

        sla_engine.add_policy(custom_policy)

        # Match should find the custom policy
        props = {"priority": "p2", "category": "billing"}
        policy = sla_engine.match_policy(props)

        assert policy.name == "Premium Support"
        assert policy.resolution_time_minutes == 120
