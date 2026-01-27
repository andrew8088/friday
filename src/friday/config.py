"""Configuration management for Friday."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

FRIDAY_HOME = Path(os.environ.get("FRIDAY_HOME", Path.home() / "friday"))
CONFIG_FILE = FRIDAY_HOME / "config" / "friday.conf"
TOKEN_FILE = FRIDAY_HOME / "config" / ".tokens.json"
DATA_DIR = FRIDAY_HOME / "data"


@dataclass
class Config:
    """Friday configuration."""

    ticktick_client_id: str = ""
    ticktick_client_secret: str = ""
    use_gcalcli: bool = False
    icalpal_include_calendars: list[str] = field(default_factory=list)
    icalpal_exclude_calendars: list[str] = field(default_factory=list)
    timezone: str = "America/Toronto"
    deep_work_hours: list[str] = field(default_factory=lambda: ["09:00-11:00", "14:00-16:00"])
    no_meetings_before: str = "10:00"
    weekly_review_day: str = "Sunday"


@dataclass
class Tokens:
    """OAuth tokens for TickTick."""

    access_token: str = ""
    refresh_token: str = ""
    expires_at: int = 0

    def save(self) -> None:
        """Save tokens to file."""
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(
            json.dumps(
                {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_at": self.expires_at,
                }
            )
        )
        TOKEN_FILE.chmod(0o600)

    @classmethod
    def load(cls) -> "Tokens":
        """Load tokens from file."""
        if not TOKEN_FILE.exists():
            return cls()
        try:
            data = json.loads(TOKEN_FILE.read_text())
            return cls(
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token", ""),
                expires_at=data.get("expires_at", 0),
            )
        except (json.JSONDecodeError, KeyError):
            return cls()


def load_config() -> Config:
    """Load configuration from friday.conf file."""
    config = Config()

    if not CONFIG_FILE.exists():
        return config

    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")

        match key:
            case "ticktick_client_id":
                config.ticktick_client_id = value
            case "ticktick_client_secret":
                config.ticktick_client_secret = value
            case "use_gcalcli":
                config.use_gcalcli = value.lower() == "true"
            case "icalpal_include_calendars":
                config.icalpal_include_calendars = [c.strip() for c in value.split(",") if c.strip()]
            case "icalpal_exclude_calendars":
                config.icalpal_exclude_calendars = [c.strip() for c in value.split(",") if c.strip()]
            case "timezone":
                config.timezone = value
            case "deep_work_hours":
                config.deep_work_hours = [h.strip() for h in value.split(",") if h.strip()]
            case "no_meetings_before":
                config.no_meetings_before = value
            case "weekly_review_day":
                config.weekly_review_day = value

    return config
