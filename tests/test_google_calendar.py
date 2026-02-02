"""Tests for Google Calendar adapter."""

from unittest.mock import patch, MagicMock
from datetime import date, datetime

import pytest

from friday.adapters.google_calendar import GoogleCalendarAdapter
from friday.config import Config, GcalAccount, load_config
from friday.adapters.composite_calendar import CompositeCalendarAdapter


class TestGoogleCalendarAdapter:
    """Tests for GoogleCalendarAdapter."""

    def test_label_from_config_folder(self):
        adapter = GoogleCalendarAdapter(config_folder="/home/user/.config/work")
        assert adapter.label == "work"

    def test_explicit_label(self):
        adapter = GoogleCalendarAdapter(
            config_folder="/home/user/.config/work",
            label="Work Calendar",
        )
        assert adapter.label == "Work Calendar"

    def test_token_path(self):
        adapter = GoogleCalendarAdapter(config_folder="/home/user/.config/work")
        assert adapter._token_path.name == "token.json"
        assert "work" in str(adapter._token_path)

    @patch("friday.adapters.google_calendar.GoogleCalendarAdapter._build_service")
    def test_fetch_day_returns_timed_events(self, mock_build):
        service = MagicMock()
        mock_build.return_value = service

        service.calendarList().list().execute.return_value = {
            "items": [{"summary": "Work", "id": "work@group.calendar.google.com"}]
        }
        service.events().list().execute.return_value = {
            "items": [
                {
                    "summary": "Standup",
                    "start": {"dateTime": "2025-01-15T10:00:00-05:00"},
                    "end": {"dateTime": "2025-01-15T10:30:00-05:00"},
                    "location": "Room A",
                },
            ]
        }

        adapter = GoogleCalendarAdapter(
            config_folder="/tmp/test",
            label="Work",
            calendars=["Work"],
        )
        events = adapter.fetch_day(date(2025, 1, 15))

        assert len(events) == 1
        assert events[0].title == "Standup"
        assert events[0].calendar == "Work"
        assert events[0].location == "Room A"
        assert events[0].all_day is False
        assert events[0].source == "google_calendar"

    @patch("friday.adapters.google_calendar.GoogleCalendarAdapter._build_service")
    def test_fetch_day_returns_all_day_events(self, mock_build):
        service = MagicMock()
        mock_build.return_value = service

        service.calendarList().list().execute.return_value = {"items": []}
        service.events().list().execute.return_value = {
            "items": [
                {
                    "summary": "Holiday",
                    "start": {"date": "2025-01-15"},
                    "end": {"date": "2025-01-16"},
                },
            ]
        }

        adapter = GoogleCalendarAdapter(config_folder="/tmp/test", label="Personal")
        events = adapter.fetch_day(date(2025, 1, 15))

        assert len(events) == 1
        assert events[0].all_day is True
        assert events[0].title == "Holiday"

    @patch("friday.adapters.google_calendar.GoogleCalendarAdapter._build_service")
    def test_fetch_day_excludes_declined_events(self, mock_build):
        service = MagicMock()
        mock_build.return_value = service

        service.calendarList().list().execute.return_value = {"items": []}
        service.events().list().execute.return_value = {
            "items": [
                {
                    "summary": "Accepted Meeting",
                    "start": {"dateTime": "2025-01-15T10:00:00-05:00"},
                    "end": {"dateTime": "2025-01-15T10:30:00-05:00"},
                    "attendees": [
                        {"email": "me@example.com", "self": True, "responseStatus": "accepted"},
                    ],
                },
                {
                    "summary": "Declined Meeting",
                    "start": {"dateTime": "2025-01-15T11:00:00-05:00"},
                    "end": {"dateTime": "2025-01-15T11:30:00-05:00"},
                    "attendees": [
                        {"email": "me@example.com", "self": True, "responseStatus": "declined"},
                    ],
                },
                {
                    "summary": "No Attendees Event",
                    "start": {"dateTime": "2025-01-15T12:00:00-05:00"},
                    "end": {"dateTime": "2025-01-15T12:30:00-05:00"},
                },
            ]
        }

        adapter = GoogleCalendarAdapter(config_folder="/tmp/test", label="Work")
        events = adapter.fetch_day(date(2025, 1, 15))

        assert len(events) == 2
        assert events[0].title == "Accepted Meeting"
        assert events[1].title == "No Attendees Event"

    @patch("friday.adapters.google_calendar.GoogleCalendarAdapter._build_service")
    def test_fetch_day_api_error_returns_empty(self, mock_build):
        mock_build.side_effect = Exception("API error")
        adapter = GoogleCalendarAdapter(config_folder="/tmp/test")
        events = adapter.fetch_day(date(2025, 1, 15))
        assert events == []

    @patch("friday.adapters.google_calendar.GoogleCalendarAdapter._build_service")
    def test_fetch_day_no_credentials_returns_empty(self, mock_build):
        mock_build.return_value = None
        adapter = GoogleCalendarAdapter(config_folder="/tmp/test")
        events = adapter.fetch_day(date(2025, 1, 15))
        assert events == []

    @patch("friday.adapters.google_calendar.GoogleCalendarAdapter._build_service")
    def test_list_calendars(self, mock_build):
        service = MagicMock()
        mock_build.return_value = service
        service.calendarList().list().execute.return_value = {
            "items": [
                {"accessRole": "owner", "summary": "andrew@gmail.com"},
                {"accessRole": "reader", "summary": "Holidays"},
            ]
        }

        adapter = GoogleCalendarAdapter(config_folder="/tmp/test")
        result = adapter.list_calendars()

        assert result == [
            ("owner", "andrew@gmail.com"),
            ("reader", "Holidays"),
        ]

    @patch("friday.adapters.google_calendar.GoogleCalendarAdapter._build_service")
    def test_resolve_calendar_ids_filters_by_name(self, mock_build):
        service = MagicMock()
        mock_build.return_value = service
        service.calendarList().list().execute.return_value = {
            "items": [
                {"summary": "Work", "id": "work@group.calendar.google.com"},
                {"summary": "Personal", "id": "personal@gmail.com"},
            ]
        }

        adapter = GoogleCalendarAdapter(
            config_folder="/tmp/test",
            calendars=["Work"],
        )
        ids = adapter._resolve_calendar_ids(service)
        assert ids == ["work@group.calendar.google.com"]

    @patch("friday.adapters.google_calendar.GoogleCalendarAdapter._build_service")
    def test_resolve_calendar_ids_no_filter_returns_primary(self, mock_build):
        service = MagicMock()
        adapter = GoogleCalendarAdapter(config_folder="/tmp/test")
        ids = adapter._resolve_calendar_ids(service)
        assert ids == ["primary"]


