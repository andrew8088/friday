"""Calendar fetching from icalPal and gcalcli."""

import json
import subprocess
from dataclasses import dataclass
from datetime import date, datetime

from .config import Config, load_config


@dataclass
class Event:
    """A calendar event."""

    title: str
    start: datetime
    end: datetime | None
    location: str
    calendar: str
    all_day: bool
    source: str

    def format_time(self) -> str:
        """Format the event time for display."""
        if self.all_day:
            return "All day"
        return self.start.strftime("%H:%M")


def fetch_icalpal_events(
    days: int = 1, include: list[str] | None = None, exclude: list[str] | None = None
) -> list[Event]:
    """Fetch events from icalPal (macOS Calendar)."""
    try:
        cmd = ["icalPal", "eventsToday", "--days", str(days), "-o", "json"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout) if result.stdout else []
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return []

    events = []
    for item in data:
        cal_name = item.get("calendar", "")

        # Apply filters
        if include and cal_name not in include:
            continue
        if exclude and cal_name in exclude:
            continue

        try:
            start = datetime.fromisoformat(item["sdate"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(item["edate"].replace("Z", "+00:00")) if item.get("edate") else None
        except (ValueError, KeyError):
            continue

        events.append(
            Event(
                title=item.get("title", "Untitled"),
                start=start,
                end=end,
                location=item.get("location", ""),
                calendar=cal_name,
                all_day=item.get("all_day", False),
                source="icalpal",
            )
        )

    return events


def fetch_gcalcli_events(target_date: date | None = None) -> list[Event]:
    """Fetch events from gcalcli (Google Calendar)."""
    target_date = target_date or date.today()
    next_day = target_date.isoformat()

    try:
        cmd = [
            "gcalcli",
            "agenda",
            target_date.isoformat(),
            next_day,
            "--tsv",
            "--details",
            "length",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    events = []
    for line in result.stdout.strip().split("\n")[1:]:  # Skip header
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue

        try:
            start = datetime.fromisoformat(f"{parts[0]}T{parts[1]}")
            end = datetime.fromisoformat(f"{parts[2]}T{parts[3]}") if parts[2] and parts[3] else None
        except ValueError:
            continue

        events.append(
            Event(
                title=parts[4] if len(parts) > 4 else "Untitled",
                start=start,
                end=end,
                location=parts[5] if len(parts) > 5 else "",
                calendar="Google",
                all_day=False,
                source="gcalcli",
            )
        )

    return events


def fetch_all_events(config: Config | None = None, days: int = 1) -> list[Event]:
    """Fetch events from all configured calendar sources."""
    config = config or load_config()
    events = []

    # icalPal (primary)
    events.extend(
        fetch_icalpal_events(
            days=days,
            include=config.icalpal_include_calendars or None,
            exclude=config.icalpal_exclude_calendars or None,
        )
    )

    # gcalcli (if enabled)
    if config.use_gcalcli:
        events.extend(fetch_gcalcli_events())

    # Sort by start time
    return sorted(events, key=lambda e: e.start)


def fetch_today(config: Config | None = None) -> list[Event]:
    """Fetch today's events."""
    return fetch_all_events(config, days=1)


def fetch_week(config: Config | None = None) -> list[Event]:
    """Fetch this week's events."""
    return fetch_all_events(config, days=7)
