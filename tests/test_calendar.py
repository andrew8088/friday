"""Tests for core calendar logic."""

from datetime import date, datetime, time, timedelta

import pytest

from friday.core.calendar import (
    Event,
    TimeSlot,
    find_free_slots,
    filter_events_by_date,
    sort_events_by_start,
    find_conflicts,
    is_during_hours,
)


# Fixtures
@pytest.fixture
def today():
    return date(2025, 1, 15)


@pytest.fixture
def make_event(today):
    """Factory for creating events."""
    def _make(
        title: str,
        start_hour: int,
        end_hour: int,
        all_day: bool = False,
    ) -> Event:
        start = datetime.combine(today, time(start_hour, 0))
        end = datetime.combine(today, time(end_hour, 0)) if end_hour else None
        return Event(
            title=title,
            start=start,
            end=end,
            location="",
            calendar="Test",
            all_day=all_day,
            source="test",
        )
    return _make


# Event class tests
class TestEvent:
    def test_format_time_regular(self, today):
        event = Event(
            title="Meeting",
            start=datetime.combine(today, time(14, 30)),
            end=datetime.combine(today, time(15, 30)),
            location="",
            calendar="Test",
            all_day=False,
            source="test",
        )
        assert event.format_time() == "14:30"

    def test_format_time_all_day(self, today):
        event = Event(
            title="Holiday",
            start=datetime.combine(today, time(0, 0)),
            end=datetime.combine(today, time(23, 59)),
            location="",
            calendar="Test",
            all_day=True,
            source="test",
        )
        assert event.format_time() == "All day"

    def test_duration_minutes(self, today):
        event = Event(
            title="Meeting",
            start=datetime.combine(today, time(14, 0)),
            end=datetime.combine(today, time(15, 30)),
            location="",
            calendar="Test",
            all_day=False,
            source="test",
        )
        assert event.duration_minutes() == 90

    def test_duration_minutes_no_end(self, today):
        event = Event(
            title="Meeting",
            start=datetime.combine(today, time(14, 0)),
            end=None,
            location="",
            calendar="Test",
            all_day=False,
            source="test",
        )
        assert event.duration_minutes() is None


# TimeSlot class tests
class TestTimeSlot:
    def test_duration_minutes(self, today):
        slot = TimeSlot(
            start=datetime.combine(today, time(9, 0)),
            end=datetime.combine(today, time(10, 30)),
        )
        assert slot.duration_minutes() == 90

    def test_format(self, today):
        slot = TimeSlot(
            start=datetime.combine(today, time(9, 0)),
            end=datetime.combine(today, time(10, 30)),
        )
        assert slot.format() == "09:00-10:30 (90 min)"

    def test_contains(self, today):
        slot = TimeSlot(
            start=datetime.combine(today, time(9, 0)),
            end=datetime.combine(today, time(12, 0)),
        )
        assert slot.contains(datetime.combine(today, time(10, 0))) is True
        assert slot.contains(datetime.combine(today, time(9, 0))) is True
        assert slot.contains(datetime.combine(today, time(12, 0))) is False
        assert slot.contains(datetime.combine(today, time(8, 0))) is False

    def test_overlaps(self, today):
        slot1 = TimeSlot(
            start=datetime.combine(today, time(9, 0)),
            end=datetime.combine(today, time(11, 0)),
        )
        slot2 = TimeSlot(
            start=datetime.combine(today, time(10, 0)),
            end=datetime.combine(today, time(12, 0)),
        )
        slot3 = TimeSlot(
            start=datetime.combine(today, time(11, 0)),
            end=datetime.combine(today, time(13, 0)),
        )

        assert slot1.overlaps(slot2) is True
        assert slot2.overlaps(slot1) is True
        assert slot1.overlaps(slot3) is False  # Adjacent, not overlapping