class TestGcalAccountConfig:
    """Tests for GcalAccount config parsing (unchanged)."""

    def test_parse_single_account_with_label(self, tmp_path):
        config_file = tmp_path / "friday.conf"
        config_file.write_text('GCALCLI_ACCOUNTS="~/.gcalcli/work:Work"')

        with patch("friday.config.CONFIG_FILE", config_file):
            config = load_config()

        assert len(config.gcalcli_accounts) == 1
        assert config.gcalcli_accounts[0].config_folder == "~/.gcalcli/work"
        assert config.gcalcli_accounts[0].label == "Work"

    def test_parse_json_format_with_calendars(self, tmp_path):
        config_file = tmp_path / "friday.conf"
        config_file.write_text(
            'GCALCLI_ACCOUNTS=\'[{"config_folder": "~/.gcalcli/work", "label": "Work", "calendars": ["Work", "Meetings"]}]\''
        )

        with patch("friday.config.CONFIG_FILE", config_file):
            config = load_config()

        assert len(config.gcalcli_accounts) == 1
        assert config.gcalcli_accounts[0].calendars == ["Work", "Meetings"]

    def test_parse_google_client_secret_file(self, tmp_path):
        config_file = tmp_path / "friday.conf"
        config_file.write_text('GOOGLE_CLIENT_SECRET_FILE="~/secrets/client_secret.json"')

        with patch("friday.config.CONFIG_FILE", config_file):
            config = load_config()

        assert config.google_client_secret_file == "~/secrets/client_secret.json"


class TestCompositeCalendarMultiAccount:
    """Tests for CompositeCalendarAdapter with multiple accounts."""

    def test_creates_multiple_adapters(self):
        config = Config(
            gcalcli_accounts=[
                GcalAccount("~/.config/personal", "Personal"),
                GcalAccount("~/.config/work", "Work"),
            ]
        )
        adapter = CompositeCalendarAdapter(config)

        assert len(adapter._adapters) == 2
        assert adapter._adapters[0].label == "Personal"
        assert adapter._adapters[1].label == "Work"

    def test_no_accounts_creates_empty_list(self):
        config = Config()
        adapter = CompositeCalendarAdapter(config)
        assert len(adapter._adapters) == 0

    def test_passes_calendars_to_adapters(self):
        config = Config(
            gcalcli_accounts=[
                GcalAccount("~/.config/work", "Work", ["Work", "Meetings"]),
            ]
        )
        adapter = CompositeCalendarAdapter(config)
        assert adapter._adapters[0].calendars == ["Work", "Meetings"]

    def test_none_calendars_when_empty_list(self):
        config = Config(
            gcalcli_accounts=[
                GcalAccount("~/.config/work", "Work", []),
            ]
        )
        adapter = CompositeCalendarAdapter(config)
        assert adapter._adapters[0].calendars is None

    def test_passes_client_secret_and_timezone(self):
        config = Config(
            gcalcli_accounts=[GcalAccount("~/.config/work", "Work")],
            google_client_secret_file="~/secret.json",
            timezone="US/Eastern",
        )
        adapter = CompositeCalendarAdapter(config)
        assert adapter._adapters[0].client_secret_file == "~/secret.json"
        assert adapter._adapters[0].timezone == "US/Eastern"
