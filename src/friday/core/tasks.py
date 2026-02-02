"""Pure task domain logic - no I/O dependencies."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Task:
    """A task with Eisenhower matrix classification."""

    id: str
    title: str
    priority: int
    due_date: date | None
    project_id: str
    project_name: str = ""
    kind: str = "TEXT"

    @property
    def is_note(self) -> bool:
        return self.kind == "NOTE"

    def is_important(self) -> bool:
        """High priority (3+) = important."""
        return self.priority >= 3

    def is_urgent(self, urgent_days: int = 3, as_of: date | None = None) -> bool:
        """Due within N days or overdue = urgent."""
        if not self.due_date:
            return False
        as_of = as_of or date.today()
        days_until = (self.due_date - as_of).days
        return days_until <= urgent_days

    def quadrant(self, urgent_days: int = 3, as_of: date | None = None) -> int:
        """
        Eisenhower quadrant (1-4).

        Q1: Urgent + Important (Do)
        Q2: Not Urgent + Important (Schedule)
        Q3: Urgent + Not Important (Delegate)
        Q4: Not Urgent + Not Important (Delete)
        """
        important = self.is_important()
        urgent = self.is_urgent(urgent_days, as_of)

        if urgent and important:
            return 1
        elif not urgent and important:
            return 2
        elif urgent and not important:
            return 3
        else:
            return 4

    def quadrant_label(self, urgent_days: int = 3, as_of: date | None = None) -> str:
        """Human-readable quadrant label."""
        labels = {1: "Do", 2: "Schedule", 3: "Delegate", 4: "Delete"}
        return labels[self.quadrant(urgent_days, as_of)]

    def days_until_due(self, as_of: date | None = None) -> int | None:
        """Days until due date (negative if overdue)."""
        if not self.due_date:
            return None
        as_of = as_of or date.today()
        return (self.due_date - as_of).days

    @classmethod
    def from_api(cls, data: dict, project_name: str = "") -> "Task":
        """Create Task from TickTick API response."""
        due = None
        if data.get("dueDate"):
            due = date.fromisoformat(data["dueDate"].split("T")[0])
        return cls(
            id=data["id"],
            title=data["title"],
            priority=data.get("priority", 0),
            due_date=due,
            project_id=data.get("projectId", ""),
            project_name=project_name,
            kind=data.get("kind", "TEXT") or "TEXT",
        )


def filter_actionable(
    tasks: list[Task],
    urgent_days: int = 3,
    as_of: date | None = None,
) -> list[Task]:
    """
    Filter to actionable tasks: due soon OR Q1 (urgent + important).

    Pure function - no I/O.
    """
    as_of = as_of or date.today()
    return [
        t
        for t in tasks
        if not t.is_note
        and (t.is_urgent(urgent_days, as_of) or t.quadrant(urgent_days, as_of) == 1)
    ]


def categorize_tasks(
    tasks: list[Task],
    work_lists: list[str],
    personal_lists: list[str],
) -> tuple[list[Task], list[Task], list[Task]]:
    """
    Split tasks into work, personal, and other categories.

    Returns: (work_tasks, personal_tasks, other_tasks)
    Pure function - no I/O.
    """
    work = [t for t in tasks if t.project_name in work_lists]
    personal = [t for t in tasks if t.project_name in personal_lists]
    other = [
        t for t in tasks if t.project_name not in work_lists and t.project_name not in personal_lists
    ]
    return work, personal, other


def sort_by_priority(tasks: list[Task], as_of: date | None = None) -> list[Task]:
    """
    Sort tasks by priority (descending) then due date (ascending).

    Pure function - no I/O.
    """
    as_of = as_of or date.today()

    def sort_key(t: Task) -> tuple[int, int]:
        # Negative priority for descending sort
        # Days until due (use large number for no due date)
        days = t.days_until_due(as_of)
        return (-t.priority, days if days is not None else 9999)

    return sorted(tasks, key=sort_key)


def filter_notes(
    tasks: list[Task],
    urgent_days: int = 3,
    as_of: date | None = None,
) -> list[Task]:
    """Filter to notes that are due soon (time-relevant reminders)."""
    as_of = as_of or date.today()
    return [
        t
        for t in tasks
        if t.is_note and t.due_date and (t.due_date - as_of).days <= urgent_days
    ]


def filter_overdue(tasks: list[Task], as_of: date | None = None) -> list[Task]:
    """Filter to overdue tasks only."""
    as_of = as_of or date.today()
    return [t for t in tasks if t.due_date and t.due_date < as_of]


def filter_by_project(tasks: list[Task], project_name: str) -> list[Task]:
    """Filter tasks to a specific project."""
    return [t for t in tasks if t.project_name.lower() == project_name.lower()]
