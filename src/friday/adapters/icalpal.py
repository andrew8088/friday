"""icalPal adapter - subprocess wrapper for macOS Calendar."""

import json
import logging
import subprocess
from datetime import date, datetime

from friday.core.calendar import Event

logger = logging.getLogger(__name__)


class IcalPalAdapter:
    """
    icalPal subprocess adapter.

    Fetches events from macOS Calendar via the icalPal CLI tool.
    """

    def __init__(
        self,
        include_calendars: list[str] | None = None,
        exclude_calendars: list[str] | None = None,
        timeout: int = 30,
    ):
        self.include_calendars = include_calendars
        self.exclude_calendars = exclude_calendars
        self.timeout = timeout

    def fetch_events(self, days: int = 1) -> list[Event]:
        """Fetch events for the next N days."""
        try:
            command = "eventsToday" if days <= 1 else f"eventsToday+{days}"
            cmd = ["icalPal", command, "-o", "json"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout,
            )
            data = json.loads(result.stdout) if result.stdout else []
        except subprocess.CalledProcessError as e:
            logger.warning(f"icalPal command failed: {e}")
            return []
        except FileNotFoundError:
            logger.warning("icalPal not found - install with 'brew install icalpal'")
            return []
        except subprocess.TimeoutExpired:
            logger.warning(f"icalPal timed out after {self.timeout}s")
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse icalPal output: {e}")
            return []

        return self._parse_events(data)

    def fetch_day(self, target_date: date) -> list[Event]:
        """Fetch events for a specific date."""
        # icalPal doesn't support arbitrary dates, so fetch range and filter
        today = date.today()
        days_ahead = (target_date - today).days

        if days_ahead < 0:
            return []  # Can't fetch past events easily

        events = self.fetch_events(days=days_ahead + 1)
        return [e for e in events if e.start.date() == target_date]

    def _parse_events(self, data: list[dict]) -> list[Event]:
        """Parse icalPal JSON output into Event objects."""
        events = []

        for item in data:
            cal_name = item.get("calendar", "")

            # Apply calendar filters
            if self.include_calendars and cal_name not in self.include_calendars:
                continue
            if self.exclude_calendars and cal_name in self.exclude_calendars:
                continue

            try:
                event = self._parse_event(item)
                if event:
                    events.append(event)
            except (ValueError, KeyError, TypeError) as e:
                logger.debug(f"Skipping malformed event: {e}")
                continue

        return events

    def _parse_event(self, item: dict) -> Event | None:
        """Parse a single event from icalPal data."""
        is_all_day = item.get("all_day") == 1

        # Use sctime/ectime strings - they have correct dates for recurring events
        sctime = item.get("sctime", "")
        ectime = item.get("ectime", "")

        if sctime:
            start = datetime.strptime(sctime[:19], "%Y-%m-%d %H:%M:%S")
        elif item.get("sseconds"):
            start = datetime.fromtimestamp(item["sseconds"])
        else:
            return None

        if ectime:
            end = datetime.strptime(ectime[:19], "%Y-%m-%d %H:%M:%S")
        elif item.get("eseconds"):
            end = datetime.fromtimestamp(item["eseconds"])
        else:
            end = None

        return Event(
            title=item.get("title", "Untitled"),
            start=start,
            end=end,
            location=item.get("location") or item.get("address") or "",
            calendar=item.get("calendar", ""),
            all_day=is_all_day,
            source="icalpal",
        )
