"""Journal storage interface."""

from datetime import date
from typing import Protocol


class JournalStore(Protocol):
    """Interface for reading and writing journal entries."""

    def read(self, target_date: date) -> str | None:
        """Read journal content for a date. Returns None if not found."""
        ...

    def write(self, target_date: date, content: str) -> None:
        """Write/overwrite journal content for a date."""
        ...

    def append(self, target_date: date, section_header: str, content: str) -> None:
        """Append a section to an existing journal entry."""
        ...

    def exists(self, target_date: date) -> bool:
        """Check if a journal entry exists for a date."""
        ...

    def has_section(self, target_date: date, section_header: str) -> bool:
        """Check if a journal entry contains a specific section."""
        ...
