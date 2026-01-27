"""Daily recap data model and utilities."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path


class RecapMode(Enum):
    """Recap mode based on available context."""

    FULL = "full"  # Had briefing, compare planned vs actual
    TASKS_ONLY = "tasks_only"  # No briefing, but have task data
    FREEFORM = "freeform"  # Minimal data, open reflection


@dataclass
class Recap:
    """Daily recap entry."""

    date: date
    mode: RecapMode
    wins: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    energy: str | None = None
    planned_tasks: int | None = None
    completed_tasks: int | None = None
    reflection: str = ""
    tomorrow_focus: str = ""

    @property
    def age_hours(self) -> float:
        """Hours since this recap's date (end of day)."""
        recap_eod = datetime.combine(self.date, datetime.max.time())
        return (datetime.now() - recap_eod).total_seconds() / 3600

    def to_markdown(self) -> str:
        """Serialize to YAML frontmatter + markdown."""
        lines = ["---"]
        lines.append(f"date: {self.date.isoformat()}")
        lines.append(f"mode: {self.mode.value}")

        if self.planned_tasks is not None:
            lines.append(f"planned_tasks: {self.planned_tasks}")
        if self.completed_tasks is not None:
            lines.append(f"completed_tasks: {self.completed_tasks}")

        if self.wins:
            lines.append("wins:")
            for win in self.wins:
                lines.append(f'  - "{win}"')

        if self.blockers:
            lines.append("blockers:")
            for blocker in self.blockers:
                lines.append(f'  - "{blocker}"')

        if self.tags:
            lines.append("tags:")
            for tag in self.tags:
                lines.append(f'  - "{tag}"')

        if self.energy:
            lines.append(f'energy: "{self.energy}"')

        lines.append("---")
        lines.append("")

        if self.reflection:
            lines.append("## Reflection")
            lines.append("")
            lines.append(self.reflection)
            lines.append("")

        if self.tomorrow_focus:
            lines.append("## Tomorrow's Focus")
            lines.append("")
            lines.append(self.tomorrow_focus)
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, content: str) -> "Recap":
        """Parse from YAML frontmatter + markdown."""
        # Split frontmatter from body
        if not content.startswith("---"):
            raise ValueError("Invalid recap format: missing frontmatter")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Invalid recap format: incomplete frontmatter")

        frontmatter = parts[1].strip()
        body = parts[2].strip()

        # Parse frontmatter (simple YAML parsing)
        data = {}
        current_list = None
        current_key = None

        for line in frontmatter.splitlines():
            line = line.rstrip()
            if not line:
                continue

            # Check for list item
            if line.startswith("  - "):
                value = line[4:].strip().strip('"').strip("'")
                if current_key and current_list is not None:
                    current_list.append(value)
                continue

            # Check for key: value
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if value == "":
                    # Start of a list
                    current_key = key
                    current_list = []
                    data[key] = current_list
                else:
                    data[key] = value
                    current_key = None
                    current_list = None

        # Parse body sections
        reflection = ""
        tomorrow_focus = ""

        reflection_match = re.search(
            r"## Reflection\s*\n(.*?)(?=## |$)", body, re.DOTALL
        )
        if reflection_match:
            reflection = reflection_match.group(1).strip()

        tomorrow_match = re.search(
            r"## Tomorrow's Focus\s*\n(.*?)(?=## |$)", body, re.DOTALL
        )
        if tomorrow_match:
            tomorrow_focus = tomorrow_match.group(1).strip()

        # Build recap object
        return cls(
            date=date.fromisoformat(data.get("date", date.today().isoformat())),
            mode=RecapMode(data.get("mode", "freeform")),
            wins=data.get("wins", []),
            blockers=data.get("blockers", []),
            tags=data.get("tags", []),
            energy=data.get("energy"),
            planned_tasks=int(data["planned_tasks"]) if "planned_tasks" in data else None,
            completed_tasks=int(data["completed_tasks"]) if "completed_tasks" in data else None,
            reflection=reflection,
            tomorrow_focus=tomorrow_focus,
        )


def load_recap(target_date: date, recap_dir: Path) -> Recap | None:
    """Load recap for a specific date, or None if missing."""
    recap_file = recap_dir / f"{target_date.isoformat()}.md"
    if not recap_file.exists():
        return None

    try:
        return Recap.from_markdown(recap_file.read_text())
    except (ValueError, KeyError):
        return None


def load_recent_recaps(days: int, recap_dir: Path) -> list[Recap]:
    """Load recaps from the last N days (excludes today)."""
    recaps = []
    today = date.today()

    for i in range(1, days + 1):
        target = today - timedelta(days=i)
        recap = load_recap(target, recap_dir)
        if recap:
            recaps.append(recap)

    # Return in chronological order (oldest first)
    return list(reversed(recaps))


def determine_recap_mode(
    target_date: date, journal_dir: Path, ticktick_available: bool
) -> RecapMode:
    """Determine which recap mode to use based on available data."""
    journal_file = journal_dir / f"{target_date.isoformat()}.md"

    if journal_file.exists():
        return RecapMode.FULL
    elif ticktick_available:
        return RecapMode.TASKS_ONLY
    else:
        return RecapMode.FREEFORM
