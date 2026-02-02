"""Google Calendar API adapter."""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from friday.core.calendar import Event

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class GoogleCalendarAdapter:
    """Fetches events from Google Calendar via the API."""

    def __init__(
        self,
        config_folder: str,
        label: str | None = None,
        calendars: list[str] | None = None,
        client_secret_file: str = "",
        timezone: str = "America/Toronto",
    ):
        self.config_folder = config_folder
        self.label = label or Path(config_folder).name
        self.calendars = calendars
        self.client_secret_file = client_secret_file
        self.timezone = timezone
        self._token_path = Path(config_folder).expanduser() / "token.json"

    def _get_credentials(self):
        """Load credentials from token.json, refreshing if needed."""
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if not self._token_path.exists():
            logger.warning(f"No token.json for {self.label} — run 'friday cal-auth'")
            return None

        creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._token_path.write_text(creds.to_json())
                self._token_path.chmod(0o600)
            except Exception as e:
                logger.warning(f"Failed to refresh token for {self.label}: {e}")
                return None

        return creds

    def _build_service(self):
        """Build a Google Calendar API service."""
        from googleapiclient.discovery import build

        creds = self._get_credentials()
        if not creds:
            return None
        return build("calendar", "v3", credentials=creds)

    def _resolve_calendar_ids(self, service) -> list[str]:
        """Resolve display name filters to calendar IDs."""
        if not self.calendars:
            return ["primary"]

        result = service.calendarList().list().execute()
        cal_map = {}
        for entry in result.get("items", []):
            cal_map[entry["summary"]] = entry["id"]

        ids = []
        for name in self.calendars:
            if name in cal_map:
                ids.append(cal_map[name])
            else:
                logger.warning(f"Calendar '{name}' not found for {self.label}")
        return ids or ["primary"]

    def authenticate(self) -> bool:
        """Run OAuth flow for this account. Returns True on success."""
        from google_auth_oauthlib.flow import InstalledAppFlow

        if not self.client_secret_file:
            logger.error("No client secret file configured")
            return False

        secret_path = Path(self.client_secret_file).expanduser()
        if not secret_path.exists():
            logger.error(f"Client secret file not found: {secret_path}")
            return False

        flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
        creds = flow.run_local_server(port=0)

        token_dir = self._token_path.parent
        token_dir.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())
        self._token_path.chmod(0o600)
        return True

    def fetch_events(self, days: int = 1) -> list[Event]:
        """Fetch events for the next N days."""
        events = []
        today = date.today()
        for i in range(days):
            events.extend(self.fetch_day(date.fromordinal(today.toordinal() + i)))
        return events

    def fetch_day(self, target_date: date) -> list[Event]:
        """Fetch events for a specific date."""
        try:
            return self._fetch_day_api(target_date)
        except Exception as e:
            logger.warning(f"Google Calendar API error for {self.label}: {e}")
            return []

    def _fetch_day_api(self, target_date: date) -> list[Event]:
        service = self._build_service()
        if not service:
            return []

        cal_ids = self._resolve_calendar_ids(service)
        time_min = datetime(target_date.year, target_date.month, target_date.day).isoformat() + "Z"
        next_day = target_date + timedelta(days=1)
        time_max = datetime(next_day.year, next_day.month, next_day.day).isoformat() + "Z"

        events = []
        for cal_id in cal_ids:
            result = (
                service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    timeZone=self.timezone,
                )
                .execute()
            )

            for item in result.get("items", []):
                start_raw = item.get("start", {})
                end_raw = item.get("end", {})

                if "date" in start_raw:
                    # All-day event — attach timezone so sorting with timed events works
                    tz = ZoneInfo(self.timezone)
                    start_dt = datetime.fromisoformat(start_raw["date"]).replace(tzinfo=tz)
                    end_dt = datetime.fromisoformat(end_raw["date"]).replace(tzinfo=tz) if "date" in end_raw else None
                    all_day = True
                elif "dateTime" in start_raw:
                    start_dt = datetime.fromisoformat(start_raw["dateTime"])
                    end_dt = datetime.fromisoformat(end_raw["dateTime"]) if "dateTime" in end_raw else None
                    all_day = False
                else:
                    continue

                events.append(
                    Event(
                        title=item.get("summary", "Untitled"),
                        start=start_dt,
                        end=end_dt,
                        location=item.get("location", ""),
                        calendar=self.label,
                        all_day=all_day,
                        source="google_calendar",
                    )
                )

        return events

    def list_calendars(self) -> list[tuple[str, str]]:
        """List calendars as (accessRole, summary) tuples."""
        service = self._build_service()
        if not service:
            return []

        result = service.calendarList().list().execute()
        return [
            (entry.get("accessRole", ""), entry.get("summary", ""))
            for entry in result.get("items", [])
        ]
