"""Tests for gcalcli adapter."""

from unittest.mock import patch, MagicMock
from datetime import date, datetime

import pytest

from friday.adapters.gcalcli import GcalcliAdapter
from friday.config import Config, GcalAccount, load_config
from friday.adapters.composite_calendar import CompositeCalendarAdapter


class TestGcalcliAdapter:
    """Tests for GcalcliAdapter."""

    def test_default_label(self):
        """Default label is 'Google' when no config folder."""
        adapter = GcalcliAdapter()
        assert adapter.label == "Google"
        assert adapter.config_folder is None

    def test_label_from_config_folder(self):
        """Label is derived from config folder name."""
        adapter = GcalcliAdapter(config_folder="/home/user/.gcalcli/work")
        assert adapter.label == "work"

    def test_explicit_label(self):
        """Explicit label overrides derived label."""
        adapter = GcalcliAdapter(
            config_folder="/home/user/.gcalcli/work",
            label="Work Calendar",
        )
        assert adapter.label == "Work Calendar"

    @patch("friday.adapters.gcalcli.subprocess.run")
    def test_config_folder_passed_to_command(self, mock_run):
        """Config folder is passed to gcalcli command."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        adapter = GcalcliAdapter(config_folder="/home/user/.gcalcli/work")
        adapter.fetch_day(date(2025, 1, 15))

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "--config-folder" in cmd
        assert "/home/user/.gcalcli/work" in cmd

    @patch("friday.adapters.gcalcli.subprocess.run")
    def test_no_config_folder_in_default_command(self, mock_run):
        """No config folder flag when using default."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        adapter = GcalcliAdapter()
        adapter.fetch_day(date(2025, 1, 15))

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "--config-folder" not in cmd

    @patch("friday.adapters.gcalcli.subprocess.run")
    def test_events_have_correct_calendar_label(self, mock_run):
        """Parsed events use the adapter's label for calendar field."""
        tsv_output = (
            "Start\tStart Time\tEnd\tEnd Time\tTitle\tLocation\n"
            "2025-01-15\t10:00\t2025-01-15\t11:00\tMeeting\tRoom A\n"
        )
        mock_run.return_value = MagicMock(stdout=tsv_output, returncode=0)

        adapter = GcalcliAdapter(label="Work")
        events = adapter.fetch_day(date(2025, 1, 15))

        assert len(events) == 1
        assert events[0].calendar == "Work"
        assert events[0].title == "Meeting"


class TestGcalAccountConfig:
    """Tests for GcalAccount config parsing."""

    def test_parse_single_account_with_label(self, tmp_path):
        """Parse single account with label."""
        config_file = tmp_path / "friday.conf"
        config_file.write_text('GCALCLI_ACCOUNTS="~/.gcalcli/work:Work"')

        with patch("friday.config.CONFIG_FILE", config_file):
            config = load_config()

        assert len(config.gcalcli_accounts) == 1
        assert config.gcalcli_accounts[0].config_folder == "~/.gcalcli/work"
        assert config.gcalcli_accounts[0].label == "Work"

    def test_parse_single_account_without_label(self, tmp_path):
        """Parse single account without label."""
        config_file = tmp_path / "friday.conf"
        config_file.write_text('GCALCLI_ACCOUNTS="~/.gcalcli/personal"')

        with patch("friday.config.CONFIG_FILE", config_file):
            config = load_config()

        assert len(config.gcalcli_accounts) == 1
        assert config.gcalcli_accounts[0].config_folder == "~/.gcalcli/personal"
        assert config.gcalcli_accounts[0].label is None

    def test_parse_multiple_accounts(self, tmp_path):
        """Parse multiple accounts."""
        config_file = tmp_path / "friday.conf"
        config_file.write_text(
            'GCALCLI_ACCOUNTS="~/.gcalcli/personal:Personal,~/.gcalcli/work:Work"'
        )

        with patch("friday.config.CONFIG_FILE", config_file):
            config = load_config()

        assert len(config.gcalcli_accounts) == 2
        assert config.gcalcli_accounts[0].config_folder == "~/.gcalcli/personal"
        assert config.gcalcli_accounts[0].label == "Personal"
        assert config.gcalcli_accounts[1].config_folder == "~/.gcalcli/work"
        assert config.gcalcli_accounts[1].label == "Work"


class TestCompositeCalendarMultiAccount:
    """Tests for CompositeCalendarAdapter with multiple gcalcli accounts."""

    def test_creates_multiple_adapters(self):
        """Creates adapter for each gcalcli account."""
        config = Config(
            gcalcli_accounts=[
                GcalAccount("~/.gcalcli/personal", "Personal"),
                GcalAccount("~/.gcalcli/work", "Work"),
            ]
        )

        adapter = CompositeCalendarAdapter(config)

        assert len(adapter._gcalcli_adapters) == 2
        assert adapter._gcalcli_adapters[0].label == "Personal"
        assert adapter._gcalcli_adapters[1].label == "Work"

    def test_backwards_compatible_use_gcalcli(self):
        """use_gcalcli=True creates single default adapter."""
        config = Config(use_gcalcli=True)

        adapter = CompositeCalendarAdapter(config)

        assert len(adapter._gcalcli_adapters) == 1
        assert adapter._gcalcli_adapters[0].config_folder is None
        assert adapter._gcalcli_adapters[0].label == "Google"

    def test_gcalcli_accounts_overrides_use_gcalcli(self):
        """gcalcli_accounts takes precedence over use_gcalcli."""
        config = Config(
            use_gcalcli=True,  # Should be ignored
            gcalcli_accounts=[GcalAccount("~/.gcalcli/work", "Work")],
        )

        adapter = CompositeCalendarAdapter(config)

        assert len(adapter._gcalcli_adapters) == 1
        assert adapter._gcalcli_adapters[0].label == "Work"

    def test_no_gcalcli_when_disabled(self):
        """No gcalcli adapters when neither option is set."""
        config = Config(use_gcalcli=False)

        adapter = CompositeCalendarAdapter(config)

        assert len(adapter._gcalcli_adapters) == 0
