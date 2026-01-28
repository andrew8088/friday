"""Tests for core task logic."""

from datetime import date, timedelta

import pytest

from friday.core.tasks import (
    Task,
    filter_actionable,
    categorize_tasks,
    sort_by_priority,
    filter_overdue,
    filter_by_project,
)


# Fixtures
@pytest.fixture
def today():
    return date(2025, 1, 15)


@pytest.fixture
def sample_tasks(today):
    """Sample tasks covering various scenarios."""
    return [
        Task(
            id="1",
            title="Urgent important task",
            priority=5,
            due_date=today,
            project_id="p1",
            project_name="Work",
        ),
        Task(
            id="2",
            title="Important not urgent",
            priority=5,
            due_date=today + timedelta(days=10),
            project_id="p1",
            project_name="Work",
        ),
        Task(
            id="3",
            title="Urgent not important",
            priority=1,
            due_date=today,
            project_id="p2",
            project_name="Personal",
        ),
        Task(
            id="4",
            title="Neither urgent nor important",
            priority=1,
            due_date=None,
            project_id="p2",
            project_name="Personal",
        ),
        Task(
            id="5",
            title="Overdue task",
            priority=3,
            due_date=today - timedelta(days=2),
            project_id="p1",
            project_name="Work",
        ),
        Task(
            id="6",
            title="Due in 2 days",
            priority=2,
            due_date=today + timedelta(days=2),
            project_id="p3",
            project_name="Side Project",
        ),
    ]


# Task class tests
class TestTask:
    def test_is_important_high_priority(self):
        task = Task(id="1", title="Test", priority=5, due_date=None, project_id="p1")
        assert task.is_important() is True

    def test_is_important_threshold(self):
        task = Task(id="1", title="Test", priority=3, due_date=None, project_id="p1")
        assert task.is_important() is True

    def test_is_important_low_priority(self):
        task = Task(id="1", title="Test", priority=2, due_date=None, project_id="p1")
        assert task.is_important() is False

    def test_is_urgent_due_today(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=today, project_id="p1")
        assert task.is_urgent(urgent_days=3, as_of=today) is True

    def test_is_urgent_due_within_window(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=today + timedelta(days=2), project_id="p1")
        assert task.is_urgent(urgent_days=3, as_of=today) is True

    def test_is_urgent_overdue(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=today - timedelta(days=1), project_id="p1")
        assert task.is_urgent(urgent_days=3, as_of=today) is True

    def test_is_urgent_not_due_soon(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=today + timedelta(days=10), project_id="p1")
        assert task.is_urgent(urgent_days=3, as_of=today) is False

    def test_is_urgent_no_due_date(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=None, project_id="p1")
        assert task.is_urgent(urgent_days=3, as_of=today) is False

    def test_quadrant_1_urgent_important(self, today):
        task = Task(id="1", title="Test", priority=5, due_date=today, project_id="p1")
        assert task.quadrant(urgent_days=3, as_of=today) == 1
        assert task.quadrant_label(urgent_days=3, as_of=today) == "Do"

    def test_quadrant_2_not_urgent_important(self, today):
        task = Task(id="1", title="Test", priority=5, due_date=today + timedelta(days=10), project_id="p1")
        assert task.quadrant(urgent_days=3, as_of=today) == 2
        assert task.quadrant_label(urgent_days=3, as_of=today) == "Schedule"

    def test_quadrant_3_urgent_not_important(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=today, project_id="p1")
        assert task.quadrant(urgent_days=3, as_of=today) == 3
        assert task.quadrant_label(urgent_days=3, as_of=today) == "Delegate"

    def test_quadrant_4_not_urgent_not_important(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=None, project_id="p1")
        assert task.quadrant(urgent_days=3, as_of=today) == 4
        assert task.quadrant_label(urgent_days=3, as_of=today) == "Delete"

    def test_days_until_due_future(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=today + timedelta(days=5), project_id="p1")
        assert task.days_until_due(as_of=today) == 5

    def test_days_until_due_past(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=today - timedelta(days=2), project_id="p1")
        assert task.days_until_due(as_of=today) == -2

    def test_days_until_due_no_date(self, today):
        task = Task(id="1", title="Test", priority=1, due_date=None, project_id="p1")
        assert task.days_until_due(as_of=today) is None

    def test_from_api(self):
        api_data = {
            "id": "abc123",
            "title": "Test Task",
            "priority": 3,
            "dueDate": "2025-01-20T10:00:00.000+0000",
            "projectId": "proj1",
        }
        task = Task.from_api(api_data, "My Project")

        assert task.id == "abc123"
        assert task.title == "Test Task"
        assert task.priority == 3
        assert task.due_date == date(2025, 1, 20)
        assert task.project_id == "proj1"
        assert task.project_name == "My Project"

    def test_from_api_no_due_date(self):
        api_data = {
            "id": "abc123",
            "title": "Test Task",
            "priority": 0,
        }
        task = Task.from_api(api_data)

        assert task.due_date is None
        assert task.priority == 0


