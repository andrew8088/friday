"""Composite calendar adapter - combines multiple calendar sources."""

from datetime import date

from friday.config import Config
from friday.core.calendar import Event, sort_events_by_start, filter_events_by_date

from .icalpal import IcalPalAdapter
from .gcalcli import GcalcliAdapter


class CompositeCalendarAdapter:
    """
    Composite calendar adapter that combines icalPal and gcalcli.

    Implements CalendarRepository protocol.
    """

    def __init__(self, config: Config):
        self.config = config
        self._icalpal = IcalPalAdapter(
            include_calendars=config.icalpal_include_calendars or None,
            exclude_calendars=config.icalpal_exclude_calendars or None,
        )
        self._gcalcli = GcalcliAdapter() if config.use_gcalcli else None

    def fetch_events(self, days: int = 1) -> list[Event]:
        """Fetch events from all configured sources for the next N days."""
        events = []

        # Primary: icalPal (macOS Calendar)
        events.extend(self._icalpal.fetch_events(days))

        # Secondary: gcalcli (Google Calendar) if enabled
        if self._gcalcli:
            events.extend(self._gcalcli.fetch_events(days))

        # Filter to date range and sort
        today = date.today()
        end_date = date.fromordinal(today.toordinal() + days - 1)
        events = filter_events_by_date(events, today, end_date)

        return sort_events_by_start(events)

    def fetch_day(self, target_date: date) -> list[Event]:
        """Fetch events for a specific date."""
        events = []

        events.extend(self._icalpal.fetch_day(target_date))

        if self._gcalcli:
            events.extend(self._gcalcli.fetch_day(target_date))

        return sort_events_by_start(events)
