"""Composite calendar adapter - combines multiple calendar sources."""

from datetime import date

from friday.config import Config
from friday.core.calendar import Event, sort_events_by_start, filter_events_by_date

from .gcalcli import GcalcliAdapter


class CompositeCalendarAdapter:
    """
    Composite calendar adapter using gcalcli.

    Implements CalendarRepository protocol.
    """

    def __init__(self, config: Config):
        self.config = config
        self._gcalcli_adapters: list[GcalcliAdapter] = []
        if config.gcalcli_accounts:
            for account in config.gcalcli_accounts:
                self._gcalcli_adapters.append(
                    GcalcliAdapter(
                        config_folder=account.config_folder,
                        label=account.label,
                        calendars=account.calendars or None,
                    )
                )
        else:
            # Default: single gcalcli account
            self._gcalcli_adapters.append(GcalcliAdapter())

    def fetch_events(self, days: int = 1) -> list[Event]:
        """Fetch events from all configured sources for the next N days."""
        events = []

        for adapter in self._gcalcli_adapters:
            events.extend(adapter.fetch_events(days))

        # Filter to date range and sort
        today = date.today()
        end_date = date.fromordinal(today.toordinal() + days - 1)
        events = filter_events_by_date(events, today, end_date)

        return sort_events_by_start(events)

    def fetch_day(self, target_date: date) -> list[Event]:
        """Fetch events for a specific date."""
        events = []

        for adapter in self._gcalcli_adapters:
            events.extend(adapter.fetch_day(target_date))

        return sort_events_by_start(events)
