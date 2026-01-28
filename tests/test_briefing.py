"""Tests for core briefing assembly logic."""

from datetime import date, datetime, time, timedelta

import pytest

from friday.core.tasks import Task
from friday.core.calendar import Event
from friday.core.briefing import (
    BriefingData,
    assemble_briefing,
    format_task_line,
    format_event_line,
    format_briefing_sections,
)


@pytest.fixture
def today():
    return date(2025, 1, 15)


@pytest.fixture
def work_hours_datetime(today):
    return datetime.combine(today, time(10, 0))


@pytest.fixture
def outside_work_hours_datetime(today):
    return datetime.combine(today, time(7, 0))


@pytest.fixture
def sample_tasks(today):
    return [
        Task(
            id="1",
            title="Urgent work task",
            priority=5,
            due_date=today,
            project_id="p1",
            project_name="Work",
        ),
        Task(
            id="2",
            title="Important personal task",
            priority=4,
            due_date=today + timedelta(days=1),
            project_id="p2",
            project_name="Personal",
        ),
        Task(
            id="3",
            title="Low priority task",
            priority=1,
            due_date=today + timedelta(days=10),
            project_id="p3",
            project_name="Side Project",
        ),
    ]


@pytest.fixture
def sample_events(today):
    return [
        Event(
            title="Morning standup",
            start=datetime.combine(today, time(9, 0)),
            end=datetime.combine(today, time(9, 30)),
            location="Zoom",
            calendar="Work",
            all_day=False,
            source="test",
        ),
        Event(
            title="Lunch",
            start=datetime.combine(today, time(12, 0)),
            end=datetime.combine(today, time(13, 0)),
            location="",
            calendar="Personal",
            all_day=False,
            source="test",
        ),
    ]


class TestAssembleBriefing:
    def test_filters_actionable_tasks(self, sample_tasks, sample_events, work_hours_datetime, today):
        """Only actionable tasks should be included."""
        data = assemble_briefing(
            tasks=sample_tasks,
            events=sample_events,
            work_task_lists=["Work"],
            personal_task_lists=["Personal"],
            work_start=9,
            work_end=17,
            as_of=work_hours_datetime,
        )

        # Low priority task with far due date should not be included
        all_tasks = data.work_tasks + data.personal_tasks + data.other_tasks
        task_titles = [t.title for t in all_tasks]
        assert "Urgent work task" in task_titles
        assert "Important personal task" in task_titles
        assert "Low priority task" not in task_titles

    def test_categorizes_tasks_correctly(self, sample_tasks, sample_events, work_hours_datetime):
        data = assemble_briefing(
            tasks=sample_tasks,
            events=sample_events,
            work_task_lists=["Work"],
            personal_task_lists=["Personal"],
            work_start=9,
            work_end=17,
            as_of=work_hours_datetime,
        )

        assert len(data.work_tasks) == 1
        assert data.work_tasks[0].project_name == "Work"

        assert len(data.personal_tasks) == 1
        assert data.personal_tasks[0].project_name == "Personal"

    def test_work_hours_flag_during_work(self, sample_tasks, sample_events, work_hours_datetime):
        data = assemble_briefing(
            tasks=sample_tasks,
            events=sample_events,
            work_task_lists=["Work"],
            personal_task_lists=["Personal"],
            work_start=9,
            work_end=17,
            as_of=work_hours_datetime,
        )

        assert data.is_work_hours is True

    def test_work_hours_flag_outside_work(self, sample_tasks, sample_events, outside_work_hours_datetime):
        data = assemble_briefing(
            tasks=sample_tasks,
            events=sample_events,
            work_task_lists=["Work"],
            personal_task_lists=["Personal"],
            work_start=9,
            work_end=17,
            as_of=outside_work_hours_datetime,
        )

        assert data.is_work_hours is False

    def test_finds_free_slots(self, sample_tasks, sample_events, work_hours_datetime):
        data = assemble_briefing(
            tasks=sample_tasks,
            events=sample_events,
            work_task_lists=["Work"],
            personal_task_lists=["Personal"],
            work_start=9,
            work_end=17,
            as_of=work_hours_datetime,
        )

        # Should have slots: 9:30-12:00, 13:00-17:00
        assert len(data.free_slots) == 2

    def test_sets_date_info(self, sample_tasks, sample_events, work_hours_datetime, today):
        data = assemble_briefing(
            tasks=sample_tasks,
            events=sample_events,
            work_task_lists=["Work"],
            personal_task_lists=["Personal"],
            work_start=9,
            work_end=17,
            as_of=work_hours_datetime,
        )

        assert data.date == today
        assert data.day_of_week == "Wednesday"


