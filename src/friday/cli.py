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
from .workflows import (
    compile_briefing,
    compile_recap_prompt,
    compile_review,
    compile_week,
    generate_briefing,
    generate_weekly_plan,
    generate_weekly_review,
    get_journal,
)


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


@main.command("task-debug")
def task_debug():
    """Dump raw TickTick API responses for debugging."""
    try:
        client = TickTickClient()
        raw = client.fetch_all_raw()
    except AuthenticationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(json.dumps(raw, indent=2, default=str))


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
    try:
        output = generate_briefing(config)
        click.echo(output)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("endweek")
def endweek():
    """End-of-week review."""
    config = load_config()
    try:
        output = generate_weekly_review(config)
        click.echo(output)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("startweek")
def startweek():
    """Start-of-week planning."""
    config = load_config()
    try:
        output = generate_weekly_plan(config)
        click.echo(output)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command("startweek-fixture")
def startweek_fixture():
    """Capture startweek pipeline data as a JSON test fixture."""
    from dataclasses import asdict
    from datetime import datetime, timedelta

    from .core.tasks import filter_notes

    config = load_config()
    today = date.today()

    # Days remaining through Saturday
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0 and today.weekday() == 5:
        days_until_saturday = 0
    days_remaining = days_until_saturday + 1

    work_start_str, work_end_str = config.work_hours.split("-")
    work_start = int(work_start_str.split(":")[0])
    work_end = int(work_end_str.split(":")[0])
    end_of_saturday = today + timedelta(days=days_until_saturday)

    def serialize_event(e):
        return {
            "title": e.title,
            "start": e.start.isoformat(),
            "end": e.end.isoformat() if e.end else None,
            "location": e.location,
            "calendar": e.calendar,
            "all_day": e.all_day,
            "source": e.source,
        }

    def serialize_task(t):
        return {
            "id": t.id,
            "title": t.title,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "project_id": t.project_id,
            "project_name": t.project_name,
            "kind": t.kind,
        }

    def serialize_slot(s):
        return {"start": s.start.isoformat(), "end": s.end.isoformat()}

    fixture = {"captured_at": datetime.now().isoformat(), "raw": {}, "processed": {}, "prompt": ""}

    # --- Raw data ---
    try:
        client = TickTickClient()
        fixture["raw"]["ticktick_projects"] = client._get_projects()
        fixture["raw"]["ticktick_tasks"] = client.fetch_all_raw()
        all_tasks = client.get_all_tasks()
    except AuthenticationError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    events_raw = cal.fetch_all_events(config, days=days_remaining)
    fixture["raw"]["calendar_events"] = [serialize_event(e) for e in events_raw]

    # --- Processed data ---
    events = cal.drop_redundant_ooo(events_raw)
    fixture["processed"]["events_after_ooo_filter"] = [serialize_event(e) for e in events]

    # Free slots per day
    free_slots_by_day = {}
    day_events = {}
    for e in events:
        d = e.start.date()
        day_events.setdefault(d, []).append(e)
    for i in range(days_remaining):
        d = today + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        slots = cal.find_free_slots(day_events.get(d, []), work_start=work_start, work_end=work_end, min_duration=30)
        free_slots_by_day[d.isoformat()] = [serialize_slot(s) for s in slots]
    fixture["processed"]["free_slots"] = free_slots_by_day

    # Tasks
    week_tasks = [
        t for t in all_tasks
        if not t.is_note
        and ((t.due_date and t.due_date <= end_of_saturday) or t.priority >= 3)
    ]
    work_tasks = [t for t in week_tasks if t.project_name in config.work_task_lists]
    personal_tasks = [t for t in week_tasks if t.project_name in config.personal_task_lists]
    other_tasks = [t for t in week_tasks if t.project_name not in config.work_task_lists and t.project_name not in config.personal_task_lists]
    notes = filter_notes(all_tasks, urgent_days=days_remaining)

    fixture["processed"]["week_tasks"] = [serialize_task(t) for t in week_tasks]
    fixture["processed"]["work_tasks"] = [serialize_task(t) for t in work_tasks]
    fixture["processed"]["personal_tasks"] = [serialize_task(t) for t in personal_tasks]
    fixture["processed"]["other_tasks"] = [serialize_task(t) for t in other_tasks]
    fixture["processed"]["notes"] = [serialize_task(t) for t in notes]

    # --- Prompt ---
    fixture["prompt"] = compile_week()

    # Save
    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    output_path = fixtures_dir / f"startweek-{today.isoformat()}.json"
    output_path.write_text(json.dumps(fixture, indent=2, default=str))
    click.echo(f"Fixture saved to {output_path}")


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
def status():
    """Quick status check (calendar + top tasks + recap status)."""
    config = load_config()
    today = date.today()

    # Calendar
    try:
        events = cal.fetch_today(config)
        calendar_text = (
            "\n".join(f"  {e.format_time()} {e.title}" for e in events[:5])
            or "  No events"
        )
    except Exception as e:
        calendar_text = f"  (Calendar unavailable: {e})"

    # Tasks
    try:
        client = TickTickClient()
        priority_tasks = client.get_priority_tasks()[:5]
        tasks_text = (
            "\n".join(f"  - {t.title}" for t in priority_tasks) or "  No priority tasks"
        )
    except AuthenticationError:
        tasks_text = "  (TickTick not connected)"

    # Recap status
    journal = get_journal(config)
    recap_status = "Done" if journal.has_section(today, "Evening Recap") else "Pending"

    click.echo(f"Status for {today.strftime('%A, %b %d')}\n")
    click.echo(f"Calendar:\n{calendar_text}\n")
    click.echo(f"Priority Tasks:\n{tasks_text}\n")
    click.echo(f"Today's Recap: {recap_status}")


@main.command()
@click.option("--date", "-d", "target_date", default=None,
              help="Date to view (YYYY-MM-DD), defaults to today")
def journal(target_date: str | None):
    """View today's journal entry."""
    config = load_config()
    target = date.fromisoformat(target_date) if target_date else date.today()

    j = get_journal(config)
    content = j.read(target)

    if content is None:
        click.echo(f"No journal entry for {target.strftime('%A, %b %d')}.")
        return

    if not content.strip():
        click.echo(f"Journal for {target.strftime('%A, %b %d')} is empty.")
        return

    click.echo(f"Journal for {target.strftime('%A, %b %d')}\n")
    click.echo(content.strip())


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


@main.command("evening")
@click.option("--date", "-d", "target_date", default=None,
              help="Date to recap (YYYY-MM-DD), defaults to today")
@click.option("--deep", is_flag=True, help="Launch interactive deep mode with Claude")
def evening(target_date: str | None, deep: bool):
    """Record your daily recap."""
    config = load_config()
    target = date.fromisoformat(target_date) if target_date else date.today()

    j = get_journal(config)
    journal_dir = j.journal_dir

    # Check if recap already exists in journal
    if j.has_section(target, "Evening Recap"):
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
    from .adapters.file_journal import FileJournalStore

    journal = FileJournalStore(journal_dir)
    journal.append(target, "Evening Recap", recap_entry.to_markdown())

    output_file = journal_dir / f"{target.isoformat()}.md"
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

    j = get_journal(config)
    prompt = compile_recap_prompt(target, config, j.journal_dir)
    click.echo(prompt)


if __name__ == "__main__":
    main()
