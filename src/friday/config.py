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
    work_hours: str = "09:00-17:00"
    work_task_lists: list[str] = field(default_factory=list)
    personal_task_lists: list[str] = field(default_factory=list)
    deep_work_hours: list[str] = field(default_factory=lambda: ["09:00-11:00", "14:00-16:00"])
    daily_journal_dir: str = ""
    weekly_review_day: str = "Sunday"
    # Telegram bot settings
    telegram_bot_token: str = ""
    telegram_allowed_users: list[int] = field(default_factory=list)
    telegram_briefing_time: str = "07:30"
    telegram_recap_reminder_time: str = "21:00"


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
        value = value.strip()

        # Handle quoted values with inline comments: "value" # comment
        if value.startswith('"'):
            end_quote = value.find('"', 1)
            if end_quote != -1:
                value = value[1:end_quote]
            else:
                value = value[1:]
        elif value.startswith("'"):
            end_quote = value.find("'", 1)
            if end_quote != -1:
                value = value[1:end_quote]
            else:
                value = value[1:]
        else:
            # Unquoted: strip inline comments
            if "#" in value:
                value = value.split("#")[0].strip()

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
            case "work_hours":
                config.work_hours = value
            case "work_task_lists":
                config.work_task_lists = [c.strip() for c in value.split(",") if c.strip()]
            case "personal_task_lists":
                config.personal_task_lists = [c.strip() for c in value.split(",") if c.strip()]
            case "deep_work_hours":
                config.deep_work_hours = [h.strip() for h in value.split(",") if h.strip()]
            case "daily_journal_dir":
                config.daily_journal_dir = value
            case "weekly_review_day":
                config.weekly_review_day = value
            case "telegram_bot_token":
                config.telegram_bot_token = value
            case "telegram_allowed_users":
                config.telegram_allowed_users = [int(u.strip()) for u in value.split(",") if u.strip()]
            case "telegram_briefing_time":
                config.telegram_briefing_time = value
            case "telegram_recap_reminder_time":
                config.telegram_recap_reminder_time = value

    return config
