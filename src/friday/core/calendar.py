"""Pure calendar domain logic - no I/O dependencies."""

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass
class Event:
    """A calendar event."""

    title: str
    start: datetime
    end: datetime | None
    location: str
    calendar: str
    all_day: bool
    source: str

    def format_time(self) -> str:
        """Format the event time for display."""
        if self.all_day:
            return "All day"
        return self.start.strftime("%H:%M")

    def duration_minutes(self) -> int | None:
        """Event duration in minutes, or None if no end time."""
        if not self.end:
            return None
        return int((self.end - self.start).total_seconds() / 60)


@dataclass
class TimeSlot:
    """A free time slot."""

    start: datetime
    end: datetime

    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() / 60)

    def format(self) -> str:
        return f"{self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')} ({self.duration_minutes()} min)"

    def contains(self, dt: datetime) -> bool:
        """Check if a datetime falls within this slot."""
        return self.start <= dt < self.end

    def overlaps(self, other: "TimeSlot") -> bool:
        """Check if this slot overlaps with another."""
        return self.start < other.end and other.start < self.end


def find_free_slots(
    events: list[Event],
    work_start: int = 9,
    work_end: int = 17,
    min_duration: int = 30,
    target_date: date | None = None,
) -> list[TimeSlot]:
    """
    Find free time slots between events during work hours.

    Pure function - no I/O.

    Args:
        events: List of calendar events (should be for a single day)
        work_start: Start of work day (hour, 24h format)
        work_end: End of work day (hour, 24h format)
        min_duration: Minimum slot duration in minutes
        target_date: Date to find slots for (defaults to first event's date or today)

    Returns:
        List of free TimeSlots
    """
    # Determine target date
    if target_date:
        d = target_date
    elif events:
        d = events[0].start.date()
    else:
        d = date.today()

    # Work hours boundaries
    day_start = datetime.combine(d, time(work_start, 0))
    day_end = datetime.combine(d, time(work_end, 0))

    # Filter to timed events only (not all-day) and sort by start
    timed_events = sorted(
        [e for e in events if not e.all_day and e.end is not None],
        key=lambda e: e.start,
    )

    free_slots = []
    current_time = day_start

    for event in timed_events:
        event_start = event.start
        event_end = event.end or event.start

        # Skip events outside work hours
        if event_end <= day_start or event_start >= day_end:
            continue

        # Clamp to work hours
        event_start = max(event_start, day_start)
        event_end = min(event_end, day_end)

        # Gap before this event?
        if event_start > current_time:
            gap = TimeSlot(start=current_time, end=event_start)
            if gap.duration_minutes() >= min_duration:
                free_slots.append(gap)

        # Move current time past this event
        current_time = max(current_time, event_end)

    # Gap after last event?
    if current_time < day_end:
        gap = TimeSlot(start=current_time, end=day_end)
        if gap.duration_minutes() >= min_duration:
            free_slots.append(gap)

    return free_slots


def filter_events_by_date(
    events: list[Event],
    start_date: date,
    end_date: date | None = None,
) -> list[Event]:
    """
    Filter events to those within a date range.

    Pure function - no I/O.
    """
    end_date = end_date or start_date
    return [e for e in events if start_date <= e.start.date() <= end_date]


def sort_events_by_start(events: list[Event]) -> list[Event]:
    """Sort events by start time."""
    return sorted(events, key=lambda e: e.start)


def find_conflicts(events: list[Event]) -> list[tuple[Event, Event]]:
    """
    Find overlapping events.

    Returns list of (event1, event2) tuples that conflict.
    Pure function - no I/O.
    """
    conflicts = []
    sorted_events = sort_events_by_start(events)

    for i, e1 in enumerate(sorted_events):
        if e1.all_day or not e1.end:
            continue
        for e2 in sorted_events[i + 1 :]:
            if e2.all_day or not e2.end:
                continue
            # e2 starts after e1 ends - no more conflicts possible
            if e2.start >= e1.end:
                break
            # e2 starts before e1 ends - conflict
            conflicts.append((e1, e2))

    return conflicts


def is_during_hours(
    dt: datetime,
    start_hour: int,
    end_hour: int,
) -> bool:
    """Check if a datetime is during specified hours."""
    return start_hour <= dt.hour < end_hour
