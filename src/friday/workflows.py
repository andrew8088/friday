"""Shared workflow layer between CLI and Telegram.

Each generate_* function: compiles a prompt, runs Claude, saves to journal,
and returns the output string.
"""

from datetime import date, datetime, timedelta
from pathlib import Path

from .adapters.claude_cli import ClaudeCLIService
from .adapters.file_journal import FileJournalStore
from .config import FRIDAY_HOME, Config, load_config
from . import calendar as cal
from .ticktick import AuthenticationError, TickTickClient


def get_journal(config: Config) -> FileJournalStore:
    """Resolve journal directory from config."""
    if config.daily_journal_dir:
        return FileJournalStore(Path(config.daily_journal_dir).expanduser())
    return FileJournalStore(FRIDAY_HOME / "journal" / "daily")


def generate_briefing(config: Config) -> str:
    """Compile briefing prompt, run Claude, save to journal, return output."""
    prompt = compile_briefing()
    claude = ClaudeCLIService(cwd=FRIDAY_HOME)
    output = claude.generate(prompt).strip()
    journal = get_journal(config)
    journal.append(date.today(), "Morning Briefing", output)
    return output


def generate_weekly_plan(config: Config) -> str:
    """Compile weekly plan prompt, run Claude, save to journal, return output."""
    prompt = compile_week()
    claude = ClaudeCLIService(cwd=FRIDAY_HOME)
    output = claude.generate(prompt).strip()
    journal = get_journal(config)
    journal.append(date.today(), "Weekly Plan", output)
    return output


def generate_weekly_review(config: Config) -> str:
    """Compile weekly review prompt, run Claude, save to journal, return output."""
    prompt = compile_review()
    claude = ClaudeCLIService(cwd=FRIDAY_HOME)
    output = claude.generate(prompt).strip()
    journal = get_journal(config)
    journal.append(date.today(), "Weekly Review", output)
    return output


# ============== Prompt Compilation ==============


def compile_briefing() -> str:
    """Compile the daily briefing prompt."""
    config = load_config()
    today = date.today()
    now = datetime.now()

    # Parse work hours
    work_start_str, work_end_str = config.work_hours.split("-")
    work_start = int(work_start_str.split(":")[0])
    work_end = int(work_end_str.split(":")[0])
    is_work_hours = work_start <= now.hour < work_end

    # Fetch all tasks and filter to actionable ones
    actionable_tasks_md = ""
    work_tasks = []
    personal_tasks = []

    notes_md = ""
    try:
        from .core.tasks import filter_actionable, filter_notes

        client = TickTickClient()
        all_tasks = client.get_all_tasks()

        actionable = filter_actionable(all_tasks, urgent_days=3)

        # Split by work/personal
        work_tasks = [t for t in actionable if t.project_name in config.work_task_lists]
        personal_tasks = [t for t in actionable if t.project_name in config.personal_task_lists]
        other_tasks = [t for t in actionable if t.project_name not in config.work_task_lists and t.project_name not in config.personal_task_lists]

        def format_task(t):
            days_until = (t.due_date - today).days if t.due_date else None
            urgency = ""
            if days_until is not None:
                if days_until < 0:
                    urgency = f"OVERDUE by {-days_until}d"
                elif days_until == 0:
                    urgency = "due TODAY"
                else:
                    urgency = f"due in {days_until}d"
            quadrant = t.quadrant_label()
            return f"- [{quadrant}] {t.title} ({urgency}, project: {t.project_name})"

        work_tasks_md = "\n".join(format_task(t) for t in work_tasks) or "None"
        personal_tasks_md = "\n".join(format_task(t) for t in personal_tasks) or "None"
        other_tasks_md = "\n".join(format_task(t) for t in other_tasks) or "None"

        actionable_tasks_md = f"""### Work Tasks ({', '.join(config.work_task_lists)})
{work_tasks_md}

### Personal Tasks ({', '.join(config.personal_task_lists)})
{personal_tasks_md}

### Other
{other_tasks_md}"""

        # Notes = time-relevant reminders, not tasks to complete
        notes = filter_notes(all_tasks, urgent_days=3)
        if notes:
            def format_note(t):
                days_until = (t.due_date - today).days
                if days_until < 0:
                    when = f"since {-days_until}d ago"
                elif days_until == 0:
                    when = "today"
                else:
                    when = f"in {days_until}d"
                return f"- {t.title} ({when}, project: {t.project_name})"
            notes_md = "\n".join(format_note(n) for n in notes)

    except AuthenticationError:
        actionable_tasks_md = "(TickTick not authenticated - run 'friday auth')"

    # Calendar events
    events = cal.fetch_today(config)
    events = cal.drop_redundant_ooo(events)
    calendar_md = "\n".join(
        f"- {e.format_time()} - {e.end.strftime('%H:%M') if e.end and not e.all_day else ''} {e.title}".strip()
        + (f" @ {e.location}" if e.location else "")
        for e in events
    ) or "No events today."

    # Find free time slots
    free_slots = cal.find_free_slots(events, work_start=work_start, work_end=work_end, min_duration=30)
    free_slots_md = "\n".join(f"- {slot.format()}" for slot in free_slots) or "No free slots today."

    # Context for Claude
    time_context = "during work hours" if is_work_hours else "outside work hours"
    task_focus = "work" if is_work_hours else "personal"

    template = FRIDAY_HOME / "templates" / "daily-briefing.md"
    if template.exists():
        prompt = template.read_text()
        prompt = prompt.replace("{{DATE}}", today.isoformat())
        prompt = prompt.replace("{{DAY_OF_WEEK}}", today.strftime("%A"))
        prompt = prompt.replace("{{YESTERDAY_CONTEXT}}", "")
        prompt = prompt.replace("{{TASKS}}", actionable_tasks_md)
        prompt = prompt.replace("{{NOTES}}", notes_md or "None")
        prompt = prompt.replace("{{CALENDAR}}", calendar_md)
        prompt = prompt.replace("{{FREE_SLOTS}}", free_slots_md)
        prompt = prompt.replace("{{TIME_CONTEXT}}", f"Currently {time_context} ({config.work_hours}). Focus on {task_focus} tasks.")
        return prompt

    # Fallback inline template
    return f"""You are Friday, a personal assistant. Generate a morning briefing.

## Date
{today.strftime("%A, %B %d, %Y")}

## Context
Currently {time_context} ({config.work_hours}). Focus on {task_focus} tasks.

## Today's Calendar
{calendar_md}

## Free Time Slots
{free_slots_md}

## Actionable Tasks
These are tasks due within 3 days OR marked urgent+important (Q1).

{actionable_tasks_md}

## Reminders (Notes)
These are not tasks to complete — they are time-relevant info to keep in mind.
{notes_md or "None"}

## Instructions
1. For each actionable task, recommend a specific free time slot to work on it
2. Match task type to time of day (work tasks during work hours, personal outside)
3. Prioritize Q1 (Do) tasks first, then by due date
4. Flag any tasks that won't fit in today's free slots
5. Be specific with times, not vague
"""


