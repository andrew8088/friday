"""gcalcli adapter - subprocess wrapper for Google Calendar."""

import logging
import subprocess
from datetime import date, datetime

from friday.core.calendar import Event

logger = logging.getLogger(__name__)


class GcalcliAdapter:
    """
    gcalcli subprocess adapter.

    Fetches events from Google Calendar via the gcalcli CLI tool.
    Supports multiple Google accounts via separate config folders.
    """

    def __init__(
        self,
        config_folder: str | None = None,
        label: str | None = None,
        calendars: list[str] | None = None,
        timeout: int = 30,
    ):
        """
        Initialize the gcalcli adapter.

        Args:
            config_folder: Path to gcalcli config folder (for multi-account support).
                          Each account needs its own folder with OAuth credentials.
            label: Optional label to identify this account in event sources.
            calendars: List of calendar names to include. If None, all calendars are fetched.
            timeout: Command timeout in seconds.
        """
        self.config_folder = config_folder
        self.label = label or (config_folder.split("/")[-1] if config_folder else "Google")
        self.calendars = calendars
        self.timeout = timeout

    def fetch_events(self, days: int = 1) -> list[Event]:
        """Fetch events for the next N days."""
        today = date.today()
        events = []

        for i in range(days):
            target = date.fromordinal(today.toordinal() + i)
            events.extend(self.fetch_day(target))

        return events

    def fetch_day(self, target_date: date) -> list[Event]:
        """Fetch events for a specific date."""
        try:
            cmd = [
                "gcalcli",
                "agenda",
                target_date.isoformat(),
                target_date.isoformat(),
                "--tsv",
                "--details",
                "length",
            ]
            if self.config_folder:
                cmd.extend(["--config-folder", self.config_folder])
            if self.calendars:
                for cal in self.calendars:
                    cmd.extend(["--calendar", cal])
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout,
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"gcalcli command failed: {e}")
            return []
        except FileNotFoundError:
            logger.warning("gcalcli not found - install with 'pip install gcalcli'")
            return []
        except subprocess.TimeoutExpired:
            logger.warning(f"gcalcli timed out after {self.timeout}s")
            return []

        return self._parse_output(result.stdout)

    def _parse_output(self, output: str) -> list[Event]:
        """Parse gcalcli TSV output into Event objects."""
        events = []
        lines = output.strip().split("\n")

        # Skip header line
        for line in lines[1:]:
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 5:
                continue

            try:
                start = datetime.fromisoformat(f"{parts[0]}T{parts[1]}")
                end = None
                if parts[2] and parts[3]:
                    end = datetime.fromisoformat(f"{parts[2]}T{parts[3]}")

                events.append(
                    Event(
                        title=parts[4] if len(parts) > 4 else "Untitled",
                        start=start,
                        end=end,
                        location=parts[5] if len(parts) > 5 else "",
                        calendar=self.label,
                        all_day=False,
                        source="gcalcli",
                    )
                )
            except ValueError as e:
                logger.debug(f"Skipping malformed gcalcli line: {e}")
                continue

        return events
