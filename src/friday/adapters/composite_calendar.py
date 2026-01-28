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
        # Support multiple gcalcli accounts
        self._gcalcli_adapters: list[GcalcliAdapter] = []
        if config.gcalcli_accounts:
            for account in config.gcalcli_accounts:
                self._gcalcli_adapters.append(
                    GcalcliAdapter(
                        config_folder=account.config_folder,
                        label=account.label,
                    )
                )
        elif config.use_gcalcli:
            # Backwards compatibility: single default account
            self._gcalcli_adapters.append(GcalcliAdapter())

    def fetch_events(self, days: int = 1) -> list[Event]:
        """Fetch events from all configured sources for the next N days."""
        events = []

        # Primary: icalPal (macOS Calendar)
        events.extend(self._icalpal.fetch_events(days))

        # Secondary: gcalcli (Google Calendar accounts)
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

        events.extend(self._icalpal.fetch_day(target_date))

        for adapter in self._gcalcli_adapters:
            events.extend(adapter.fetch_day(target_date))

        return sort_events_by_start(events)
