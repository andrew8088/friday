"""Tests for core recap logic."""

from datetime import date

import pytest

from friday.core.recap import Recap, RecapMode, determine_recap_mode


@pytest.fixture
def today():
    return date(2025, 1, 15)


class TestRecap:
    def test_to_markdown_full(self, today):
        """Test serialization with all fields."""
        recap = Recap(
            date=today,
            mode=RecapMode.FULL,
            wins=["Completed project", "Good meeting"],
            blockers=["Slow build times"],
            tags=["productive", "focused"],
            energy="high",
            planned_tasks=5,
            completed_tasks=4,
            reflection="Today went well overall.",
            tomorrow_focus="Finish the API integration",
        )

        md = recap.to_markdown()

        # Check frontmatter
        assert "---" in md
        assert "date: 2025-01-15" in md
        assert "mode: full" in md
        assert "planned_tasks: 5" in md
        assert "completed_tasks: 4" in md
        assert 'energy: "high"' in md

        # Check lists
        assert 'wins:' in md
        assert '"Completed project"' in md
        assert '"Good meeting"' in md
        assert 'blockers:' in md
        assert '"Slow build times"' in md

        # Check body sections
        assert "## Reflection" in md
        assert "Today went well overall." in md
        assert "## Tomorrow's Focus" in md
        assert "Finish the API integration" in md

    def test_to_markdown_minimal(self, today):
        """Test serialization with minimal fields."""
        recap = Recap(
            date=today,
            mode=RecapMode.FREEFORM,
        )

        md = recap.to_markdown()

        assert "date: 2025-01-15" in md
        assert "mode: freeform" in md
        assert "wins:" not in md
        assert "blockers:" not in md
        assert "## Reflection" not in md

    def test_from_markdown_roundtrip(self, today):
        """Test that from_markdown can parse to_markdown output."""
        original = Recap(
            date=today,
            mode=RecapMode.FULL,
            wins=["Win 1", "Win 2"],
            blockers=["Blocker 1"],
            tags=["tag1"],
            energy="medium",
            planned_tasks=3,
            completed_tasks=2,
            reflection="Test reflection.",
            tomorrow_focus="Test focus.",
        )

        md = original.to_markdown()
        parsed = Recap.from_markdown(md)

        assert parsed.date == original.date
        assert parsed.mode == original.mode
        assert parsed.wins == original.wins
        assert parsed.blockers == original.blockers
        assert parsed.tags == original.tags
        assert parsed.energy == original.energy
        assert parsed.planned_tasks == original.planned_tasks
        assert parsed.completed_tasks == original.completed_tasks
        assert parsed.reflection == original.reflection
        assert parsed.tomorrow_focus == original.tomorrow_focus

    def test_from_markdown_missing_frontmatter(self):
        """Test error handling for invalid format."""
        with pytest.raises(ValueError, match="missing frontmatter"):
            Recap.from_markdown("No frontmatter here")

    def test_from_markdown_incomplete_frontmatter(self):
        """Test error handling for incomplete frontmatter."""
        with pytest.raises(ValueError, match="incomplete frontmatter"):
            Recap.from_markdown("---\ndate: 2025-01-15")

    def test_from_markdown_defaults(self, today):
        """Test that missing fields get defaults."""
        md = f"""---
date: {today.isoformat()}
mode: freeform
---

Just some text.
"""
        recap = Recap.from_markdown(md)

        assert recap.wins == []
        assert recap.blockers == []
        assert recap.energy is None
        assert recap.planned_tasks is None

    def test_from_markdown_parses_lists(self, today):
        """Test YAML list parsing."""
        md = f"""---
date: {today.isoformat()}
mode: full
wins:
  - "First win"
  - "Second win"
blockers:
  - "A blocker"
---
"""
        recap = Recap.from_markdown(md)

        assert recap.wins == ["First win", "Second win"]
        assert recap.blockers == ["A blocker"]

    def test_from_markdown_parses_body_sections(self, today):
        """Test body section parsing."""
        md = f"""---
date: {today.isoformat()}
mode: full
---

## Reflection

This is the reflection text.
It spans multiple lines.

## Tomorrow's Focus

Focus on testing.
"""
        recap = Recap.from_markdown(md)

        assert "This is the reflection text" in recap.reflection
        assert "It spans multiple lines" in recap.reflection
        assert "Focus on testing" in recap.tomorrow_focus


class TestDetermineRecapMode:
    def test_full_mode_with_briefing(self):
        """FULL mode when briefing exists."""
        mode = determine_recap_mode(has_briefing=True, has_task_data=True)
        assert mode == RecapMode.FULL

    def test_full_mode_prioritizes_briefing(self):
        """Briefing presence takes priority over task data."""
        mode = determine_recap_mode(has_briefing=True, has_task_data=False)
        assert mode == RecapMode.FULL

    def test_tasks_only_mode(self):
        """TASKS_ONLY mode when only task data available."""
        mode = determine_recap_mode(has_briefing=False, has_task_data=True)
        assert mode == RecapMode.TASKS_ONLY

    def test_freeform_mode(self):
        """FREEFORM mode when no data available."""
        mode = determine_recap_mode(has_briefing=False, has_task_data=False)
        assert mode == RecapMode.FREEFORM


class TestRecapModeEnum:
    def test_mode_values(self):
        """Test RecapMode enum values."""
        assert RecapMode.FULL.value == "full"
        assert RecapMode.TASKS_ONLY.value == "tasks_only"
        assert RecapMode.FREEFORM.value == "freeform"

    def test_mode_from_value(self):
        """Test creating RecapMode from string value."""
        assert RecapMode("full") == RecapMode.FULL
        assert RecapMode("tasks_only") == RecapMode.TASKS_ONLY
        assert RecapMode("freeform") == RecapMode.FREEFORM
