"""Friday Telegram Bot."""

import logging
from datetime import date
from pathlib import Path

from telegram import BotCommand, Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from .config import load_config, FRIDAY_HOME
from .telegram_handlers import (
    start_handler,
    help_handler,
    briefing_handler,
    week_handler,
    review_handler,
    status_handler,
    tasks_handler,
    calendar_handler,
    version_handler,
    journal_handler,
    journal_read_handler,
    recap_start_handler,
    recap_confirm_handler,
    recap_wins_handler,
    recap_blockers_handler,
    recap_energy_handler,
    recap_tomorrow_handler,
    recap_cancel_handler,
)
from .telegram_states import RecapStates

from .telegram_format import send_markdown

logger = logging.getLogger(__name__)


class AuthFilter(filters.BaseFilter):
    """Filter to only allow authorized users."""

    def __init__(self, allowed_users: list[int]):
        super().__init__()
        self.allowed_users = allowed_users

    def check_update(self, update: Update) -> bool:
        if not self.allowed_users:
            return True  # No restriction if no users configured
        user = update.effective_user
        if user is None:
            return False
        return user.id in self.allowed_users


def create_application(config=None) -> Application:
    """Create and configure the Telegram bot application."""
    if config is None:
        config = load_config()

    if not config.telegram_bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN not configured. "
            "Get a token from @BotFather on Telegram and add it to friday.conf"
        )

    # Build application
    app = Application.builder().token(config.telegram_bot_token).build()

    # Create auth filter
    auth_filter = AuthFilter(config.telegram_allowed_users)

    # Simple commands (with auth filter)
    app.add_handler(CommandHandler("start", start_handler, filters=auth_filter))
    app.add_handler(CommandHandler("help", help_handler, filters=auth_filter))
    app.add_handler(CommandHandler("morning", briefing_handler, filters=auth_filter))
    app.add_handler(CommandHandler("startweek", week_handler, filters=auth_filter))
    app.add_handler(CommandHandler("endweek", review_handler, filters=auth_filter))
    app.add_handler(CommandHandler("status", status_handler, filters=auth_filter))
    app.add_handler(CommandHandler("tasks", tasks_handler, filters=auth_filter))
    app.add_handler(CommandHandler("calendar", calendar_handler, filters=auth_filter))
    app.add_handler(CommandHandler("version", version_handler, filters=auth_filter))
    app.add_handler(CommandHandler("journal", journal_read_handler, filters=auth_filter))

    # Recap conversation handler (multi-step)
    recap_conv = ConversationHandler(
        entry_points=[CommandHandler("evening", recap_start_handler, filters=auth_filter)],
        states={
            RecapStates.CONFIRM_OVERWRITE: [
                CallbackQueryHandler(recap_confirm_handler),
            ],
            RecapStates.WINS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recap_wins_handler),
                CallbackQueryHandler(recap_wins_handler),
            ],
            RecapStates.BLOCKERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recap_blockers_handler),
                CallbackQueryHandler(recap_blockers_handler),
            ],
            RecapStates.ENERGY: [
                CallbackQueryHandler(recap_energy_handler),
            ],
            RecapStates.TOMORROW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recap_tomorrow_handler),
            ],
        },
        fallbacks=[CommandHandler("cancel", recap_cancel_handler)],
        per_user=True,
    )
    app.add_handler(recap_conv)

    # Handle non-command messages by logging to journal (authorized users only)
    app.add_handler(
        MessageHandler(
            auth_filter & filters.TEXT & ~filters.COMMAND,
            journal_handler,
        )
    )

    # Handle unauthorized access attempts
    async def unauthorized_handler(update: Update, context):
        user = update.effective_user
        logger.warning(f"Unauthorized access attempt from user {user.id} ({user.username})")
        await update.message.reply_text(
            "Unauthorized. This bot is private.\n"
            "If you're the owner, add your Telegram user ID to TELEGRAM_ALLOWED_USERS in friday.conf"
        )

    # Add catch-all for unauthorized users if we have an allowlist
    if config.telegram_allowed_users:
        app.add_handler(
            MessageHandler(~auth_filter & filters.ALL, unauthorized_handler)
        )

    # Global error handler so commands never fail silently
    async def error_handler(update: object, context) -> None:
        logger.error("Unhandled exception in handler", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    f"Something went wrong: {context.error}"
                )
            except Exception:
                logger.error("Failed to send error message to user")

    app.add_error_handler(error_handler)

    return app