# find_free_slots tests
class TestFindFreeSlots:
    def test_no_events_returns_full_day(self, today):
        """With no events, the entire work day is free."""
        slots = find_free_slots([], work_start=9, work_end=17, target_date=today)
        assert len(slots) == 1
        assert slots[0].start.hour == 9
        assert slots[0].end.hour == 17
        assert slots[0].duration_minutes() == 480

    def test_single_event_middle_of_day(self, make_event):
        """Single event in middle creates two free slots."""
        events = [make_event("Meeting", 12, 13)]
        slots = find_free_slots(events, work_start=9, work_end=17)

        assert len(slots) == 2
        # Morning slot: 9-12
        assert slots[0].start.hour == 9
        assert slots[0].end.hour == 12
        # Afternoon slot: 13-17
        assert slots[1].start.hour == 13
        assert slots[1].end.hour == 17

    def test_event_at_start_of_day(self, make_event):
        """Event at start of day creates one free slot after."""
        events = [make_event("Morning standup", 9, 10)]
        slots = find_free_slots(events, work_start=9, work_end=17)

        assert len(slots) == 1
        assert slots[0].start.hour == 10
        assert slots[0].end.hour == 17

    def test_event_at_end_of_day(self, make_event):
        """Event at end of day creates one free slot before."""
        events = [make_event("EOD meeting", 16, 17)]
        slots = find_free_slots(events, work_start=9, work_end=17)

        assert len(slots) == 1
        assert slots[0].start.hour == 9
        assert slots[0].end.hour == 16

    def test_back_to_back_events(self, make_event):
        """Back-to-back events create no gap between them."""
        events = [
            make_event("Meeting 1", 10, 11),
            make_event("Meeting 2", 11, 12),
        ]
        slots = find_free_slots(events, work_start=9, work_end=17)

        assert len(slots) == 2
        # Before meetings
        assert slots[0].start.hour == 9
        assert slots[0].end.hour == 10
        # After meetings
        assert slots[1].start.hour == 12
        assert slots[1].end.hour == 17

    def test_overlapping_events(self, make_event):
        """Overlapping events are handled correctly."""
        events = [
            make_event("Meeting 1", 10, 12),
            make_event("Meeting 2", 11, 13),
        ]
        slots = find_free_slots(events, work_start=9, work_end=17)

        assert len(slots) == 2
        assert slots[0].end.hour == 10  # Before first meeting
        assert slots[1].start.hour == 13  # After second meeting ends

    def test_min_duration_filters_short_gaps(self, make_event):
        """Short gaps below min_duration are excluded."""
        events = [
            make_event("Meeting 1", 9, 10),
            make_event("Meeting 2", 10, 11),  # No gap - 0 min
        ]
        slots = find_free_slots(events, work_start=9, work_end=12, min_duration=30)

        assert len(slots) == 1
        assert slots[0].start.hour == 11
        assert slots[0].end.hour == 12

    def test_all_day_events_ignored(self, today):
        """All-day events don't block time slots."""
        all_day = Event(
            title="Holiday",
            start=datetime.combine(today, time(0, 0)),
            end=datetime.combine(today, time(23, 59)),
            location="",
            calendar="Test",
            all_day=True,
            source="test",
        )
        slots = find_free_slots([all_day], work_start=9, work_end=17, target_date=today)

        # Should still have full day free since all-day events are excluded
        assert len(slots) == 1
        assert slots[0].duration_minutes() == 480

    def test_events_outside_work_hours_ignored(self, make_event):
        """Events outside work hours don't affect free slots."""
        events = [
            make_event("Early meeting", 7, 8),  # Before work
            make_event("Late meeting", 18, 19),  # After work
        ]
        slots = find_free_slots(events, work_start=9, work_end=17)

        assert len(slots) == 1
        assert slots[0].duration_minutes() == 480