# Filter function tests
class TestFilterActionable:
    def test_includes_q1_tasks(self, sample_tasks, today):
        """Q1 (urgent + important) tasks should be included."""
        actionable = filter_actionable(sample_tasks, urgent_days=3, as_of=today)
        q1_task = next(t for t in sample_tasks if t.id == "1")
        assert q1_task in actionable

    def test_includes_urgent_tasks(self, sample_tasks, today):
        """Urgent tasks (even if not important) should be included."""
        actionable = filter_actionable(sample_tasks, urgent_days=3, as_of=today)
        urgent_task = next(t for t in sample_tasks if t.id == "3")
        assert urgent_task in actionable

    def test_includes_overdue_tasks(self, sample_tasks, today):
        """Overdue tasks should be included."""
        actionable = filter_actionable(sample_tasks, urgent_days=3, as_of=today)
        overdue_task = next(t for t in sample_tasks if t.id == "5")
        assert overdue_task in actionable

    def test_excludes_non_urgent_non_q1(self, sample_tasks, today):
        """Tasks that are neither urgent nor Q1 should be excluded."""
        actionable = filter_actionable(sample_tasks, urgent_days=3, as_of=today)
        q2_task = next(t for t in sample_tasks if t.id == "2")
        q4_task = next(t for t in sample_tasks if t.id == "4")
        assert q2_task not in actionable
        assert q4_task not in actionable

    def test_respects_urgent_days_parameter(self, sample_tasks, today):
        """urgent_days parameter should control the urgency window."""
        # With 1 day window, task due in 2 days is not urgent
        actionable_1day = filter_actionable(sample_tasks, urgent_days=1, as_of=today)
        due_in_2_task = next(t for t in sample_tasks if t.id == "6")
        assert due_in_2_task not in actionable_1day

        # With 3 day window, task due in 2 days is urgent
        actionable_3day = filter_actionable(sample_tasks, urgent_days=3, as_of=today)
        assert due_in_2_task in actionable_3day


class TestCategorizeTasks:
    def test_categorizes_work_tasks(self, sample_tasks):
        work, personal, other = categorize_tasks(
            sample_tasks,
            work_lists=["Work"],
            personal_lists=["Personal"],
        )
        work_titles = [t.title for t in work]
        assert "Urgent important task" in work_titles
        assert "Important not urgent" in work_titles
        assert "Overdue task" in work_titles

    def test_categorizes_personal_tasks(self, sample_tasks):
        work, personal, other = categorize_tasks(
            sample_tasks,
            work_lists=["Work"],
            personal_lists=["Personal"],
        )
        personal_titles = [t.title for t in personal]
        assert "Urgent not important" in personal_titles
        assert "Neither urgent nor important" in personal_titles

    def test_categorizes_other_tasks(self, sample_tasks):
        work, personal, other = categorize_tasks(
            sample_tasks,
            work_lists=["Work"],
            personal_lists=["Personal"],
        )
        other_titles = [t.title for t in other]
        assert "Due in 2 days" in other_titles

    def test_empty_lists(self, sample_tasks):
        work, personal, other = categorize_tasks(
            sample_tasks,
            work_lists=[],
            personal_lists=[],
        )
        assert len(work) == 0
        assert len(personal) == 0
        assert len(other) == len(sample_tasks)


class TestSortByPriority:
    def test_sorts_by_priority_descending(self, today):
        tasks = [
            Task(id="1", title="Low", priority=1, due_date=today, project_id="p1"),
            Task(id="2", title="High", priority=5, due_date=today, project_id="p1"),
            Task(id="3", title="Medium", priority=3, due_date=today, project_id="p1"),
        ]
        sorted_tasks = sort_by_priority(tasks, as_of=today)
        assert [t.title for t in sorted_tasks] == ["High", "Medium", "Low"]

    def test_sorts_by_due_date_secondary(self, today):
        tasks = [
            Task(id="1", title="Later", priority=3, due_date=today + timedelta(days=5), project_id="p1"),
            Task(id="2", title="Sooner", priority=3, due_date=today + timedelta(days=1), project_id="p1"),
            Task(id="3", title="Today", priority=3, due_date=today, project_id="p1"),
        ]
        sorted_tasks = sort_by_priority(tasks, as_of=today)
        assert [t.title for t in sorted_tasks] == ["Today", "Sooner", "Later"]

    def test_no_due_date_sorted_last(self, today):
        tasks = [
            Task(id="1", title="No date", priority=3, due_date=None, project_id="p1"),
            Task(id="2", title="Has date", priority=3, due_date=today + timedelta(days=1), project_id="p1"),
        ]
        sorted_tasks = sort_by_priority(tasks, as_of=today)
        assert sorted_tasks[0].title == "Has date"
        assert sorted_tasks[1].title == "No date"


class TestFilterOverdue:
    def test_includes_overdue_tasks(self, today):
        tasks = [
            Task(id="1", title="Overdue", priority=1, due_date=today - timedelta(days=1), project_id="p1"),
            Task(id="2", title="Due today", priority=1, due_date=today, project_id="p1"),
            Task(id="3", title="Future", priority=1, due_date=today + timedelta(days=1), project_id="p1"),
        ]
        overdue = filter_overdue(tasks, as_of=today)
        assert len(overdue) == 1
        assert overdue[0].title == "Overdue"

    def test_empty_for_no_overdue(self, today):
        tasks = [
            Task(id="1", title="Due today", priority=1, due_date=today, project_id="p1"),
            Task(id="2", title="Future", priority=1, due_date=today + timedelta(days=1), project_id="p1"),
        ]
        overdue = filter_overdue(tasks, as_of=today)
        assert len(overdue) == 0


class TestFilterByProject:
    def test_filters_by_project_name(self, sample_tasks):
        work_tasks = filter_by_project(sample_tasks, "Work")
        assert all(t.project_name == "Work" for t in work_tasks)
        assert len(work_tasks) == 3

    def test_case_insensitive(self, sample_tasks):
        work_tasks = filter_by_project(sample_tasks, "work")
        assert len(work_tasks) == 3

    def test_returns_empty_for_unknown_project(self, sample_tasks):
        unknown = filter_by_project(sample_tasks, "Unknown Project")
        assert len(unknown) == 0
