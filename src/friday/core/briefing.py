"""Pure briefing assembly logic - no I/O dependencies."""

from dataclasses import dataclass
from datetime import date, datetime

from .tasks import Task, filter_actionable, categorize_tasks, sort_by_priority
from .calendar import Event, TimeSlot, find_free_slots


@dataclass
class BriefingData:
    """Assembled briefing data ready for formatting."""

    date: date
    day_of_week: str
    work_tasks: list[Task]
    personal_tasks: list[Task]
    other_tasks: list[Task]
    events: list[Event]
    free_slots: list[TimeSlot]
    is_work_hours: bool
    work_hours_str: str


def assemble_briefing(
    tasks: list[Task],
    events: list[Event],
    work_task_lists: list[str],
    personal_task_lists: list[str],
    work_start: int,
    work_end: int,
    as_of: datetime | None = None,
    urgent_days: int = 3,
) -> BriefingData:
    """
    Assemble briefing data from raw tasks and events.

    Pure function - no I/O. Handles all filtering, sorting, categorization.
    """
    as_of = as_of or datetime.now()
    today = as_of.date()

    # Filter to actionable tasks
    actionable = filter_actionable(tasks, urgent_days, today)

    # Categorize by work/personal
    work, personal, other = categorize_tasks(actionable, work_task_lists, personal_task_lists)

    # Sort each category by priority
    work = sort_by_priority(work, today)
    personal = sort_by_priority(personal, today)
    other = sort_by_priority(other, today)

    # Find free time slots
    free_slots = find_free_slots(
        events,
        work_start=work_start,
        work_end=work_end,
        min_duration=30,
        target_date=today,
    )

    return BriefingData(
        date=today,
        day_of_week=today.strftime("%A"),
        work_tasks=work,
        personal_tasks=personal,
        other_tasks=other,
        events=events,
        free_slots=free_slots,
        is_work_hours=work_start <= as_of.hour < work_end,
        work_hours_str=f"{work_start:02d}:00-{work_end:02d}:00",
    )


def format_task_line(task: Task, as_of: date | None = None) -> str:
    """
    Format a single task for display in briefing.

    Pure function - no I/O.
    """
    as_of = as_of or date.today()
    days = task.days_until_due(as_of)

    urgency = ""
    if days is not None:
        if days < 0:
            urgency = f"OVERDUE by {-days}d"
        elif days == 0:
            urgency = "due TODAY"
        else:
            urgency = f"due in {days}d"

    quadrant = task.quadrant_label(as_of=as_of)
    return f"- [{quadrant}] {task.title} ({urgency}, project: {task.project_name})"


def format_event_line(event: Event) -> str:
    """
    Format a single event for display.

    Pure function - no I/O.
    """
    time_str = event.format_time()
    end_str = ""
    if event.end and not event.all_day:
        end_str = f" - {event.end.strftime('%H:%M')}"

    location = f" @ {event.location}" if event.location else ""
    return f"- {time_str}{end_str} {event.title}{location}"


def format_briefing_sections(data: BriefingData) -> dict[str, str]:
    """
    Format briefing data into markdown sections.

    Pure function - no I/O.
    Returns dict with keys: tasks, calendar, free_slots, time_context
    """
    # Format tasks by category
    work_md = "\n".join(format_task_line(t, data.date) for t in data.work_tasks) or "None"
    personal_md = "\n".join(format_task_line(t, data.date) for t in data.personal_tasks) or "None"
    other_md = "\n".join(format_task_line(t, data.date) for t in data.other_tasks) or "None"

    tasks_md = f"""### Work Tasks
{work_md}

### Personal Tasks
{personal_md}

### Other
{other_md}"""

    # Format calendar
    calendar_md = "\n".join(format_event_line(e) for e in data.events) or "No events today."

    # Format free slots
    free_slots_md = "\n".join(f"- {slot.format()}" for slot in data.free_slots) or "No free slots today."

    # Time context
    context = "during work hours" if data.is_work_hours else "outside work hours"
    focus = "work" if data.is_work_hours else "personal"
    time_context = f"Currently {context} ({data.work_hours_str}). Focus on {focus} tasks."

    return {
        "tasks": tasks_md,
        "calendar": calendar_md,
        "free_slots": free_slots_md,
        "time_context": time_context,
    }
