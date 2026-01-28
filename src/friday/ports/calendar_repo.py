"""Calendar repository interface."""

from datetime import date
from typing import Protocol

from friday.core.calendar import Event


class CalendarRepository(Protocol):
    """Interface for fetching calendar events from any backend."""

    def fetch_events(self, days: int = 1) -> list[Event]:
        """Fetch events for the next N days."""
        ...

    def fetch_day(self, target_date: date) -> list[Event]:
        """Fetch events for a specific date."""
        ...
