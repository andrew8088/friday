"""Adapters - I/O implementations of ports."""

from .ticktick_api import TickTickAdapter, AuthenticationError
from .icalpal import IcalPalAdapter
from .gcalcli import GcalcliAdapter
from .composite_calendar import CompositeCalendarAdapter
from .file_journal import FileJournalStore
from .claude_cli import ClaudeCLIService

__all__ = [
    "TickTickAdapter",
    "AuthenticationError",
    "IcalPalAdapter",
    "GcalcliAdapter",
    "CompositeCalendarAdapter",
    "FileJournalStore",
    "ClaudeCLIService",
]
