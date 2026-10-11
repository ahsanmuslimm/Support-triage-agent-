"""SLA management engine with temporal timers and breach prediction."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import structlog
import uuid

from triage.sla.calendar import BusinessCalendar

log = structlog.get_logger()


class SLAEventType(str, Enum):
    """SLA event types."""

    ESCALATION_WARNING = "escalation_warning"
    ESCALATION_BREACH = "escalation_breach"
    TIMER_CREATED = "timer_created"
    TIMER_CANCELLED = "timer_cancelled"
    TIMER_PAUSED = "timer_paused"
    TIMER_RESUMED = "timer_resumed"


@dataclass
class SLAEvent:
    """SLA event emitted for tracking."""

    event_type: SLAEventType
    """Event type."""

    ticket_id: str
    """Associated ticket ID."""

    timer_id: str
    """Associated timer ID."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique event ID."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    """Event timestamp."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata."""


@dataclass
class SLAPolicy:
    """SLA policy definition."""

    name: str
    """Policy name (e.g., 'P0 Premium')."""

    priority: str
    """Ticket priority this policy applies to."""

    category: Optional[str] = None
    """Ticket category (optional filter)."""

    segment: Optional[str] = None
    """Customer segment (optional filter)."""

    response_time_minutes: int = 60
    """Time to first response in business minutes."""

    resolution_time_minutes: int = 480
    """Time to resolution in business minutes."""

    warning_threshold_percent: float = 75.0
    """Trigger warning at this % of deadline (default 75%)."""


@dataclass
class SLATimer:
    """Timer tracking SLA deadline for a ticket."""

    ticket_id: str
    """Associated ticket ID."""

    policy: SLAPolicy
    """SLA policy."""

    deadline: datetime
    """Calculated deadline."""

    warning_threshold: datetime
    """Warning threshold (75% of deadline)."""

    timer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """Unique timer ID."""

    created_at: datetime = field(default_factory=datetime.utcnow)
    """Timer creation time."""

    paused_at: Optional[datetime] = None
    """Time when timer was paused (None if running)."""

    total_paused_duration: timedelta = field(default_factory=lambda: timedelta(0))
    """Total time the timer has been paused."""

    warning_emitted: bool = False
    """Whether warning event has been emitted."""

    breach_emitted: bool = False
    """Whether breach event has been emitted."""

    def is_breached(self) -> bool:
        """Check if SLA is breached.

        Returns:
            bool: True if deadline has passed.
        """
        if self.paused_at:
            # Timer is paused, not breached yet
            return False
        return datetime.utcnow() > self.deadline

    def is_warning_needed(self) -> bool:
        """Check if warning should be emitted.

        Returns:
            bool: True if at warning threshold and not yet emitted.
        """
        if self.warning_emitted or self.paused_at:
            return False
        return datetime.utcnow() >= self.warning_threshold

    def get_time_remaining(self) -> timedelta:
        """Get remaining time until breach.

        Returns:
            timedelta: Time remaining (negative if breached).
        """
        if self.paused_at:
            return self.deadline - self.paused_at
        return self.deadline - datetime.utcnow()

    def pause(self) -> None:
        """Pause the timer."""
        if not self.paused_at:
            self.paused_at = datetime.utcnow()

    def resume(self) -> None:
        """Resume the timer, adjusting deadline."""
        if self.paused_at:
            pause_duration = datetime.utcnow() - self.paused_at
            self.total_paused_duration += pause_duration
            self.deadline += pause_duration
            self.warning_threshold += pause_duration
            self.paused_at = None