class TestFormatTaskLine:
    def test_overdue_task(self, today):
        task = Task(
            id="1",
            title="Overdue task",
            priority=5,
            due_date=today - timedelta(days=2),
            project_id="p1",
            project_name="Work",
        )
        line = format_task_line(task, as_of=today)
        assert "[Do]" in line
        assert "OVERDUE by 2d" in line
        assert "Overdue task" in line
        assert "project: Work" in line

    def test_due_today(self, today):
        task = Task(
            id="1",
            title="Today task",
            priority=3,
            due_date=today,
            project_id="p1",
            project_name="Work",
        )
        line = format_task_line(task, as_of=today)
        assert "due TODAY" in line

    def test_due_in_future(self, today):
        task = Task(
            id="1",
            title="Future task",
            priority=3,
            due_date=today + timedelta(days=5),
            project_id="p1",
            project_name="Work",
        )
        line = format_task_line(task, as_of=today)
        assert "due in 5d" in line

    def test_quadrant_labels(self, today):
        # Q1: Do
        q1 = Task(id="1", title="Q1", priority=5, due_date=today, project_id="p1", project_name="Work")
        assert "[Do]" in format_task_line(q1, as_of=today)

        # Q2: Schedule
        q2 = Task(id="2", title="Q2", priority=5, due_date=today + timedelta(days=10), project_id="p1", project_name="Work")
        assert "[Schedule]" in format_task_line(q2, as_of=today)

        # Q3: Delegate
        q3 = Task(id="3", title="Q3", priority=1, due_date=today, project_id="p1", project_name="Work")
        assert "[Delegate]" in format_task_line(q3, as_of=today)


class TestFormatEventLine:
    def test_regular_event(self, today):
        event = Event(
            title="Meeting",
            start=datetime.combine(today, time(14, 30)),
            end=datetime.combine(today, time(15, 30)),
            location="Room 101",
            calendar="Work",
            all_day=False,
            source="test",
        )
        line = format_event_line(event)
        assert "14:30" in line
        assert "15:30" in line
        assert "Meeting" in line
        assert "@ Room 101" in line

    def test_all_day_event(self, today):
        event = Event(
            title="Holiday",
            start=datetime.combine(today, time(0, 0)),
            end=datetime.combine(today, time(23, 59)),
            location="",
            calendar="Personal",
            all_day=True,
            source="test",
        )
        line = format_event_line(event)
        assert "All day" in line
        assert "Holiday" in line

    def test_event_without_location(self, today):
        event = Event(
            title="Call",
            start=datetime.combine(today, time(10, 0)),
            end=datetime.combine(today, time(10, 30)),
            location="",
            calendar="Work",
            all_day=False,
            source="test",
        )
        line = format_event_line(event)
        assert "@" not in line


class TestFormatBriefingSections:
    def test_formats_tasks_section(self, today):
        data = BriefingData(
            date=today,
            day_of_week="Wednesday",
            work_tasks=[
                Task(id="1", title="Work task", priority=5, due_date=today, project_id="p1", project_name="Work"),
            ],
            personal_tasks=[],
            other_tasks=[],
            events=[],
            free_slots=[],
            is_work_hours=True,
            work_hours_str="09:00-17:00",
        )

        sections = format_briefing_sections(data)
        assert "### Work Tasks" in sections["tasks"]
        assert "Work task" in sections["tasks"]
        assert "### Personal Tasks" in sections["tasks"]

    def test_formats_empty_tasks_as_none(self, today):
        data = BriefingData(
            date=today,
            day_of_week="Wednesday",
            work_tasks=[],
            personal_tasks=[],
            other_tasks=[],
            events=[],
            free_slots=[],
            is_work_hours=True,
            work_hours_str="09:00-17:00",
        )

        sections = format_briefing_sections(data)
        assert "None" in sections["tasks"]

    def test_formats_calendar_section(self, today):
        data = BriefingData(
            date=today,
            day_of_week="Wednesday",
            work_tasks=[],
            personal_tasks=[],
            other_tasks=[],
            events=[
                Event(
                    title="Meeting",
                    start=datetime.combine(today, time(10, 0)),
                    end=datetime.combine(today, time(11, 0)),
                    location="",
                    calendar="Work",
                    all_day=False,
                    source="test",
                ),
            ],
            free_slots=[],
            is_work_hours=True,
            work_hours_str="09:00-17:00",
        )

        sections = format_briefing_sections(data)
        assert "Meeting" in sections["calendar"]

    def test_formats_time_context_work_hours(self, today):
        data = BriefingData(
            date=today,
            day_of_week="Wednesday",
            work_tasks=[],
            personal_tasks=[],
            other_tasks=[],
            events=[],
            free_slots=[],
            is_work_hours=True,
            work_hours_str="09:00-17:00",
        )

        sections = format_briefing_sections(data)
        assert "during work hours" in sections["time_context"]
        assert "Focus on work tasks" in sections["time_context"]

    def test_formats_time_context_outside_work(self, today):
        data = BriefingData(
            date=today,
            day_of_week="Wednesday",
            work_tasks=[],
            personal_tasks=[],
            other_tasks=[],
            events=[],
            free_slots=[],
            is_work_hours=False,
            work_hours_str="09:00-17:00",
        )

        sections = format_briefing_sections(data)
        assert "outside work hours" in sections["time_context"]
        assert "Focus on personal tasks" in sections["time_context"]
