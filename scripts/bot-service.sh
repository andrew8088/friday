#!/bin/bash
# Friday Telegram Bot Service Management Script
# Usage: ./bot-service.sh {install|uninstall|start|stop|restart|status|logs}

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRIDAY_HOME="${FRIDAY_HOME:-$HOME/friday}"
PLIST_SRC="$SCRIPT_DIR/../launchd/com.friday.telegram-bot.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.friday.telegram-bot.plist"
LOG_DIR="$FRIDAY_HOME/logs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

case "${1:-help}" in
    install)
        info "Installing Friday Telegram bot service..."

        # Create logs directory
        mkdir -p "$LOG_DIR"

        # Update plist with actual paths
        if [[ ! -f "$PLIST_SRC" ]]; then
            error "Plist template not found at $PLIST_SRC"
            exit 1
        fi

        # Copy and customize plist
        sed "s|/Users/andrew/friday|$FRIDAY_HOME|g" "$PLIST_SRC" > "$PLIST_DEST"

        # Load the service
        launchctl load "$PLIST_DEST"

        info "Bot service installed and started"
        info "Logs: $LOG_DIR/telegram-bot.log"
        ;;

    uninstall)
        info "Uninstalling Friday Telegram bot service..."

        if [[ -f "$PLIST_DEST" ]]; then
            launchctl unload "$PLIST_DEST" 2>/dev/null || true
            rm -f "$PLIST_DEST"
            info "Bot service uninstalled"
        else
            warn "Service not installed"
        fi
        ;;

    start)
        if [[ ! -f "$PLIST_DEST" ]]; then
            error "Service not installed. Run './bot-service.sh install' first"
            exit 1
        fi
        launchctl start com.friday.telegram-bot
        info "Bot started"
        ;;

    stop)
        launchctl stop com.friday.telegram-bot 2>/dev/null || true
        info "Bot stopped"
        ;;

    restart)
        launchctl stop com.friday.telegram-bot 2>/dev/null || true
        sleep 2
        launchctl start com.friday.telegram-bot
        info "Bot restarted"
        ;;

    status)
        echo "Service status:"
        if launchctl list | grep -q "com.friday.telegram-bot"; then
            PID=$(launchctl list | grep "com.friday.telegram-bot" | awk '{print $1}')
            if [[ "$PID" != "-" ]]; then
                info "Running (PID: $PID)"
            else
                warn "Loaded but not running"
            fi
        else
            warn "Not running"
        fi

        echo ""
        echo "Recent log entries:"
        if [[ -f "$LOG_DIR/telegram-bot.log" ]]; then
            tail -5 "$LOG_DIR/telegram-bot.log" 2>/dev/null || echo "  (no logs yet)"
        else
            echo "  (no log file)"
        fi
        ;;

    logs)
        if [[ -f "$LOG_DIR/telegram-bot.log" ]]; then
            tail -f "$LOG_DIR/telegram-bot.log"
        else
            error "Log file not found: $LOG_DIR/telegram-bot.log"
            exit 1
        fi
        ;;

    errors)
        if [[ -f "$LOG_DIR/telegram-bot.error.log" ]]; then
            tail -f "$LOG_DIR/telegram-bot.error.log"
        else
            error "Error log file not found: $LOG_DIR/telegram-bot.error.log"
            exit 1
        fi
        ;;

    help|*)
        echo "Friday Telegram Bot Service Manager"
        echo ""
        echo "Usage: $0 {command}"
        echo ""
        echo "Commands:"
        echo "  install    Install and start the bot as a background service"
        echo "  uninstall  Stop and remove the background service"
        echo "  start      Start the bot service"
        echo "  stop       Stop the bot service"
        echo "  restart    Restart the bot service"
        echo "  status     Show service status and recent logs"
        echo "  logs       Follow the bot logs (Ctrl+C to stop)"
        echo "  errors     Follow the error logs (Ctrl+C to stop)"
        echo ""
        echo "Before installing, make sure to:"
        echo "  1. Get a bot token from @BotFather on Telegram"
        echo "  2. Add TELEGRAM_BOT_TOKEN to $FRIDAY_HOME/config/friday.conf"
        echo "  3. Add your Telegram user ID to TELEGRAM_ALLOWED_USERS"
        echo "     (Message @userinfobot on Telegram to get your ID)"
        ;;
esac
