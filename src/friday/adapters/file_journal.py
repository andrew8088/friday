"""File-based journal storage adapter."""

from datetime import date
from pathlib import Path


class FileJournalStore:
    """
    File-based journal storage.

    Implements JournalStore protocol. Each day gets a markdown file.
    """

    def __init__(self, journal_dir: Path | str):
        self.journal_dir = Path(journal_dir).expanduser()
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_date(self, target_date: date) -> Path:
        """Get the file path for a given date."""
        return self.journal_dir / f"{target_date.isoformat()}.md"

    def read(self, target_date: date) -> str | None:
        """Read journal content for a date. Returns None if not found."""
        path = self._path_for_date(target_date)
        if not path.exists():
            return None
        return path.read_text()

    def write(self, target_date: date, content: str) -> None:
        """Write/overwrite journal content for a date."""
        path = self._path_for_date(target_date)
        path.write_text(content)

    def append(self, target_date: date, section_header: str, content: str) -> None:
        """Append a section to an existing journal entry."""
        path = self._path_for_date(target_date)

        if path.exists():
            existing = path.read_text()
            new_content = f"{existing}\n\n---\n\n## {section_header}\n\n{content}"
        else:
            new_content = f"## {section_header}\n\n{content}"

        path.write_text(new_content)

    def exists(self, target_date: date) -> bool:
        """Check if a journal entry exists for a date."""
        return self._path_for_date(target_date).exists()

    def has_section(self, target_date: date, section_header: str) -> bool:
        """Check if a journal entry contains a specific section."""
        content = self.read(target_date)
        if not content:
            return False
        return f"## {section_header}" in content

    def list_dates(self, start_date: date, end_date: date) -> list[date]:
        """List dates with journal entries in a range."""
        dates = []
        for path in self.journal_dir.glob("*.md"):
            try:
                entry_date = date.fromisoformat(path.stem)
                if start_date <= entry_date <= end_date:
                    dates.append(entry_date)
            except ValueError:
                continue
        return sorted(dates)

    def read_range(self, start_date: date, end_date: date) -> dict[date, str]:
        """Read all journal entries in a date range."""
        entries = {}
        for entry_date in self.list_dates(start_date, end_date):
            content = self.read(entry_date)
            if content:
                entries[entry_date] = content
        return entries
