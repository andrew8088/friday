"""Tests for the shared workflow layer."""

from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from friday.config import Config, FRIDAY_HOME
from friday.workflows import (
    get_journal,
    generate_briefing,
    generate_weekly_plan,
    generate_weekly_review,
)


@pytest.fixture
def config(tmp_path):
    return Config(daily_journal_dir=str(tmp_path))


@pytest.fixture
def config_no_journal():
    return Config(daily_journal_dir="")


class TestGetJournal:
    def test_uses_configured_dir(self, tmp_path):
        config = Config(daily_journal_dir=str(tmp_path))
        journal = get_journal(config)
        assert journal.journal_dir == tmp_path

    def test_expands_user_path(self):
        config = Config(daily_journal_dir="~/some/journal")
        journal = get_journal(config)
        assert "~" not in str(journal.journal_dir)
        assert journal.journal_dir == Path.home() / "some" / "journal"

    def test_falls_back_to_default(self):
        config = Config(daily_journal_dir="")
        journal = get_journal(config)
        assert journal.journal_dir == FRIDAY_HOME / "journal" / "daily"


class TestGenerateBriefing:
    @patch("friday.workflows.compile_briefing")
    @patch("friday.workflows.ClaudeCLIService")
    def test_calls_claude_and_saves_to_journal(self, mock_cls, mock_compile, config, tmp_path):
        mock_compile.return_value = "the prompt"
        mock_instance = MagicMock()
        mock_instance.generate.return_value = "  briefing output  "
        mock_cls.return_value = mock_instance

        result = generate_briefing(config)

        mock_compile.assert_called_once()
        mock_instance.generate.assert_called_once_with("the prompt")
        assert result == "briefing output"

        # Verify journal was written
        today = date.today().isoformat()
        journal_file = tmp_path / f"{today}.md"
        assert journal_file.exists()
        content = journal_file.read_text()
        assert "## Morning Briefing" in content
        assert "briefing output" in content

    @patch("friday.workflows.compile_briefing")
    @patch("friday.workflows.ClaudeCLIService")
    def test_appends_to_existing_journal(self, mock_cls, mock_compile, config, tmp_path):
        # Pre-populate journal
        today = date.today().isoformat()
        journal_file = tmp_path / f"{today}.md"
        journal_file.write_text("## Earlier Section\n\nSome content")

        mock_compile.return_value = "prompt"
        mock_instance = MagicMock()
        mock_instance.generate.return_value = "briefing output"
        mock_cls.return_value = mock_instance

        generate_briefing(config)

        content = journal_file.read_text()
        assert "## Earlier Section" in content
        assert "## Morning Briefing" in content
        assert "---" in content

    @patch("friday.workflows.compile_briefing")
    @patch("friday.workflows.ClaudeCLIService")
    def test_propagates_claude_errors(self, mock_cls, mock_compile, config):
        mock_compile.return_value = "prompt"
        mock_instance = MagicMock()
        mock_instance.generate.side_effect = RuntimeError("Claude CLI not found")
        mock_cls.return_value = mock_instance

        with pytest.raises(RuntimeError, match="Claude CLI not found"):
            generate_briefing(config)


class TestGenerateWeeklyPlan:
    @patch("friday.workflows.compile_week")
    @patch("friday.workflows.ClaudeCLIService")
    def test_calls_claude_and_saves_to_journal(self, mock_cls, mock_compile, config, tmp_path):
        mock_compile.return_value = "week prompt"
        mock_instance = MagicMock()
        mock_instance.generate.return_value = "weekly plan output"
        mock_cls.return_value = mock_instance

        result = generate_weekly_plan(config)

        mock_instance.generate.assert_called_once_with("week prompt")
        assert result == "weekly plan output"

        today = date.today().isoformat()
        content = (tmp_path / f"{today}.md").read_text()
        assert "## Weekly Plan" in content
        assert "weekly plan output" in content


class TestGenerateWeeklyReview:
    @patch("friday.workflows.compile_review")
    @patch("friday.workflows.ClaudeCLIService")
    def test_calls_claude_and_saves_to_journal(self, mock_cls, mock_compile, config, tmp_path):
        mock_compile.return_value = "review prompt"
        mock_instance = MagicMock()
        mock_instance.generate.return_value = "weekly review output"
        mock_cls.return_value = mock_instance

        result = generate_weekly_review(config)

        mock_instance.generate.assert_called_once_with("review prompt")
        assert result == "weekly review output"

        today = date.today().isoformat()
        content = (tmp_path / f"{today}.md").read_text()
        assert "## Weekly Review" in content
        assert "weekly review output" in content
