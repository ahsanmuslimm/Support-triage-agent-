"""Business hours calendar for SLA calculations."""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

import structlog

log = structlog.get_logger()


@dataclass
class BusinessHours:
    """Business hours configuration."""

    start_time: time = field(default_factory=lambda: time(9, 0))
    """Start of business day (e.g., 09:00)."""

    end_time: time = field(default_factory=lambda: time(17, 0))
    """End of business day (e.g., 17:00)."""

    working_days: set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})
    """Working days: 0=Monday, 6=Sunday."""

    timezone: str = "UTC"
    """Timezone name."""


class BusinessCalendar:
    """Business hours calendar with DST and holiday support."""

    def __init__(
        self,
        business_hours: BusinessHours,
        holidays: set[datetime] | None = None,
    ) -> None:
        """Initialize business calendar.

        Args:
            business_hours: Business hours configuration.
            holidays: Set of holiday dates (datetime objects, time portion ignored).
        """
        self.business_hours = business_hours
        self.holidays = holidays or set()

    def is_business_time(self, dt: datetime) -> bool:
        """Check if datetime is during business hours.

        Args:
            dt: Datetime to check.

        Returns:
            bool: True if during business hours.
        """
        # Check if weekday is working day
        if dt.weekday() not in self.business_hours.working_days:
            return False

        # Check if date is holiday
        date_only = datetime(dt.year, dt.month, dt.day)
        if date_only in self.holidays:
            return False

        # Check if time is within business hours
        if dt.time() < self.business_hours.start_time:
            return False
        if dt.time() >= self.business_hours.end_time:
            return False

        return True

    def calculate_business_time_elapsed(self, start: datetime, end: datetime) -> timedelta:
        """Calculate elapsed business time between two datetimes.

        Args:
            start: Start datetime.
            end: End datetime.

        Returns:
            timedelta: Elapsed business time.
        """
        elapsed = timedelta(0)
        current = start

        while current < end:
            if self.is_business_time(current):
                # Add 1 minute of business time
                elapsed += timedelta(minutes=1)
                current += timedelta(minutes=1)
            else:
                # Skip to next business time
                current = self._next_business_time(current)

        return elapsed

    def calculate_deadline(self, start: datetime, business_minutes: int) -> datetime:
        """Calculate deadline after N business minutes.

        Args:
            start: Start datetime.
            business_minutes: Number of business minutes.

        Returns:
            datetime: Deadline datetime.
        """
        elapsed = timedelta(0)
        current = start
        target = timedelta(minutes=business_minutes)

        while elapsed < target:
            if self.is_business_time(current):
                # Add 1 minute
                elapsed += timedelta(minutes=1)
                current += timedelta(minutes=1)
            else:
                # Skip to next business time
                current = self._next_business_time(current)

        return current

    def _next_business_time(self, dt: datetime) -> datetime:
        """Find next business time after given datetime.

        Args:
            dt: Reference datetime.

        Returns:
            datetime: Next business time.
        """
        # If during business hours, stay at current time
        if self.is_business_time(dt):
            return dt

        # If before business start today and today is working day
        if (
            dt.weekday() in self.business_hours.working_days
            and dt.time() < self.business_hours.start_time
        ):
            return dt.replace(
                hour=self.business_hours.start_time.hour,
                minute=self.business_hours.start_time.minute,
                second=0,
                microsecond=0,
            )

        # Find next working day
        next_dt = dt + timedelta(days=1)
        next_dt = next_dt.replace(
            hour=self.business_hours.start_time.hour,
            minute=self.business_hours.start_time.minute,
            second=0,
            microsecond=0,
        )

        while not self.is_business_time(next_dt):
            next_dt += timedelta(days=1)

        return next_dt

    def add_holiday(self, dt: datetime) -> None:
        """Add a holiday.

        Args:
            dt: Holiday date.
        """
        date_only = datetime(dt.year, dt.month, dt.day)
        self.holidays.add(date_only)
        log.info("holiday_added", date=date_only.isoformat())

    def remove_holiday(self, dt: datetime) -> None:
        """Remove a holiday.

        Args:
            dt: Holiday date.
        """
        date_only = datetime(dt.year, dt.month, dt.day)
        self.holidays.discard(date_only)
        log.info("holiday_removed", date=date_only.isoformat())

    @staticmethod
    def create_default(timezone: str = "UTC") -> "BusinessCalendar":
        """Create calendar with default business hours (9-5, Mon-Fri).

        Args:
            timezone: Timezone name.

        Returns:
            BusinessCalendar: Default calendar.
        """
        business_hours = BusinessHours(
            start_time=time(9, 0),
            end_time=time(17, 0),
            working_days={0, 1, 2, 3, 4},  # Mon-Fri
            timezone=timezone,
        )
        return BusinessCalendar(business_hours)
