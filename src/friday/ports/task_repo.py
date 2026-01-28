"""Task repository interface."""

from typing import Protocol

from friday.core.tasks import Task


class TaskRepository(Protocol):
    """Interface for fetching tasks from any backend."""

    def fetch_all(self) -> list[Task]:
        """Fetch all tasks."""
        ...

    def fetch_inbox(self) -> list[Task]:
        """Fetch tasks from inbox/default list."""
        ...