class SLAEngine:
    """Engine managing SLA policies, timers, and breach events."""

    def __init__(self, business_calendar: BusinessCalendar) -> None:
        """Initialize SLA engine.

        Args:
            business_calendar: Business hours calendar.
        """
        self.business_calendar = business_calendar
        self.policies: Dict[str, SLAPolicy] = {}  # policy_name -> SLAPolicy
        self.timers: Dict[str, SLATimer] = {}  # timer_id -> SLATimer
        self.events: List[SLAEvent] = []  # Event log
        self._setup_default_policies()

    def _setup_default_policies(self) -> None:
        """Setup default SLA policies."""
        policies = [
            SLAPolicy(
                name="P0 Critical",
                priority="p0",
                response_time_minutes=15,
                resolution_time_minutes=60,
            ),
            SLAPolicy(
                name="P1 High",
                priority="p1",
                response_time_minutes=60,
                resolution_time_minutes=240,
            ),
            SLAPolicy(
                name="P2 Medium",
                priority="p2",
                response_time_minutes=240,
                resolution_time_minutes=1440,
            ),
            SLAPolicy(
                name="P3 Low",
                priority="p3",
                response_time_minutes=1440,
                resolution_time_minutes=5760,
            ),
        ]

        for policy in policies:
            self.add_policy(policy)

    def add_policy(self, policy: SLAPolicy) -> None:
        """Add SLA policy.

        Args:
            policy: SLA policy.
        """
        self.policies[policy.name] = policy
        log.info("policy_added", name=policy.name, priority=policy.priority)

    def match_policy(self, ticket_properties: Dict[str, Any]) -> Optional[SLAPolicy]:
        """Find matching SLA policy for ticket.

        Args:
            ticket_properties: Ticket properties (priority, category, segment).

        Returns:
            Optional[SLAPolicy]: Matching policy or None.
        """
        priority = ticket_properties.get("priority", "p2").lower()
        category = ticket_properties.get("category")
        segment = ticket_properties.get("segment")

        # Find best match: exact match preferred over partial
        for policy in self.policies.values():
            if (
                policy.priority == priority
                and (policy.category is None or policy.category == category)
                and (policy.segment is None or policy.segment == segment)
            ):
                return policy

        # Fallback: match by priority only
        for policy in self.policies.values():
            if policy.priority == priority:
                return policy

        return None

    def create_timer(
        self,
        ticket_id: str,
        ticket_properties: Dict[str, Any],
    ) -> Optional[SLATimer]:
        """Create SLA timer for ticket.

        Args:
            ticket_id: Ticket ID.
            ticket_properties: Ticket properties.

        Returns:
            Optional[SLATimer]: Timer or None if policy not found.
        """
        policy = self.match_policy(ticket_properties)
        if not policy:
            log.warning("policy_not_found", ticket_id=ticket_id)
            return None

        now = datetime.utcnow()
        deadline = self.business_calendar.calculate_deadline(
            now,
            policy.resolution_time_minutes,
        )
        warning_threshold = self.business_calendar.calculate_deadline(
            now,
            int(policy.resolution_time_minutes * (policy.warning_threshold_percent / 100.0)),
        )

        timer = SLATimer(
            ticket_id=ticket_id,
            policy=policy,
            deadline=deadline,
            warning_threshold=warning_threshold,
        )

        self.timers[timer.timer_id] = timer

        self.events.append(
            SLAEvent(
                event_type=SLAEventType.TIMER_CREATED,
                ticket_id=ticket_id,
                timer_id=timer.timer_id,
                metadata={
                    "policy": policy.name,
                    "deadline": deadline.isoformat(),
                    "warning_at": warning_threshold.isoformat(),
                },
            )
        )

        log.info(
            "timer_created",
            timer_id=timer.timer_id,
            ticket_id=ticket_id,
            policy=policy.name,
        )

        return timer

    def get_timer(self, timer_id: str) -> Optional[SLATimer]:
        """Get timer by ID.

        Args:
            timer_id: Timer ID.

        Returns:
            Optional[SLATimer]: Timer or None.
        """
        return self.timers.get(timer_id)

    def pause_timer(self, timer_id: str) -> bool:
        """Pause a timer.

        Args:
            timer_id: Timer ID.

        Returns:
            bool: True if paused successfully.
        """
        timer = self.get_timer(timer_id)
        if timer:
            timer.pause()
            self.events.append(
                SLAEvent(
                    event_type=SLAEventType.TIMER_PAUSED,
                    ticket_id=timer.ticket_id,
                    timer_id=timer_id,
                )
            )
            log.info("timer_paused", timer_id=timer_id)
            return True
        return False

    def resume_timer(self, timer_id: str) -> bool:
        """Resume a paused timer.

        Args:
            timer_id: Timer ID.

        Returns:
            bool: True if resumed successfully.
        """
        timer = self.get_timer(timer_id)
        if timer:
            timer.resume()
            self.events.append(
                SLAEvent(
                    event_type=SLAEventType.TIMER_RESUMED,
                    ticket_id=timer.ticket_id,
                    timer_id=timer_id,
                )
            )
            log.info("timer_resumed", timer_id=timer_id)
            return True
        return False

    def check_timers(self) -> List[SLAEvent]:
        """Check all active timers for warnings and breaches.

        Returns:
            List[SLAEvent]: New events from this check.
        """
        new_events = []

        for timer in self.timers.values():
            # Check warning
            if timer.is_warning_needed():
                timer.warning_emitted = True
                event = SLAEvent(
                    event_type=SLAEventType.ESCALATION_WARNING,
                    ticket_id=timer.ticket_id,
                    timer_id=timer.timer_id,
                    metadata={
                        "time_remaining_minutes": int(
                            timer.get_time_remaining().total_seconds() / 60
                        ),
                        "policy": timer.policy.name,
                    },
                )
                self.events.append(event)
                new_events.append(event)
                log.warning(
                    "sla_warning",
                    timer_id=timer.timer_id,
                    ticket_id=timer.ticket_id,
                )

            # Check breach
            if timer.is_breached() and not timer.breach_emitted:
                timer.breach_emitted = True
                event = SLAEvent(
                    event_type=SLAEventType.ESCALATION_BREACH,
                    ticket_id=timer.ticket_id,
                    timer_id=timer.timer_id,
                    metadata={
                        "policy": timer.policy.name,
                        "deadline": timer.deadline.isoformat(),
                    },
                )
                self.events.append(event)
                new_events.append(event)
                log.error(
                    "sla_breach",
                    timer_id=timer.timer_id,
                    ticket_id=timer.ticket_id,
                )

        return new_events

    def get_events(self, ticket_id: Optional[str] = None) -> List[SLAEvent]:
        """Get SLA events.

        Args:
            ticket_id: Optional filter by ticket ID.

        Returns:
            List[SLAEvent]: Events.
        """
        if ticket_id:
            return [e for e in self.events if e.ticket_id == ticket_id]
        return self.events.copy()
