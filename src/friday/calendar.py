"""Calendar fetching via gcalcli.

This module is preserved for backwards compatibility.
New code should import from friday.core.calendar and friday.adapters.
"""

from friday.core.calendar import Event, TimeSlot, find_free_slots

from friday.config import Config, load_config
from friday.adapters.gcalcli import GcalcliAdapter
from friday.adapters.composite_calendar import CompositeCalendarAdapter


def fetch_gcalcli_events(target_date=None) -> list[Event]:
    """Fetch events from gcalcli (Google Calendar)."""
    from datetime import date
    target_date = target_date or date.today()
    adapter = GcalcliAdapter()
    return adapter.fetch_day(target_date)


def fetch_all_events(config: Config | None = None, days: int = 1) -> list[Event]:
    """Fetch events from all configured calendar sources."""
    config = config or load_config()
    adapter = CompositeCalendarAdapter(config)
    return adapter.fetch_events(days)


def fetch_today(config: Config | None = None) -> list[Event]:
    """Fetch today's events."""
    return fetch_all_events(config, days=1)


def fetch_week(config: Config | None = None) -> list[Event]:
    """Fetch this week's events."""
    return fetch_all_events(config, days=7)


__all__ = [
    "Event",
    "TimeSlot",
    "find_free_slots",
    "fetch_gcalcli_events",
    "fetch_all_events",
    "fetch_today",
    "fetch_week",
]
