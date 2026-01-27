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
    today = date.today().isoformat()
    journal_dir = FRIDAY_HOME / "journal" / "daily"
    journal_dir.mkdir(parents=True, exist_ok=True)
    output_file = journal_dir / f"{today}.md"

    prompt = compile_briefing()

    # Pipe to claude
    try:
        result = subprocess.run(
            ["claude", "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout
        output_file.write_text(output)
        click.echo(output)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running claude: {e.stderr}", err=True)
        sys.exit(1)
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
        result = subprocess.run(
            ["claude", "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout
        output_file.write_text(output)
        click.echo(output)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running claude: {e.stderr}", err=True)
        sys.exit(1)
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
    config = load_config()
    today = date.today()

    # Fetch data
    try:
        client = TickTickClient()
        tasks = client.get_priority_tasks()
        tasks_md = "\n".join(
            f"- [{t.priority}] {t.title} (due: {t.due_date or 'no date'}, project: {t.project_name})"
            for t in tasks
        ) or "No priority tasks."
    except AuthenticationError:
        tasks_md = "(TickTick not authenticated - run 'friday auth')"

    events = cal.fetch_today(config)
    calendar_md = "\n".join(
        f"- {e.format_time()} {e.title}" + (f" @ {e.location}" if e.location else "")
        for e in events
    ) or "No events today."

    # Check for deep work conflicts
    deep_work = config.deep_work_hours
    conflicts = []
    for event in events:
        if event.all_day:
            continue
        event_hour = event.start.hour
        for block in deep_work:
            start, end = block.split("-")
            start_hour = int(start.split(":")[0])
            end_hour = int(end.split(":")[0])
            if start_hour <= event_hour < end_hour:
                conflicts.append(f"- {event.title} conflicts with deep work ({block})")

    conflicts_md = "\n".join(conflicts) if conflicts else "None"

    template = FRIDAY_HOME / "templates" / "daily-briefing.md"
    if template.exists():
        prompt = template.read_text()
        prompt = prompt.replace("{{DATE}}", today.isoformat())
        prompt = prompt.replace("{{DAY_OF_WEEK}}", today.strftime("%A"))
        prompt = prompt.replace("{{TASKS}}", tasks_md)
        prompt = prompt.replace("{{CALENDAR}}", calendar_md)
        prompt = prompt.replace("{{CONFLICTS}}", conflicts_md)
        return prompt

    # Fallback inline template
    return f"""You are Friday, a personal assistant. Generate a morning briefing.

## Date
{today.strftime("%A, %B %d, %Y")}

## Today's Calendar
{calendar_md}

## Priority Tasks
{tasks_md}

## Deep Work Conflicts
{conflicts_md}

## Instructions
1. Summarize the day ahead
2. Identify the top 3 priorities
3. Flag any scheduling conflicts
4. Suggest time blocks for focused work
5. Be direct and concise
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
