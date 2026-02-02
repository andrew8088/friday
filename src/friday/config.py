"""Configuration management for Friday."""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

FRIDAY_HOME = Path(os.environ.get("FRIDAY_HOME", Path.home() / "friday"))
CONFIG_FILE = FRIDAY_HOME / "config" / "friday.conf"
TOKEN_FILE = FRIDAY_HOME / "config" / ".tokens.json"
DATA_DIR = FRIDAY_HOME / "data"


@dataclass
class GcalAccount:
    """A Google Calendar account configuration."""

    config_folder: str
    label: str | None = None
    calendars: list[str] = field(default_factory=list)


@dataclass
class Config:
    """Friday configuration."""

    ticktick_client_id: str = ""
    ticktick_client_secret: str = ""
    gcalcli_accounts: list[GcalAccount] = field(default_factory=list)
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
    telegram_briefing_time: str = "06:50"
    telegram_start_week_day: str = "Sunday"
    telegram_start_week_time: str = "16:00"
    telegram_end_week_day: str = "Friday"
    telegram_end_week_time: str = "17:00"
    telegram_recap_reminder_time: str = "21:00"
    google_client_secret_file: str = ""


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
            case "gcalcli_accounts":
                # JSON format: [{"config_folder": "...", "label": "...", "calendars": [...]}]
                # Simple format (backwards compat): "path1:label1,path2:label2"
                accounts = []
                if value.startswith("["):
                    # JSON format
                    try:
                        data = json.loads(value)
                        for item in data:
                            accounts.append(
                                GcalAccount(
                                    config_folder=item["config_folder"],
                                    label=item.get("label"),
                                    calendars=item.get("calendars", []),
                                )
                            )
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse GCALCLI_ACCOUNTS JSON: {e}")
                else:
                    # Simple format: "path1:label1,path2:label2"
                    for entry in value.split(","):
                        entry = entry.strip()
                        if not entry:
                            continue
                        if ":" in entry:
                            folder, label = entry.split(":", 1)
                            accounts.append(GcalAccount(folder.strip(), label.strip()))
                        else:
                            accounts.append(GcalAccount(entry))
                config.gcalcli_accounts = accounts
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
            case "telegram_start_week_day":
                config.telegram_start_week_day = value
            case "telegram_start_week_time":
                config.telegram_start_week_time = value
            case "telegram_end_week_day":
                config.telegram_end_week_day = value
            case "telegram_end_week_time":
                config.telegram_end_week_time = value
            case "google_client_secret_file":
                config.google_client_secret_file = value

    return config