def compile_review() -> str:
    """Compile the weekly review prompt."""
    config = load_config()
    today = date.today()

    # Get this week's journals (which now include recaps)
    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"

    accomplishments = []
    for journal_file in sorted(journal_dir.glob("*.md")):
        try:
            journal_date = date.fromisoformat(journal_file.stem)
            days_ago = (today - journal_date).days
            if 0 <= days_ago <= 7:
                accomplishments.append(f"### {journal_date}\n{journal_file.read_text()}")
        except ValueError:
            continue

    accomplishments_md = "\n\n".join(accomplishments) or "No journal entries this week."

    # Get overdue tasks
    try:
        client = TickTickClient()
        tasks = client.get_priority_tasks()
        overdue = [t for t in tasks if t.due_date and t.due_date < today]
        overdue_md = "\n".join(f"- {t.title} (due: {t.due_date})" for t in overdue) or "None"

        inbox_tasks = client.get_inbox_tasks()
        inbox_md = "\n".join(f"- {t.title}" for t in inbox_tasks) or "Inbox is empty"
    except AuthenticationError:
        overdue_md = "(TickTick not authenticated)"
        inbox_md = "(TickTick not authenticated)"

    # Next week's calendar
    next_week_events = cal.fetch_week(config)
    calendar_md = "\n".join(
        f"- {e.start.strftime('%a %m/%d %H:%M')} {e.title}"
        for e in next_week_events
    ) or "No events scheduled."

    template = FRIDAY_HOME / "templates" / "weekly-review.md"
    if template.exists():
        prompt = template.read_text()
        prompt = prompt.replace("{{DATE}}", today.isoformat())
        prompt = prompt.replace("{{DAY_OF_WEEK}}", today.strftime("%A"))
        prompt = prompt.replace("{{RECAP_SUMMARY}}", "")
        prompt = prompt.replace("{{ACCOMPLISHMENTS}}", accomplishments_md)
        prompt = prompt.replace("{{OVERDUE_TASKS}}", overdue_md)
        prompt = prompt.replace("{{STUCK_TASKS}}", "N/A")
        prompt = prompt.replace("{{INBOX_TASKS}}", inbox_md)
        prompt = prompt.replace("{{NEXT_WEEK_CALENDAR}}", calendar_md)
        return prompt

    # Fallback
    return f"""You are Friday. Generate a weekly review.

## Week Ending {today}

## This Week's Journals
{accomplishments_md}

## Overdue Tasks
{overdue_md}

## Inbox Items
{inbox_md}

## Next Week's Calendar
{calendar_md}

## Instructions
1. Summarize accomplishments
2. Identify incomplete items and recommend action
3. Flag calendar conflicts for next week
4. Suggest 3 focus areas for the coming week
"""