def setup_scheduler(app: Application, config=None) -> AsyncIOScheduler:
    """Set up scheduled messages."""
    if config is None:
        config = load_config()

    scheduler = AsyncIOScheduler(timezone=config.timezone or "America/Toronto")

    # Parse briefing time
    if config.telegram_briefing_time and config.telegram_allowed_users:
        try:
            hour, minute = map(int, config.telegram_briefing_time.split(":"))
            scheduler.add_job(
                send_scheduled_briefing,
                CronTrigger(hour=hour, minute=minute),
                args=[app.bot, config.telegram_allowed_users],
                id="morning_briefing",
            )
            logger.info(f"Scheduled morning briefing at {hour:02d}:{minute:02d}")
        except ValueError:
            logger.warning(f"Invalid briefing time format: {config.telegram_briefing_time}")

    # Parse recap reminder time
    if config.telegram_recap_reminder_time and config.telegram_allowed_users:
        try:
            hour, minute = map(int, config.telegram_recap_reminder_time.split(":"))
            scheduler.add_job(
                send_recap_reminder,
                CronTrigger(hour=hour, minute=minute),
                args=[app.bot, config.telegram_allowed_users, config],
                id="recap_reminder",
            )
            logger.info(f"Scheduled recap reminder at {hour:02d}:{minute:02d}")
        except ValueError:
            logger.warning(f"Invalid recap reminder time format: {config.telegram_recap_reminder_time}")

    # Map day name to cron day_of_week
    day_map = {
        "monday": "mon", "tuesday": "tue", "wednesday": "wed",
        "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
    }

    # Schedule start-of-week plan
    if config.telegram_start_week_time and config.telegram_allowed_users:
        try:
            hour, minute = map(int, config.telegram_start_week_time.split(":"))
            dow = day_map.get(config.telegram_start_week_day.lower(), "sun")
            scheduler.add_job(
                send_scheduled_weekly_plan,
                CronTrigger(day_of_week=dow, hour=hour, minute=minute),
                args=[app.bot, config.telegram_allowed_users],
                id="start_week_plan",
            )
            logger.info(f"Scheduled start-of-week plan on {config.telegram_start_week_day} at {hour:02d}:{minute:02d}")
        except ValueError:
            logger.warning(f"Invalid start week time format: {config.telegram_start_week_time}")

    # Schedule end-of-week review
    if config.telegram_end_week_time and config.telegram_allowed_users:
        try:
            hour, minute = map(int, config.telegram_end_week_time.split(":"))
            dow = day_map.get(config.telegram_end_week_day.lower(), "fri")
            scheduler.add_job(
                send_scheduled_weekly_review,
                CronTrigger(day_of_week=dow, hour=hour, minute=minute),
                args=[app.bot, config.telegram_allowed_users],
                id="end_week_review",
            )
            logger.info(f"Scheduled end-of-week review on {config.telegram_end_week_day} at {hour:02d}:{minute:02d}")
        except ValueError:
            logger.warning(f"Invalid end week time format: {config.telegram_end_week_time}")

    return scheduler


