"""Friday Telegram Bot."""

import logging
from datetime import date
from pathlib import Path

from telegram import Update, Bot
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
from .recap import load_recap
from .telegram_handlers import (
    start_handler,
    help_handler,
    briefing_handler,
    status_handler,
    recap_start_handler,
    recap_confirm_handler,
    recap_wins_handler,
    recap_blockers_handler,
    recap_energy_handler,
    recap_tomorrow_handler,
    recap_cancel_handler,
)
from .telegram_states import RecapStates

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
    app.add_handler(CommandHandler("briefing", briefing_handler, filters=auth_filter))
    app.add_handler(CommandHandler("status", status_handler, filters=auth_filter))

    # Recap conversation handler (multi-step)
    recap_conv = ConversationHandler(
        entry_points=[CommandHandler("recap", recap_start_handler, filters=auth_filter)],
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

    return scheduler


async def send_scheduled_briefing(bot: Bot, user_ids: list[int]):
    """Send morning briefing to all authorized users."""
    import subprocess
    from .cli import compile_briefing

    logger.info("Sending scheduled morning briefing")

    prompt = compile_briefing()

    try:
        result = subprocess.run(
            ["claude", "-p", "-"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            briefing = result.stdout.strip()
            for user_id in user_ids:
                try:
                    # Split if too long
                    if len(briefing) > 4000:
                        await bot.send_message(chat_id=user_id, text="*Morning Briefing*", parse_mode="Markdown")
                        for i in range(0, len(briefing), 4000):
                            await bot.send_message(chat_id=user_id, text=briefing[i : i + 4000])
                    else:
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"*Morning Briefing*\n\n{briefing}",
                            parse_mode="Markdown",
                        )
                except Exception as e:
                    logger.error(f"Failed to send briefing to user {user_id}: {e}")
        else:
            logger.error(f"Claude failed to generate briefing: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Briefing generation timed out")
    except FileNotFoundError:
        logger.error("Claude CLI not found")
    except Exception as e:
        logger.error(f"Error generating briefing: {e}")


async def send_recap_reminder(bot: Bot, user_ids: list[int], config):
    """Send evening recap reminder if no recap exists for today."""
    today = date.today()

    if config.daily_recap_dir:
        recap_dir = Path(config.daily_recap_dir).expanduser()
    else:
        recap_dir = FRIDAY_HOME / "recaps" / "daily"

    # Only remind if no recap exists for today
    if load_recap(today, recap_dir) is None:
        logger.info("Sending recap reminder")
        for user_id in user_ids:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="Time for your daily recap!\n\nUse /recap to reflect on today.",
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
        """Start scheduler after event loop is running."""
        scheduler.start()
        logger.info("Scheduler started")

    app.post_init = post_init

    # Log startup info
    if config.telegram_allowed_users:
        logger.info(f"Bot authorized for users: {config.telegram_allowed_users}")
    else:
        logger.warning("No TELEGRAM_ALLOWED_USERS configured - bot is open to anyone!")

    logger.info("Starting Friday Telegram bot...")

    # Run bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)
