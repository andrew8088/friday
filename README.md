# Friday — Personal Assistant

A CLI-based personal assistant that uses scripts for data wrangling and Claude for reasoning.

**Philosophy**: Deterministic scripts handle filtering/sorting/formatting, Claude handles judgment and synthesis.

## Quick Start

```bash
# Create virtual environment
cd ~/friday
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e .

# Configure TickTick credentials
vim config/friday.conf

# Authenticate
friday auth

# Test
friday tasks
friday calendar
```

## Dependencies

```bash
# gcalcli for Google Calendar
pip install gcalcli
```

## Commands

| Command | Description |
|---------|-------------|
| `friday auth` | Authenticate with TickTick |
| `friday tasks` | List today's priority tasks |
| `friday inbox` | List inbox tasks |
| `friday calendar` | Show today's calendar events |
| `friday morning` | Generate daily briefing with Claude |
| `friday review` | Run weekly review with Claude |
| `friday triage` | Process inbox items with Claude |

All commands support `--json` for machine-readable output.

## Claude Code Integration

When running Claude Code in the `~/friday` directory, these slash commands are available:

- `/briefing` — Generate morning briefing
- `/review` — Weekly review
- `/triage` — Process inbox items

## Architecture

```
~/friday/
├── CLAUDE.md              # Claude's context and personality
├── src/friday/            # Python package
│   ├── cli.py             # Main CLI (click)
│   ├── ticktick.py        # TickTick API + OAuth
│   ├── calendar.py        # gcalcli integration
│   └── config.py          # Configuration management
├── templates/             # Prompt templates
├── config/friday.conf     # Configuration
├── journal/daily/         # Daily briefing outputs
└── reviews/weekly/        # Weekly review outputs
```

## Configuration

Edit `config/friday.conf`:

```bash
# TickTick credentials (from developer.ticktick.com)
TICKTICK_CLIENT_ID="..."
TICKTICK_CLIENT_SECRET="..."

# Calendar sources

# Preferences
TIMEZONE="America/Toronto"
DEEP_WORK_HOURS="09:00-11:00,14:00-16:00"
NO_MEETINGS_BEFORE="10:00"
WEEKLY_REVIEW_DAY="Sunday"
```

## Token Management

OAuth tokens are stored in `config/.tokens.json` (gitignored). The CLI automatically refreshes expired tokens.

To re-authenticate: `friday auth`