# filter_events_by_date tests
class TestFilterEventsByDate:
    def test_filters_to_single_date(self, today):
        events = [
            Event(
                title="Today",
                start=datetime.combine(today, time(10, 0)),
                end=datetime.combine(today, time(11, 0)),
                location="",
                calendar="Test",
                all_day=False,
                source="test",
            ),
            Event(
                title="Tomorrow",
                start=datetime.combine(today + timedelta(days=1), time(10, 0)),
                end=datetime.combine(today + timedelta(days=1), time(11, 0)),
                location="",
                calendar="Test",
                all_day=False,
                source="test",
            ),
        ]

        filtered = filter_events_by_date(events, today)
        assert len(filtered) == 1
        assert filtered[0].title == "Today"

    def test_filters_to_date_range(self, today):
        events = [
            Event(
                title="Day 1",
                start=datetime.combine(today, time(10, 0)),
                end=datetime.combine(today, time(11, 0)),
                location="",
                calendar="Test",
                all_day=False,
                source="test",
            ),
            Event(
                title="Day 3",
                start=datetime.combine(today + timedelta(days=2), time(10, 0)),
                end=datetime.combine(today + timedelta(days=2), time(11, 0)),
                location="",
                calendar="Test",
                all_day=False,
                source="test",
            ),
            Event(
                title="Day 5",
                start=datetime.combine(today + timedelta(days=4), time(10, 0)),
                end=datetime.combine(today + timedelta(days=4), time(11, 0)),
                location="",
                calendar="Test",
                all_day=False,
                source="test",
            ),
        ]

        filtered = filter_events_by_date(events, today, today + timedelta(days=3))
        assert len(filtered) == 2
        titles = [e.title for e in filtered]
        assert "Day 1" in titles
        assert "Day 3" in titles
        assert "Day 5" not in titles


# sort_events_by_start tests
class TestSortEventsByStart:
    def test_sorts_chronologically(self, today):
        events = [
            Event(
                title="Third",
                start=datetime.combine(today, time(15, 0)),
                end=None,
                location="",
                calendar="Test",
                all_day=False,
                source="test",
            ),
            Event(
                title="First",
                start=datetime.combine(today, time(9, 0)),
                end=None,
                location="",
                calendar="Test",
                all_day=False,
                source="test",
            ),
            Event(
                title="Second",
                start=datetime.combine(today, time(12, 0)),
                end=None,
                location="",
                calendar="Test",
                all_day=False,
                source="test",
            ),
        ]

        sorted_events = sort_events_by_start(events)
        assert [e.title for e in sorted_events] == ["First", "Second", "Third"]


# find_conflicts tests
class TestFindConflicts:
    def test_no_conflicts(self, make_event):
        events = [
            make_event("Meeting 1", 9, 10),
            make_event("Meeting 2", 11, 12),
        ]
        conflicts = find_conflicts(events)
        assert len(conflicts) == 0

    def test_adjacent_events_no_conflict(self, make_event):
        events = [
            make_event("Meeting 1", 9, 10),
            make_event("Meeting 2", 10, 11),
        ]
        conflicts = find_conflicts(events)
        assert len(conflicts) == 0

    def test_overlapping_events_conflict(self, make_event):
        events = [
            make_event("Meeting 1", 9, 11),
            make_event("Meeting 2", 10, 12),
        ]
        conflicts = find_conflicts(events)
        assert len(conflicts) == 1
        assert conflicts[0][0].title == "Meeting 1"
        assert conflicts[0][1].title == "Meeting 2"

    def test_multiple_conflicts(self, make_event):
        events = [
            make_event("Meeting 1", 9, 12),
            make_event("Meeting 2", 10, 11),
            make_event("Meeting 3", 11, 13),
        ]
        conflicts = find_conflicts(events)
        # Meeting 1 conflicts with 2 and 3
        assert len(conflicts) == 2


# is_during_hours tests
class TestIsDuringHours:
    def test_within_hours(self, today):
        dt = datetime.combine(today, time(10, 30))
        assert is_during_hours(dt, 9, 17) is True

    def test_at_start_boundary(self, today):
        dt = datetime.combine(today, time(9, 0))
        assert is_during_hours(dt, 9, 17) is True

    def test_before_start(self, today):
        dt = datetime.combine(today, time(8, 59))
        assert is_during_hours(dt, 9, 17) is False

    def test_at_end_boundary(self, today):
        dt = datetime.combine(today, time(17, 0))
        assert is_during_hours(dt, 9, 17) is False  # End is exclusive

    def test_after_end(self, today):
        dt = datetime.combine(today, time(18, 0))
        assert is_during_hours(dt, 9, 17) is False