def compile_week() -> str:
    """Compile the weekly planning prompt."""
    config = load_config()
    today = date.today()

    # Days remaining through Saturday (weekday 5 = Saturday)
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0 and today.weekday() == 5:
        days_until_saturday = 0  # It's Saturday, show today only
    days_remaining = days_until_saturday + 1  # inclusive

    # Parse work hours
    work_start_str, work_end_str = config.work_hours.split("-")
    work_start = int(work_start_str.split(":")[0])
    work_end = int(work_end_str.split(":")[0])

    # Calendar events with day headers
    events = cal.fetch_all_events(config, days=days_remaining)
    events = cal.drop_redundant_ooo(events)
    calendar_lines = []
    current_date = None
    day_events = {}  # date -> list of events for free slot calc
    for e in events:
        event_date = e.start.date()
        if event_date not in day_events:
            day_events[event_date] = []
        day_events[event_date].append(e)
        if event_date != current_date:
            if current_date is not None:
                calendar_lines.append("")
            calendar_lines.append(f"### {event_date.strftime('%A, %B %d')}")
            current_date = event_date
        time_str = e.format_time()
        loc = f" @ {e.location}" if e.location else ""
        calendar_lines.append(f"- {time_str} {e.title}{loc}")
    calendar_md = "\n".join(calendar_lines) or "No events this week."

    # Free slots per workday
    free_slots_lines = []
    for i in range(days_remaining):
        d = today + timedelta(days=i)
        if d.weekday() >= 5:  # Skip weekends
            continue
        day_evts = day_events.get(d, [])
        slots = cal.find_free_slots(day_evts, work_start=work_start, work_end=work_end, min_duration=30)
        if slots:
            free_slots_lines.append(f"**{d.strftime('%A, %B %d')}**: {', '.join(s.format() for s in slots)}")
        else:
            free_slots_lines.append(f"**{d.strftime('%A, %B %d')}**: No free slots")
    free_slots_md = "\n".join(free_slots_lines) or "No workdays remaining this week."

    # Tasks: due before end of Saturday OR priority >= 3
    end_of_saturday = today + timedelta(days=days_until_saturday)
    tasks_md = ""
    notes_md = ""
    try:
        from .core.tasks import filter_notes

        client = TickTickClient()
        all_tasks = client.get_all_tasks()

        week_tasks = [
            t for t in all_tasks
            if not t.is_note
            and ((t.due_date and t.due_date <= end_of_saturday) or t.priority >= 3)
        ]

        def format_task(t):
            days_until = (t.due_date - today).days if t.due_date else None
            urgency = ""
            if days_until is not None:
                if days_until < 0:
                    urgency = f"OVERDUE by {-days_until}d"
                elif days_until == 0:
                    urgency = "due TODAY"
                else:
                    urgency = f"due in {days_until}d"
            quadrant = t.quadrant_label()
            return f"- [{quadrant}] {t.title} ({urgency}, project: {t.project_name})"

        work_tasks = [t for t in week_tasks if t.project_name in config.work_task_lists]
        personal_tasks = [t for t in week_tasks if t.project_name in config.personal_task_lists]
        other_tasks = [t for t in week_tasks if t.project_name not in config.work_task_lists and t.project_name not in config.personal_task_lists]

        work_md = "\n".join(format_task(t) for t in work_tasks) or "None"
        personal_md = "\n".join(format_task(t) for t in personal_tasks) or "None"
        other_md = "\n".join(format_task(t) for t in other_tasks) or "None"

        tasks_md = f"""### Work Tasks
{work_md}

### Personal Tasks
{personal_md}

### Other
{other_md}"""

        notes = filter_notes(all_tasks, urgent_days=days_remaining)
        if notes:
            def format_note(t):
                days_until = (t.due_date - today).days
                if days_until < 0:
                    when = f"since {-days_until}d ago"
                elif days_until == 0:
                    when = "today"
                else:
                    when = f"in {days_until}d"
                return f"- {t.title} ({when}, project: {t.project_name})"
            notes_md = "\n".join(format_note(n) for n in notes)
    except AuthenticationError:
        tasks_md = "(TickTick not authenticated - run 'friday auth')"

    template = FRIDAY_HOME / "templates" / "weekly-planning.md"
    if template.exists():
        prompt = template.read_text()
        prompt = prompt.replace("{{DATE}}", today.isoformat())
        prompt = prompt.replace("{{DAY_OF_WEEK}}", today.strftime("%A"))
        prompt = prompt.replace("{{CALENDAR}}", calendar_md)
        prompt = prompt.replace("{{FREE_SLOTS}}", free_slots_md)
        prompt = prompt.replace("{{TASKS}}", tasks_md)
        prompt = prompt.replace("{{NOTES}}", notes_md or "None")
        return prompt

    # Fallback inline template
    return f"""You are Friday, a personal assistant. Generate a weekly plan.

## Week of {today.strftime("%A, %B %d, %Y")} through Saturday

## Calendar
{calendar_md}

## Free Time Slots (Workdays)
{free_slots_md}

## Tasks (due this week or high priority)
{tasks_md}

## Reminders (Notes)
These are not tasks to complete — they are time-relevant info to keep in mind.
{notes_md or "None"}

## Instructions
1. Suggest 3 focus areas for the rest of the week
2. Flag any scheduling risks or conflicts
3. Recommend specific time blocks for high-priority tasks
4. Note any overloaded days and suggest redistribution
5. Be specific with times and days, not vague
"""


