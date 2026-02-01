"""Telegram command handlers."""

import logging
import subprocess
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .config import load_config, FRIDAY_HOME
from .recap import Recap, RecapMode, determine_recap_mode
from .telegram_states import RecapStates
from . import calendar as cal
from .ticktick import TickTickClient, AuthenticationError


# ============== Simple Commands ==============


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "Hey! I'm Friday, your personal assistant.\n\n"
        "Commands:\n"
        "/tasks - List priority tasks\n"
        "/calendar - Today's events\n"
        "/briefing - Get your morning briefing\n"
        "/week - Weekly planning overview\n"
        "/journal - View today's journal\n"
        "/recap - Record your daily recap\n"
        "/status - Quick status check\n"
        "/version - Check bot version\n"
        "/help - Show all commands"
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "*Friday Commands*\n\n"
        "/tasks - List priority tasks\n"
        "/calendar - Today's events\n"
        "/briefing - Generate morning briefing with tasks and calendar\n"
        "/week - Weekly planning overview\n"
        "/journal - View today's journal entry\n"
        "/recap - Interactive daily reflection\n"
        "/status - Today's calendar and top tasks\n"
        "/version - Check bot version\n"
        "/cancel - Cancel current operation\n",
        parse_mode="Markdown",
    )


async def tasks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tasks command - list priority tasks."""
    try:
        client = TickTickClient()
        priority_tasks = client.get_priority_tasks()
    except AuthenticationError:
        await update.message.reply_text("TickTick not connected. Run `friday auth` on CLI.")
        return

    if not priority_tasks:
        await update.message.reply_text("No priority tasks for today.")
        return

    lines = []
    for task in priority_tasks:
        priority_marker = "!" * task.priority if task.priority else " "
        due = f" (due {task.due_date})" if task.due_date else ""
        lines.append(f"`[{priority_marker:3}]` {task.title}{due}")

    await update.message.reply_text(
        "*Priority Tasks*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /calendar command - show today's events."""
    config = load_config()

    try:
        events = cal.fetch_all_events(config, days=1)
    except Exception as e:
        await update.message.reply_text(f"Failed to fetch calendar: {e}")
        return

    if not events:
        await update.message.reply_text("No events today.")
        return

    lines = []
    current_date = None
    for event in events:
        event_date = event.start.date()
        if event_date != current_date:
            if current_date is not None:
                lines.append("")
            lines.append(f"*{event_date.strftime('%A, %B %d')}*")
            current_date = event_date

        time_str = event.format_time()
        loc = f" @ {event.location}" if event.location else ""
        lines.append(f"  `{time_str:8}` {event.title}{loc}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - quick overview."""
    config = load_config()
    today = date.today()

    # Get calendar
    try:
        events = cal.fetch_today(config)
        calendar_text = (
            "\n".join(f"  {e.format_time()} {e.title}" for e in events[:5])
            or "  No events"
        )
    except Exception as e:
        logger.error(f"Failed to fetch calendar for status: {e}")
        calendar_text = f"  (Calendar unavailable: {e})"

    # Get tasks
    try:
        client = TickTickClient()
        tasks = client.get_priority_tasks()[:5]
        tasks_text = (
            "\n".join(f"  - {t.title}" for t in tasks) or "  No priority tasks"
        )
    except AuthenticationError:
        tasks_text = "  (TickTick not connected)"

    # Check recap status (now stored in journal)
    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"
    journal_file = journal_dir / f"{today.isoformat()}.md"
    recap_exists = journal_file.exists() and "## Evening Recap" in journal_file.read_text()
    recap_status = "Done" if recap_exists else "Pending"

    await update.message.reply_text(
        f"*Status for {today.strftime('%A, %b %d')}*\n\n"
        f"*Calendar:*\n{calendar_text}\n\n"
        f"*Priority Tasks:*\n{tasks_text}\n\n"
        f"*Today's Recap:* {recap_status}",
        parse_mode="Markdown",
    )


async def version_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /version command - show bot version from git."""
    try:
        # Get the most recent commit info
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H%n%s%n%ci"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
            timeout=5,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            commit_hash = lines[0][:7]  # Short hash
            message = lines[1]
            timestamp = lines[2]

            await update.message.reply_text(
                f"*Friday Bot Version*\n\n"
                f"Commit: `{commit_hash}`\n"
                f"Message: {message}\n"
                f"Date: {timestamp}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text("Unable to get version info.")
    except Exception as e:
        await update.message.reply_text(f"Error getting version: {e}")


async def journal_read_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /journal command - display today's journal if it exists."""
    config = load_config()
    today = date.today()

    # Determine journal directory
    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"

    journal_file = journal_dir / f"{today.isoformat()}.md"

    if not journal_file.exists():
        await update.message.reply_text(f"No journal entry for {today.strftime('%A, %b %d')}.")
        return

    content = journal_file.read_text().strip()
    if not content:
        await update.message.reply_text(f"Journal for {today.strftime('%A, %b %d')} is empty.")
        return

    header = f"*Journal for {today.strftime('%A, %b %d')}*\n\n"
    message = header + content

    # Telegram has 4096 char limit, split if needed
    if len(message) > 4000:
        await update.message.reply_text(header, parse_mode="Markdown")
        for i in range(0, len(content), 4000):
            await update.message.reply_text(content[i : i + 4000])
    else:
        await update.message.reply_text(message, parse_mode="Markdown")


async def briefing_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /briefing command."""
    await update.message.reply_text("Generating your briefing...")

    # Import here to avoid circular imports
    from .cli import compile_briefing

    prompt = compile_briefing()

    try:
        # Run through Claude
        result = subprocess.run(
            ["claude", "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            briefing = result.stdout.strip()
            # Telegram has 4096 char limit, split if needed
            if len(briefing) > 4000:
                for i in range(0, len(briefing), 4000):
                    await update.message.reply_text(briefing[i : i + 4000])
            else:
                await update.message.reply_text(briefing)
        else:
            await update.message.reply_text(
                "Failed to generate briefing. Check logs."
            )
    except subprocess.TimeoutExpired:
        await update.message.reply_text("Briefing generation timed out.")
    except FileNotFoundError:
        await update.message.reply_text("Claude CLI not found on server.")


async def week_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /week command."""
    await update.message.reply_text("Generating your weekly plan...")

    from .cli import compile_week

    prompt = compile_week()

    try:
        result = subprocess.run(
            ["claude", "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            plan = result.stdout.strip()
            if len(plan) > 4000:
                for i in range(0, len(plan), 4000):
                    await update.message.reply_text(plan[i : i + 4000])
            else:
                await update.message.reply_text(plan)
        else:
            await update.message.reply_text(
                "Failed to generate weekly plan. Check logs."
            )
    except subprocess.TimeoutExpired:
        await update.message.reply_text("Weekly plan generation timed out.")
    except FileNotFoundError:
        await update.message.reply_text("Claude CLI not found on server.")


# ============== Journal Logging ==============


async def journal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages by appending them to the daily journal."""
    from datetime import datetime

    config = load_config()
    today = date.today()
    now = datetime.now()

    # Determine journal directory
    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"
    journal_dir.mkdir(parents=True, exist_ok=True)

    # Get message text
    text = update.message.text.strip()
    if not text:
        return

    # Format entry with timestamp
    timestamp = now.strftime("%H:%M")
    entry = f"- [{timestamp}] {text}\n"

    # Append to daily journal
    journal_file = journal_dir / f"{today.isoformat()}.md"

    if journal_file.exists():
        content = journal_file.read_text()
        # Check if there's already a Notes section
        if "## Notes" in content:
            # Append to existing Notes section
            with open(journal_file, "a") as f:
                f.write(entry)
        else:
            # Add Notes section
            with open(journal_file, "a") as f:
                f.write(f"\n\n## Notes\n\n{entry}")
    else:
        # Create new file with Notes section
        journal_file.write_text(f"## Notes\n\n{entry}")

    await update.message.reply_text("Added to journal.")


# ============== Recap Conversation ==============


async def recap_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the recap conversation."""
    config = load_config()
    today = date.today()

    # Determine journal directory
    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"

    # Store journal_dir in context for later use
    context.user_data["journal_dir"] = str(journal_dir)

    # Check if recap already exists in journal
    journal_file = journal_dir / f"{today.isoformat()}.md"
    if journal_file.exists() and "## Evening Recap" in journal_file.read_text():
        keyboard = [
            [
                InlineKeyboardButton("Yes, add another", callback_data="recap_overwrite"),
                InlineKeyboardButton("No, cancel", callback_data="recap_cancel"),
            ]
        ]
        await update.message.reply_text(
            f"You already have a recap for {today}. Add another?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return RecapStates.CONFIRM_OVERWRITE

    # Initialize recap data in context
    context.user_data["recap"] = {
        "date": today.isoformat(),
        "wins": [],
        "blockers": [],
        "energy": None,
        "tomorrow_focus": "",
    }

    return await _prompt_for_wins(update, context)


async def _prompt_for_wins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the wins prompt with quick options."""
    keyboard = [
        [
            InlineKeyboardButton("Good focus", callback_data="win:Good focus block"),
            InlineKeyboardButton("Shipped something", callback_data="win:Shipped feature"),
        ],
        [
            InlineKeyboardButton("Productive meeting", callback_data="win:Productive meeting"),
            InlineKeyboardButton("Cleared backlog", callback_data="win:Cleared backlog"),
        ],
        [InlineKeyboardButton("Done with wins ->", callback_data="wins_done")],
    ]

    message = (
        "*Daily Recap*\n\n"
        "What went well today?\n"
        "_Tap quick options or type your own (comma-separated)_"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    return RecapStates.WINS


async def recap_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle overwrite confirmation."""
    query = update.callback_query
    await query.answer()

    if query.data == "recap_cancel":
        await query.edit_message_text("Recap cancelled.")
        return ConversationHandler.END

    if query.data == "recap_overwrite":
        today = date.today()
        context.user_data["recap"] = {
            "date": today.isoformat(),
            "wins": [],
            "blockers": [],
            "energy": None,
            "tomorrow_focus": "",
        }
        return await _prompt_for_wins(update, context)

    return RecapStates.CONFIRM_OVERWRITE


async def recap_wins_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle wins input."""
    # Handle callback (button tap)
    if update.callback_query:
        query = update.callback_query
        await query.answer()

        if query.data == "wins_done":
            # Move to blockers
            keyboard = [
                [
                    InlineKeyboardButton("Meetings", callback_data="blocker:Too many meetings"),
                    InlineKeyboardButton("Interruptions", callback_data="blocker:Interruptions"),
                ],
                [
                    InlineKeyboardButton("Low energy", callback_data="blocker:Low energy"),
                    InlineKeyboardButton("Unclear priorities", callback_data="blocker:Unclear priorities"),
                ],
                [InlineKeyboardButton("No blockers ->", callback_data="blockers_done")],
            ]
            wins_count = len(context.user_data["recap"]["wins"])
            await query.edit_message_text(
                f"Wins recorded: {wins_count}\n\n"
                "What didn't go as planned?\n"
                "_Tap quick options or type your own_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return RecapStates.BLOCKERS

        if query.data.startswith("win:"):
            win = query.data[4:]
            context.user_data["recap"]["wins"].append(win)
            await query.answer(f"Added: {win}")
            return RecapStates.WINS

    # Handle text input
    if update.message:
        text = update.message.text.strip()
        wins = [w.strip() for w in text.split(",") if w.strip()]
        context.user_data["recap"]["wins"].extend(wins)

        keyboard = [
            [InlineKeyboardButton("Done with wins ->", callback_data="wins_done")],
        ]
        await update.message.reply_text(
            f"Added {len(wins)} win(s). Add more or tap done.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return RecapStates.WINS

    return RecapStates.WINS


async def recap_blockers_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle blockers input."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()

        if query.data == "blockers_done":
            # Move to energy
            keyboard = [
                [
                    InlineKeyboardButton("High", callback_data="energy:high"),
                    InlineKeyboardButton("Medium", callback_data="energy:medium"),
                    InlineKeyboardButton("Low", callback_data="energy:low"),
                ],
            ]
            blockers_count = len(context.user_data["recap"]["blockers"])
            await query.edit_message_text(
                f"Blockers recorded: {blockers_count}\n\n"
                "How was your energy today?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return RecapStates.ENERGY

        if query.data.startswith("blocker:"):
            blocker = query.data[8:]
            context.user_data["recap"]["blockers"].append(blocker)
            await query.answer(f"Added: {blocker}")
            return RecapStates.BLOCKERS

    if update.message:
        text = update.message.text.strip()
        blockers = [b.strip() for b in text.split(",") if b.strip()]
        context.user_data["recap"]["blockers"].extend(blockers)

        keyboard = [
            [InlineKeyboardButton("Done with blockers ->", callback_data="blockers_done")],
        ]
        await update.message.reply_text(
            f"Added {len(blockers)} blocker(s). Add more or tap done.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return RecapStates.BLOCKERS

    return RecapStates.BLOCKERS


async def recap_energy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle energy level selection."""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("energy:"):
        energy = query.data[7:]
        context.user_data["recap"]["energy"] = energy

        await query.edit_message_text(
            f"Energy: {energy}\n\n"
            "What's your one focus for tomorrow?\n"
            "_Type a brief intention_",
            parse_mode="Markdown",
        )
        return RecapStates.TOMORROW

    return RecapStates.ENERGY


async def recap_tomorrow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tomorrow's focus and save recap."""
    text = update.message.text.strip()
    context.user_data["recap"]["tomorrow_focus"] = text

    # Build and save recap
    recap_data = context.user_data["recap"]
    config = load_config()

    # Get journal directory
    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"
    journal_dir.mkdir(parents=True, exist_ok=True)

    try:
        TickTickClient()
        ticktick_available = True
    except AuthenticationError:
        ticktick_available = False

    recap_date = date.fromisoformat(recap_data["date"])
    mode = determine_recap_mode(recap_date, journal_dir, ticktick_available)

    recap = Recap(
        date=recap_date,
        mode=mode,
        wins=recap_data["wins"],
        blockers=recap_data["blockers"],
        energy=recap_data["energy"],
        tomorrow_focus=recap_data["tomorrow_focus"],
    )

    # Append to daily journal
    output_file = journal_dir / f"{recap_data['date']}.md"
    recap_md = recap.to_markdown()

    if output_file.exists():
        with open(output_file, "a") as f:
            f.write(f"\n\n---\n\n## Evening Recap\n\n{recap_md}")
    else:
        output_file.write_text(f"## Evening Recap\n\n{recap_md}")

    # Summary message
    wins_str = ", ".join(recap_data["wins"][:3]) or "None"
    blockers_str = ", ".join(recap_data["blockers"][:3]) or "None"

    await update.message.reply_text(
        f"*Recap saved!*\n\n"
        f"*Wins:* {wins_str}\n"
        f"*Blockers:* {blockers_str}\n"
        f"*Energy:* {recap_data['energy']}\n"
        f"*Tomorrow:* {text}",
        parse_mode="Markdown",
    )

    # Clear user data
    context.user_data.pop("recap", None)
    context.user_data.pop("journal_dir", None)
    return ConversationHandler.END


async def recap_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the recap conversation."""
    context.user_data.pop("recap", None)
    context.user_data.pop("journal_dir", None)
    await update.message.reply_text("Recap cancelled.")
    return ConversationHandler.END
