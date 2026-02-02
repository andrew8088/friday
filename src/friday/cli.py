"""Friday CLI - Personal Assistant."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import click

from . import calendar as cal
from .adapters.claude_cli import find_claude_binary
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
            [find_claude_binary(), "-p", "-"],
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
    config = load_config()
    today = date.today().isoformat()

    # Use configured journal dir or default
    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"

    journal_dir.mkdir(parents=True, exist_ok=True)
    output_file = journal_dir / f"{today}.md"

    prompt = compile_review()

    try:
        proc = subprocess.Popen(
            [find_claude_binary(), "-p", "-"],
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

        # Append to daily journal with section header
        if output_file.exists():
            with open(output_file, "a") as f:
                f.write(f"\n\n---\n\n## Weekly Review\n\n{output}")
        else:
            output_file.write_text(f"## Weekly Review\n\n{output}")

    except FileNotFoundError:
        click.echo("Error: 'claude' command not found", err=True)
        sys.exit(1)


@main.command()
def week():
    """Generate weekly plan."""
    config = load_config()
    today = date.today().isoformat()

    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"

    journal_dir.mkdir(parents=True, exist_ok=True)
    output_file = journal_dir / f"{today}.md"

    prompt = compile_week()

    try:
        proc = subprocess.Popen(
            [find_claude_binary(), "-p", "-"],
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

        if output_file.exists():
            with open(output_file, "a") as f:
                f.write(f"\n\n---\n\n## Weekly Plan\n\n{output}")
        else:
            output_file.write_text(f"## Weekly Plan\n\n{output}")

    except FileNotFoundError:
        click.echo("Error: 'claude' command not found", err=True)
        sys.exit(1)


@main.command()
def triage():
    """Process inbox items with Claude."""
    try:
        subprocess.run([find_claude_binary(), "-p", "Run /triage"], cwd=FRIDAY_HOME, check=True)
    except subprocess.CalledProcessError:
        sys.exit(1)
    except FileNotFoundError:
        click.echo("Error: 'claude' command not found", err=True)
        sys.exit(1)


@main.command("cal-auth")
@click.option("--account", default=None, help="Label of account to authenticate (default: all)")
def cal_auth(account: str | None):
    """Authenticate with Google Calendar."""
    config = load_config()

    if not config.gcalcli_accounts:
        click.echo("No calendar accounts configured in friday.conf", err=True)
        sys.exit(1)

    if not config.google_client_secret_file:
        click.echo("GOOGLE_CLIENT_SECRET_FILE not set in friday.conf", err=True)
        sys.exit(1)

    from friday.adapters.google_calendar import GoogleCalendarAdapter

    for acct in config.gcalcli_accounts:
        if account and acct.label != account:
            continue

        click.echo(f"\nAuthenticating: {acct.label or acct.config_folder}")
        adapter = GoogleCalendarAdapter(
            config_folder=acct.config_folder,
            label=acct.label,
            client_secret_file=config.google_client_secret_file,
        )
        if adapter.authenticate():
            click.echo(f"  ✓ Token saved to {adapter._token_path}")
        else:
            click.echo(f"  ✗ Authentication failed", err=True)


@main.command("cal-debug")
def cal_debug():
    """Debug calendar connectivity per account."""
    config = load_config()
    composite = cal.CompositeCalendarAdapter(config)

    for adapter in composite._adapters:
        folder_display = adapter.config_folder or "(default)"
        click.echo(f"\nAccount: {adapter.label} ({folder_display})")

        # List calendars
        try:
            calendars = adapter.list_calendars()
            if calendars:
                click.echo("  ✓ Authenticated")
                click.echo("  Calendars:")
                for access, name in calendars:
                    click.echo(f"    {access:16} {name}")
            else:
                click.echo("  ✗ No calendars (not authenticated? run 'friday cal-auth')")
        except Exception as e:
            click.echo(f"  ✗ Failed: {e}")
            continue

        # Show filter
        if adapter.calendars:
            click.echo(f"  Filter: {', '.join(adapter.calendars)}")
        else:
            click.echo("  Filter: (all calendars)")

        # Test fetch today's events
        try:
            events = adapter.fetch_events(days=1)
            click.echo(f"  Today's events: {len(events)}")
        except Exception as e:
            click.echo(f"  Today's events: error ({e})")


@main.command()
@click.option("--debug", is_flag=True, help="Enable debug logging")
def bot(debug: bool):
    """Run the Telegram bot."""
    import logging

    if debug:
        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            level=logging.DEBUG,
        )

    try:
        from .telegram_bot import run_bot
        click.echo("Starting Friday Telegram bot...")
        click.echo("Press Ctrl+C to stop")
        run_bot()
    except ImportError as e:
        click.echo(f"Error: Missing dependencies. Run 'pip install python-telegram-bot apscheduler'", err=True)
        click.echo(f"Details: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nBot stopped.")


@main.command()
@click.option("--date", "-d", "target_date", default=None,
              help="Date to recap (YYYY-MM-DD), defaults to today")
@click.option("--deep", is_flag=True, help="Launch interactive deep mode with Claude")
def recap(target_date: str | None, deep: bool):
    """Record daily recap."""
    config = load_config()
    target = date.fromisoformat(target_date) if target_date else date.today()

    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"
    journal_dir.mkdir(parents=True, exist_ok=True)

    # Check if recap already exists in journal
    journal_file = journal_dir / f"{target.isoformat()}.md"
    if journal_file.exists():
        content = journal_file.read_text()
        if "## Evening Recap" in content:
            if not click.confirm(f"Recap for {target} already exists in journal. Add another?"):
                return

    if deep:
        _run_deep_recap(target, config, journal_dir)
    else:
        _run_quick_recap(target, config, journal_dir)


def _run_quick_recap(target: date, config, journal_dir: Path):
    """Quick 2-minute structured recap."""
    from .recap import determine_recap_mode, RecapMode, Recap

    # Check what data we have
    try:
        client = TickTickClient()
        ticktick_available = True
    except AuthenticationError:
        ticktick_available = False

    mode = determine_recap_mode(target, journal_dir, ticktick_available)

    # Show context based on mode
    if mode == RecapMode.FULL:
        click.echo(f"Recap for {target} (comparing to morning briefing)\n")
    elif mode == RecapMode.TASKS_ONLY:
        click.echo(f"Recap for {target} (task data available)\n")
    else:
        click.echo(f"Recap for {target} (freeform reflection)\n")

    # Collect input
    click.echo("What went well today? (comma-separated or freeform)")
    wins_raw = click.prompt(">", default="").strip()
    wins = [w.strip() for w in wins_raw.split(",") if w.strip()] if wins_raw else []

    click.echo("\nWhat didn't go as planned?")
    blockers_raw = click.prompt(">", default="").strip()
    blockers = [b.strip() for b in blockers_raw.split(",") if b.strip()] if blockers_raw else []

    click.echo("\nOne focus for tomorrow?")
    tomorrow = click.prompt(">", default="").strip()

    click.echo("\nEnergy level today? (low/medium/high, or skip)")
    energy = click.prompt(">", default="").strip() or None

    click.echo("\nAny additional reflection? (optional, press enter to skip)")
    reflection = click.prompt(">", default="").strip()

    # Build recap
    recap_entry = Recap(
        date=target,
        mode=mode,
        wins=wins,
        blockers=blockers,
        energy=energy,
        tomorrow_focus=tomorrow,
        reflection=reflection,
    )

    # Append to daily journal
    output_file = journal_dir / f"{target.isoformat()}.md"
    recap_md = recap_entry.to_markdown()

    if output_file.exists():
        with open(output_file, "a") as f:
            f.write(f"\n\n---\n\n## Evening Recap\n\n{recap_md}")
    else:
        output_file.write_text(f"## Evening Recap\n\n{recap_md}")

    click.echo(f"\n✓ Recap saved to {output_file}")


def _run_deep_recap(target: date, config, journal_dir: Path):
    """Launch interactive deep recap with Claude."""
    prompt = compile_recap_prompt(target, config, journal_dir)

    try:
        # Run Claude interactively with the recap context
        result = subprocess.run(
            [find_claude_binary(), "-p", prompt],
            cwd=FRIDAY_HOME,
        )
        if result.returncode != 0:
            sys.exit(1)
    except FileNotFoundError:
        click.echo("Error: 'claude' command not found", err=True)
        sys.exit(1)


@main.command("compile-recap")
@click.option("--date", "-d", "target_date", default=None,
              help="Date to compile recap for (YYYY-MM-DD)")
def compile_recap_cmd(target_date: str | None):
    """Output recap context for Claude (used by /recap slash command)."""
    config = load_config()
    target = date.fromisoformat(target_date) if target_date else date.today()

    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"

    prompt = compile_recap_prompt(target, config, journal_dir)
    click.echo(prompt)


def compile_briefing() -> str:
    """Compile the daily briefing prompt."""
    from datetime import datetime

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
        prompt = prompt.replace("{{YESTERDAY_CONTEXT}}", "")
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
    from datetime import datetime, timedelta

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
    try:
        client = TickTickClient()
        all_tasks = client.get_all_tasks()

        week_tasks = [
            t for t in all_tasks
            if (t.due_date and t.due_date <= end_of_saturday) or t.priority >= 3
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

## Instructions
1. Suggest 3 focus areas for the rest of the week
2. Flag any scheduling risks or conflicts
3. Recommend specific time blocks for high-priority tasks
4. Note any overloaded days and suggest redistribution
5. Be specific with times and days, not vague
"""


def compile_recap_prompt(target: date, config, journal_dir: Path) -> str:
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


if __name__ == "__main__":
    main()