def compile_recap_prompt(target: date, config: Config, journal_dir: Path) -> str:
    """Compile context for deep recap mode."""
    from .recap import determine_recap_mode, RecapMode

    # Determine mode
    try:
        client = TickTickClient()
        ticktick_available = True
        all_tasks = client.get_all_tasks()
        # Get tasks completed today (high priority or due today that are marked done)
        completed = [t for t in all_tasks if t.due_date == target]
    except AuthenticationError:
        ticktick_available = False
        completed = []

    mode = determine_recap_mode(target, journal_dir, ticktick_available)

    # Build context based on mode
    sections = [
        f"# Evening Recap — {target.strftime('%A, %B %d, %Y')}",
        f"**Mode:** {mode.value}",
    ]

    if mode == RecapMode.FULL:
        # Include morning briefing
        briefing_file = journal_dir / f"{target.isoformat()}.md"
        if briefing_file.exists():
            briefing = briefing_file.read_text()
            # Truncate if very long
            if len(briefing) > 2000:
                briefing = briefing[:2000] + "\n\n[... truncated ...]"
            sections.append(f"## This Morning's Plan\n\n{briefing}")

    if ticktick_available and completed:
        completed_md = "\n".join(f"- {t.title}" for t in completed[:10])
        sections.append(f"## Tasks Due Today\n\n{completed_md}")

    # Instructions based on mode
    if mode == RecapMode.FULL:
        sections.append("""## Your Task

Guide me through an evening reflection by comparing my morning plan to what actually happened.

1. Ask what got done as planned
2. Ask what didn't happen and why
3. Ask about any wins not in the original plan
4. Help me crystallize one focus for tomorrow

After our conversation, generate a recap section with YAML frontmatter containing:
- date, mode, wins (list), blockers (list), energy, tags
- A ## Reflection section summarizing our discussion
- A ## Tomorrow's Focus section with the intention we identified

Keep the conversation brief (5-7 exchanges). Be curious, not judgmental.""")
    elif mode == RecapMode.TASKS_ONLY:
        sections.append("""## Your Task

Guide me through an evening reflection based on today's tasks.

1. Ask what felt like a win today
2. Ask what was harder than expected
3. Help me set one focus for tomorrow

After our conversation, generate a recap section with YAML frontmatter.
Keep the conversation brief (5-7 exchanges).""")
    else:
        sections.append("""## Your Task

Guide me through an open evening reflection.

1. Ask how today went overall
2. Ask what's worth remembering
3. Ask what I would do differently
4. Help me set one intention for tomorrow

After our conversation, generate a recap section with YAML frontmatter.
Keep the conversation brief (5-7 exchanges).""")

    journal_file = journal_dir / f"{target.isoformat()}.md"
    sections.append(f"\nAppend the final recap (with '## Evening Recap' header) to the daily journal: {journal_file}")

    return "\n\n".join(sections)
