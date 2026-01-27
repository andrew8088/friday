"""Friday CLI - Personal Assistant."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import click

from . import calendar as cal
from .config import DATA_DIR, FRIDAY_HOME, load_config, Tokens
from .ticktick import AuthenticationError, TickTickClient, authorize


@click.group()
@click.version_option()
def main():
    """Friday - Personal Assistant CLI."""
    pass


@main.command()
def auth():
    """Authenticate with TickTick."""
    try:
        authorize()
    except AuthenticationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def tasks(as_json: bool):
    """List today's priority tasks."""
    try:
        client = TickTickClient()
        priority_tasks = client.get_priority_tasks()
    except AuthenticationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(
            json.dumps(
                [
                    {
                        "id": t.id,
                        "title": t.title,
                        "priority": t.priority,
                        "due_date": t.due_date.isoformat() if t.due_date else None,
                        "project": t.project_name,
                    }
                    for t in priority_tasks
                ],
                indent=2,
            )
        )
    else:
        if not priority_tasks:
            click.echo("No priority tasks for today.")
            return

        for task in priority_tasks:
            priority_marker = "!" * task.priority if task.priority else " "
            due = f" (due {task.due_date})" if task.due_date else ""
            click.echo(f"[{priority_marker:3}] {task.title}{due}")


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def inbox(as_json: bool):
    """List inbox tasks."""
    try:
        client = TickTickClient()
        inbox_tasks = client.get_inbox_tasks()
    except AuthenticationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(
            json.dumps(
                [
                    {
                        "id": t.id,
                        "title": t.title,
                        "priority": t.priority,
                    }
                    for t in inbox_tasks
                ],
                indent=2,
            )
        )
    else:
        if not inbox_tasks:
            click.echo("Inbox is empty.")
            return

        for task in inbox_tasks:
            click.echo(f"• {task.title}")


@main.group(invoke_without_command=True)
@click.pass_context
def calendar(ctx):
    """Show calendar events."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(calendar_day)


def _show_events(events: list, as_json: bool, empty_msg: str = "No events.") -> None:
    """Shared event display logic."""
    if as_json:
        click.echo(
            json.dumps(
                [
                    {
                        "title": e.title,
                        "start": e.start.isoformat(),
                        "end": e.end.isoformat() if e.end else None,
                        "location": e.location,
                        "calendar": e.calendar,
                        "all_day": e.all_day,
                    }
                    for e in events
                ],
                indent=2,
            )
        )
    else:
        if not events:
            click.echo(empty_msg)
            return

        current_date = None
        for event in events:
            event_date = event.start.date()
            if event_date != current_date:
                if current_date is not None:
                    click.echo()
                click.echo(f"### {event_date.strftime('%A, %B %d')}")
                current_date = event_date

            time_str = event.format_time()
            loc = f" @ {event.location}" if event.location else ""
            click.echo(f"  {time_str:8} {event.title}{loc}")


@calendar.command("day")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def calendar_day(as_json: bool = False):
    """Show today's events."""
    config = load_config()
    events = cal.fetch_all_events(config, days=1)
    _show_events(events, as_json, "No events today.")


@calendar.command("week")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def calendar_week(as_json: bool = False):
    """Show this week's events."""
    config = load_config()
    events = cal.fetch_all_events(config, days=7)
    _show_events(events, as_json, "No events this week.")


@main.command()
def morning():
    """Generate daily briefing."""
    config = load_config()
    today = date.today().isoformat()

    # Use configured journal dir or default
    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"

    journal_dir.mkdir(parents=True, exist_ok=True)
    output_file = journal_dir / f"{today}.md"

    prompt = compile_briefing()

    # Pipe to claude with streaming output
    try:
        proc = subprocess.Popen(
            ["claude", "-p", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send prompt and close stdin
        proc.stdin.write(prompt)
        proc.stdin.close()

        # Stream output in real-time while collecting it
        output_lines = []
        for line in proc.stdout:
            click.echo(line, nl=False)
            output_lines.append(line)

        proc.wait()
        output = "".join(output_lines)

        if proc.returncode != 0:
            stderr = proc.stderr.read()
            click.echo(f"Error running claude: {stderr}", err=True)
            sys.exit(1)

        # Append if file exists, otherwise create
        if output_file.exists():
            with open(output_file, "a") as f:
                f.write(f"\n\n---\n\n{output}")
        else:
            output_file.write_text(output)

    except FileNotFoundError:
        click.echo("Error: 'claude' command not found", err=True)
        sys.exit(1)


@main.command()
def review():
    """Run weekly review."""
    from datetime import datetime

    week = datetime.now().strftime("%Y-W%V")
    review_dir = FRIDAY_HOME / "reviews" / "weekly"
    review_dir.mkdir(parents=True, exist_ok=True)
    output_file = review_dir / f"{week}.md"

    prompt = compile_review()

    try:
        proc = subprocess.Popen(
            ["claude", "-p", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        proc.stdin.write(prompt)
        proc.stdin.close()

        output_lines = []
        for line in proc.stdout:
            click.echo(line, nl=False)
            output_lines.append(line)

        proc.wait()
        output = "".join(output_lines)

        if proc.returncode != 0:
            stderr = proc.stderr.read()
            click.echo(f"Error running claude: {stderr}", err=True)
            sys.exit(1)

        output_file.write_text(output)

    except FileNotFoundError:
        click.echo("Error: 'claude' command not found", err=True)
        sys.exit(1)


@main.command()
def triage():
    """Process inbox items with Claude."""
    try:
        subprocess.run(["claude", "-p", "Run /triage"], cwd=FRIDAY_HOME, check=True)
    except subprocess.CalledProcessError:
        sys.exit(1)
    except FileNotFoundError:
        click.echo("Error: 'claude' command not found", err=True)
        sys.exit(1)


def compile_briefing() -> str:
    """Compile the daily briefing prompt."""
    from datetime import datetime, timedelta

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

    try:
        client = TickTickClient()
        all_tasks = client.get_all_tasks()

        # Actionable = due in 3 days OR Q1 (urgent + important)
        actionable = [
            t for t in all_tasks
            if t.is_urgent(urgent_days=3) or t.quadrant(urgent_days=3) == 1
        ]

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

    except AuthenticationError:
        actionable_tasks_md = "(TickTick not authenticated - run 'friday auth')"

    # Calendar events
    events = cal.fetch_today(config)
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
        prompt = prompt.replace("{{TASKS}}", actionable_tasks_md)
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

    # Get this week's journals
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


if __name__ == "__main__":
    main()