async def send_scheduled_briefing(bot: Bot, user_ids: list[int]):
    """Send morning briefing to all authorized users."""
    import subprocess
    from .adapters.claude_cli import find_claude_binary
    from .cli import compile_briefing

    logger.info("Sending scheduled morning briefing")

    prompt = compile_briefing()

    try:
        result = subprocess.run(
            [find_claude_binary(), "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            briefing = result.stdout.strip()
            for user_id in user_ids:
                try:
                    await send_markdown(bot, briefing, chat_id=user_id)
                except Exception as e:
                    logger.error(f"Failed to send briefing to user {user_id}: {e}")

            # Append to daily journal
            from pathlib import Path
            from .config import load_config, FRIDAY_HOME

            config = load_config()
            if config.daily_journal_dir:
                journal_dir = Path(config.daily_journal_dir).expanduser()
            else:
                journal_dir = FRIDAY_HOME / "journal" / "daily"
            journal_dir.mkdir(parents=True, exist_ok=True)
            output_file = journal_dir / f"{date.today().isoformat()}.md"
            if output_file.exists():
                with open(output_file, "a") as f:
                    f.write(f"\n\n---\n\n## Morning Briefing\n\n{briefing}")
            else:
                output_file.write_text(f"## Morning Briefing\n\n{briefing}")
        else:
            logger.error(f"Claude failed to generate briefing: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Briefing generation timed out")
    except FileNotFoundError:
        logger.error("Claude CLI not found")
    except Exception as e:
        logger.error(f"Error generating briefing: {e}")


async def send_scheduled_weekly_plan(bot: Bot, user_ids: list[int]):
    """Send weekly plan to all authorized users."""
    import subprocess
    from .adapters.claude_cli import find_claude_binary
    from .cli import compile_week

    logger.info("Sending scheduled weekly plan")

    prompt = compile_week()

    try:
        result = subprocess.run(
            [find_claude_binary(), "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            plan = result.stdout.strip()
            for user_id in user_ids:
                try:
                    await send_markdown(bot, plan, chat_id=user_id)
                except Exception as e:
                    logger.error(f"Failed to send weekly plan to user {user_id}: {e}")

            # Append to daily journal
            config = load_config()
            if config.daily_journal_dir:
                journal_dir = Path(config.daily_journal_dir).expanduser()
            else:
                journal_dir = FRIDAY_HOME / "journal" / "daily"
            journal_dir.mkdir(parents=True, exist_ok=True)
            output_file = journal_dir / f"{date.today().isoformat()}.md"
            if output_file.exists():
                with open(output_file, "a") as f:
                    f.write(f"\n\n---\n\n## Weekly Plan\n\n{plan}")
            else:
                output_file.write_text(f"## Weekly Plan\n\n{plan}")
        else:
            logger.error(f"Claude failed to generate weekly plan: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Weekly plan generation timed out")
    except FileNotFoundError:
        logger.error("Claude CLI not found")
    except Exception as e:
        logger.error(f"Error generating weekly plan: {e}")


async def send_scheduled_weekly_review(bot: Bot, user_ids: list[int]):
    """Send weekly review to all authorized users."""
    import subprocess
    from .adapters.claude_cli import find_claude_binary
    from .cli import compile_review

    logger.info("Sending scheduled weekly review")

    prompt = compile_review()

    try:
        result = subprocess.run(
            [find_claude_binary(), "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            review = result.stdout.strip()
            for user_id in user_ids:
                try:
                    await send_markdown(bot, review, chat_id=user_id)
                except Exception as e:
                    logger.error(f"Failed to send weekly review to user {user_id}: {e}")

            # Append to daily journal
            config = load_config()
            if config.daily_journal_dir:
                journal_dir = Path(config.daily_journal_dir).expanduser()
            else:
                journal_dir = FRIDAY_HOME / "journal" / "daily"
            journal_dir.mkdir(parents=True, exist_ok=True)
            output_file = journal_dir / f"{date.today().isoformat()}.md"
            if output_file.exists():
                with open(output_file, "a") as f:
                    f.write(f"\n\n---\n\n## Weekly Review\n\n{review}")
            else:
                output_file.write_text(f"## Weekly Review\n\n{review}")
        else:
            logger.error(f"Claude failed to generate weekly review: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Weekly review generation timed out")
    except FileNotFoundError:
        logger.error("Claude CLI not found")
    except Exception as e:
        logger.error(f"Error generating weekly review: {e}")


async def send_recap_reminder(bot: Bot, user_ids: list[int], config):
    """Send evening recap reminder if no recap exists for today."""
    today = date.today()

    if config.daily_journal_dir:
        journal_dir = Path(config.daily_journal_dir).expanduser()
    else:
        journal_dir = FRIDAY_HOME / "journal" / "daily"

    # Only remind if no recap exists in journal for today
    journal_file = journal_dir / f"{today.isoformat()}.md"
    recap_exists = journal_file.exists() and "## Evening Recap" in journal_file.read_text()

    if not recap_exists:
        logger.info("Sending recap reminder")
        for user_id in user_ids:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="Time for your daily recap!\n\nUse /evening to reflect on today.",
                )
            except Exception as e:
                logger.error(f"Failed to send recap reminder to user {user_id}: {e}")
    else:
        logger.info("Recap already exists for today, skipping reminder")


def run_bot():
    """Run the Telegram bot."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    config = load_config()
    app = create_application(config)
    scheduler = setup_scheduler(app, config)

    async def post_init(application: Application) -> None:
        """Start scheduler and register commands after event loop is running."""
        scheduler.start()
        logger.info("Scheduler started")

        await application.bot.set_my_commands([
            BotCommand("morning", "Get your morning briefing"),
            BotCommand("startweek", "Start-of-week planning"),
            BotCommand("endweek", "End-of-week review"),
            BotCommand("evening", "Record your daily recap"),
            BotCommand("tasks", "List priority tasks"),
            BotCommand("calendar", "Today's events"),
            BotCommand("journal", "View today's journal"),
            BotCommand("status", "Quick status check"),
            BotCommand("version", "Check bot version"),
            BotCommand("help", "Show all commands"),
        ])

    app.post_init = post_init

    # Log startup info
    if config.telegram_allowed_users:
        logger.info(f"Bot authorized for users: {config.telegram_allowed_users}")
    else:
        logger.warning("No TELEGRAM_ALLOWED_USERS configured - bot is open to anyone!")

    logger.info("Starting Friday Telegram bot...")

    # Run bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)
