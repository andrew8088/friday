# Friday: Personal Assistant Setup Plan

You are helping me bootstrap "Friday" — a CLI-based personal assistant that uses scripts for data wrangling and LLMs for reasoning. The philosophy: deterministic scripts handle filtering/sorting/formatting, Claude handles judgment and synthesis.

## Project Overview

**Stack:**
- TickTick for task management (I have Premium, API access available)
- iCloud Calendar and Google Calendar for scheduling
- Claude Code CLI for LLM interactions
- Shell scripts + jq for data processing
- Markdown files for templates, journals, and context

**Core workflows:**
1. Daily briefing (morning)
2. Task prioritization
3. Weekly review
4. Project gap analysis

## Directory Structure

Create this structure:

```
~/friday/
├── CLAUDE.md                     # Claude Code context and rules
├── README.md                     # Project documentation
├── .claude/
│   └── commands/                 # Slash commands for Claude Code
│       ├── briefing.md           # /briefing
│       ├── review.md             # /review
│       └── triage.md             # /triage
├── bin/
│   ├── friday                    # Main CLI entry point
│   ├── fetch-tasks               # Pull tasks from TickTick
│   ├── fetch-calendar            # Pull calendar from gcalcli
│   ├── compile-briefing          # Assemble daily briefing prompt
│   └── compile-review            # Assemble weekly review prompt
├── lib/
│   ├── filters.sh                # Common jq filters and utilities
│   └── templates.sh              # Prompt template functions
├── templates/
│   ├── daily-briefing.md         # Prompt template for morning briefing
│   ├── weekly-review.md          # Prompt template for weekly review
│   └── task-triage.md            # Prompt template for inbox triage
├── data/
│   └── .gitkeep                  # Cached API responses (gitignored)
├── journal/
│   └── daily/                    # Daily briefing outputs
├── reviews/
│   └── weekly/                   # Weekly review outputs
└── config/
    └── friday.conf               # Configuration (API keys, preferences)
```

## Phase 1: Foundation

### Task 1.1: Create directory structure and base files

Create all directories and placeholder files. The config file should have this structure:

```bash
# ~/friday/config/friday.conf
# Friday configuration

# TickTick API credentials (get from developer.ticktick.com)
TICKTICK_CLIENT_ID=""
TICKTICK_CLIENT_SECRET=""
TICKTICK_ACCESS_TOKEN=""

# Calendar sources
# icalPal is used by default for iCloud/macOS calendars
# Set to true to also include Google Calendar via gcalcli
USE_GCALCLI="false"

# Calendar filters (comma-separated)
# Leave empty to include all calendars
ICALPAL_INCLUDE_CALENDARS=""    # e.g., "Work,Personal,Family"
ICALPAL_EXCLUDE_CALENDARS=""    # e.g., "Birthdays,Holidays"

# Time zone
TIMEZONE="America/Toronto"

# Deep work preferences
DEEP_WORK_HOURS="09:00-11:00,14:00-16:00"
NO_MEETINGS_BEFORE="10:00"

# Review schedule
WEEKLY_REVIEW_DAY="Sunday"
```

### Task 1.2: Create CLAUDE.md

This is the brain of the system. Create a CLAUDE.md with:

```markdown
# Friday — Personal Assistant

You are Friday, Andrew's personal assistant. Your role is judgment and synthesis, not data wrangling.

## Philosophy

Scripts handle: fetching, filtering, sorting, formatting, counting
You handle: prioritization rationale, conflict detection, recommendations, gap analysis, summaries

## About Andrew

- Full-stack developer (Node.js, TypeScript, AWS)
- Boulders 2-3x/week, values deep work
- Time zone: America/Toronto
- Deep work blocks: 9-11am, 2-4pm (protect these)
- No meetings before 10am preferred
- Weekly planning: Sunday evenings

## Data Sources

When data is provided in prompts, trust it — scripts have already filtered and validated.

- **Tasks**: From TickTick, pre-filtered by due date and priority
- **Calendar**: From gcalcli, today's events with times
- **Journal**: Markdown files in journal/daily/

## Response Style

- Direct, no fluff
- Prioritize ruthlessly — top 3 is better than top 10
- Flag conflicts explicitly
- Suggest time blocks when calendar allows
- Be honest about trade-offs

## Available Commands

- `/briefing` — Generate morning briefing
- `/review` — Weekly review
- `/triage` — Process inbox items
```

### Task 1.3: Create the main `friday` CLI script

Create `bin/friday` as the main entry point:

```bash
#!/usr/bin/env bash
set -euo pipefail

FRIDAY_HOME="${FRIDAY_HOME:-$HOME/friday}"
source "$FRIDAY_HOME/config/friday.conf"
source "$FRIDAY_HOME/lib/filters.sh"
source "$FRIDAY_HOME/lib/templates.sh"

usage() {
    cat <<EOF
Usage: friday <command> [options]

Commands:
    morning     Generate daily briefing
    add         Quick-add task to TickTick inbox
    tasks       List today's priority tasks
    calendar    Show today's calendar
    review      Run weekly review
    triage      Process inbox items
    help        Show this help

Examples:
    friday morning              # Get your daily briefing
    friday add "Call dentist"   # Add task to inbox
    friday tasks                # Show priority tasks
EOF
}

cmd_morning() {
    local today=$(date +%Y-%m-%d)
    local prompt=$("$FRIDAY_HOME/bin/compile-briefing")
    
    echo "$prompt" | claude -p - | tee "$FRIDAY_HOME/journal/daily/$today.md"
}

cmd_tasks() {
    "$FRIDAY_HOME/bin/fetch-tasks" | jq -r '.[] | "[\(.priority // 0)] \(.title)"'
}

cmd_calendar() {
    "$FRIDAY_HOME/bin/fetch-calendar"
}

cmd_add() {
    local task="$*"
    if [[ -z "$task" ]]; then
        echo "Usage: friday add <task description>"
        exit 1
    fi
    # Placeholder — implement with tickli or API call
    echo "Adding task: $task"
    tickli task add "$task" --project "Inbox"
}

cmd_review() {
    local week=$(date +%Y-W%V)
    local prompt=$("$FRIDAY_HOME/bin/compile-review")
    
    echo "$prompt" | claude -p - | tee "$FRIDAY_HOME/reviews/weekly/$week.md"
}

cmd_triage() {
    cd "$FRIDAY_HOME"
    claude -p "Run /triage"
}

# Main dispatch
case "${1:-help}" in
    morning)    cmd_morning ;;
    tasks)      cmd_tasks ;;
    calendar)   cmd_calendar ;;
    add)        shift; cmd_add "$@" ;;
    review)     cmd_review ;;
    triage)     cmd_triage ;;
    help|*)     usage ;;
esac
```

Make it executable: `chmod +x bin/friday`

## Phase 2: Data Fetching Scripts

### Task 2.1: Create fetch-tasks script

Create `bin/fetch-tasks`:

```bash
#!/usr/bin/env bash
set -euo pipefail

FRIDAY_HOME="${FRIDAY_HOME:-$HOME/friday}"
source "$FRIDAY_HOME/config/friday.conf"

TODAY=$(date +%Y-%m-%d)
CACHE_FILE="$FRIDAY_HOME/data/tasks-$TODAY.json"

# Use cache if fresh (less than 5 minutes old)
if [[ -f "$CACHE_FILE" ]] && [[ $(find "$CACHE_FILE" -mmin -5 2>/dev/null) ]]; then
    cat "$CACHE_FILE"
    exit 0
fi

# Fetch from TickTick CLI and filter
# Adjust based on which CLI you install (tickli, tick-tick-cli, etc.)
tickli task list --json 2>/dev/null | jq '
    [.[] | select(
        (.dueDate != null and .dueDate <= "'"$TODAY"'") or
        (.priority != null and .priority >= 3)
    )] | sort_by(.priority) | reverse
' | tee "$CACHE_FILE"
```

### Task 2.2: Create fetch-calendar script

Create `bin/fetch-calendar`:

```bash
#!/usr/bin/env bash
set -euo pipefail

FRIDAY_HOME="${FRIDAY_HOME:-$HOME/friday}"
source "$FRIDAY_HOME/config/friday.conf"

TODAY=$(date +%Y-%m-%d)
CACHE_FILE="$FRIDAY_HOME/data/calendar-$TODAY.json"

# Use cache if fresh (less than 5 minutes old)
if [[ -f "$CACHE_FILE" ]] && [[ $(find "$CACHE_FILE" -mmin -5 2>/dev/null) ]]; then
    cat "$CACHE_FILE"
    exit 0
fi

# Collect events from all configured sources
EVENTS="[]"

# icalPal for iCloud/macOS calendars (primary)
if command -v icalPal &> /dev/null; then
    ICAL_EVENTS=$(icalPal eventsToday --days 1 -o json 2>/dev/null | jq '[.[] | {
        title: .title,
        start: .sdate,
        end: .edate,
        location: .location,
        calendar: .calendar,
        allDay: (.all_day // false),
        source: "icalpal"
    }]' 2>/dev/null || echo "[]")
    EVENTS=$(echo "$EVENTS" | jq --argjson new "$ICAL_EVENTS" '. + $new')
fi

# gcalcli for Google Calendar (if configured)
if command -v gcalcli &> /dev/null && [[ "${USE_GCALCLI:-false}" == "true" ]]; then
    # gcalcli doesn't have great JSON output, so we parse TSV
    GCAL_EVENTS=$(gcalcli agenda "$TODAY" "$(date -v+1d +%Y-%m-%d)" --tsv --details length 2>/dev/null | \
        tail -n +2 | \
        jq -R -s '[split("\n")[] | select(length > 0) | split("\t") | {
            title: .[4],
            start: .[0],
            end: .[2],
            location: .[5],
            calendar: "Google",
            allDay: false,
            source: "gcalcli"
        }]' 2>/dev/null || echo "[]")
    EVENTS=$(echo "$EVENTS" | jq --argjson new "$GCAL_EVENTS" '. + $new')
fi

# Sort by start time and cache
echo "$EVENTS" | jq 'sort_by(.start)' | tee "$CACHE_FILE"
```

This script:
- Uses icalPal as the primary source (iCloud + any calendars synced to macOS Calendar)
- Optionally includes gcalcli for Google Calendar (enable with `USE_GCALCLI=true` in config)
- Merges and sorts events from both sources
- Caches results for 5 minutes

### Task 2.3: Create lib/filters.sh

Create `lib/filters.sh` with common utilities:

```bash
#!/usr/bin/env bash
# Common filters and utilities for Friday

# Filter tasks due today or overdue
filter_urgent() {
    local today=$(date +%Y-%m-%d)
    jq '[.[] | select(.dueDate != null and .dueDate <= "'"$today"'")]'
}

# Filter high priority tasks (priority >= 3)
filter_high_priority() {
    jq '[.[] | select(.priority != null and .priority >= 3)]'
}

# Get top N items
top_n() {
    local n="${1:-5}"
    jq ".[:$n]"
}

# Format tasks as markdown list
format_tasks_md() {
    jq -r '.[] | "- [\(.priority // "-")] \(.title)\(.dueDate | if . then " (due: \(.))" else "" end)"'
}

# Count items
count_items() {
    jq 'length'
}

# Format calendar events as readable text
format_calendar_md() {
    jq -r '
        if length == 0 then "No events scheduled"
        else .[] | 
            if .allDay then "• [All Day] \(.title)\(if .location then " @ \(.location)" else "" end)"
            else "• \(.start | split("T")[1] | split(":")[0:2] | join(":")) - \(.title)\(if .location then " @ \(.location)" else "" end)"
            end
        end
    '
}

# Find calendar gaps (potential deep work windows)
find_free_blocks() {
    local min_duration="${1:-60}"  # minimum minutes for a "free" block
    # This is a placeholder - real implementation would parse event times
    # and find gaps longer than min_duration
    echo "TODO: Implement free block detection"
}
```

## Phase 3: Prompt Templates

### Task 3.1: Create daily briefing template

Create `templates/daily-briefing.md`:

```markdown
You are Friday, my personal assistant. Today is {{DATE}} ({{DAY_OF_WEEK}}).

## Today's Calendar
{{CALENDAR}}

## Priority Tasks
These are pre-filtered: overdue items + high priority tasks, sorted by urgency.

{{TASKS}}

## Quick Stats
- Overdue items: {{OVERDUE_COUNT}}
- High priority tasks: {{HIGH_PRIORITY_COUNT}}
- Meetings today: {{MEETING_COUNT}}

## Your Job

1. **Top 3 Focus Areas**: What should I prioritize today? Consider calendar load, task urgency, and energy management.

2. **Conflicts & Concerns**: Flag anything that looks problematic — back-to-back meetings, overdue items that need escalation, etc.

3. **Deep Work Windows**: Given my calendar, when can I do focused work? My preferred blocks are 9-11am and 2-4pm.

Be direct. Prioritize ruthlessly. No fluff.
```

### Task 3.2: Create compile-briefing script

Create `bin/compile-briefing`:

```bash
#!/usr/bin/env bash
set -euo pipefail

FRIDAY_HOME="${FRIDAY_HOME:-$HOME/friday}"
source "$FRIDAY_HOME/lib/filters.sh"

TODAY=$(date +%Y-%m-%d)
DAY_OF_WEEK=$(date +%A)

# Fetch data
TASKS_JSON=$("$FRIDAY_HOME/bin/fetch-tasks")
CALENDAR_JSON=$("$FRIDAY_HOME/bin/fetch-calendar")

# Process tasks
TASKS=$(echo "$TASKS_JSON" | format_tasks_md)
OVERDUE_COUNT=$(echo "$TASKS_JSON" | filter_urgent | count_items)
HIGH_PRIORITY_COUNT=$(echo "$TASKS_JSON" | filter_high_priority | count_items)

# Process calendar - format JSON into readable list
CALENDAR=$(echo "$CALENDAR_JSON" | jq -r '
    if length == 0 then "No events scheduled"
    else .[] | 
        if .allDay then "• [All Day] \(.title)\(if .location then " @ \(.location)" else "" end)"
        else "• \(.start | split("T")[1] | split(":")[0:2] | join(":")) - \(.title)\(if .location then " @ \(.location)" else "" end)"
        end
    end
')

# Count meetings
MEETING_COUNT=$(echo "$CALENDAR_JSON" | jq 'length')

# Read template and substitute
TEMPLATE=$(cat "$FRIDAY_HOME/templates/daily-briefing.md")

echo "$TEMPLATE" | sed \
    -e "s/{{DATE}}/$TODAY/g" \
    -e "s/{{DAY_OF_WEEK}}/$DAY_OF_WEEK/g" \
    -e "s/{{OVERDUE_COUNT}}/$OVERDUE_COUNT/g" \
    -e "s/{{HIGH_PRIORITY_COUNT}}/$HIGH_PRIORITY_COUNT/g" \
    -e "s/{{MEETING_COUNT}}/$MEETING_COUNT/g" | \
    awk -v calendar="$CALENDAR" '{gsub(/\{\{CALENDAR\}\}/, calendar)}1' | \
    awk -v tasks="$TASKS" '{gsub(/\{\{TASKS\}\}/, tasks)}1'
```

### Task 3.3: Create weekly review template

Create `templates/weekly-review.md`:

```markdown
You are Friday, my personal assistant. It's {{DAY_OF_WEEK}}, {{DATE}} — time for the weekly review.

## This Week's Accomplishments
From the daily journals:

{{ACCOMPLISHMENTS}}

## Current Task Inventory

### Overdue (needs attention)
{{OVERDUE_TASKS}}

### Stuck Items (no progress in 7+ days)
{{STUCK_TASKS}}

### Inbox (unprocessed)
{{INBOX_TASKS}}

## Next Week Preview
{{NEXT_WEEK_CALENDAR}}

## Your Job

1. **Week in Review**: What did I actually accomplish? What patterns do you see?

2. **Stuck Item Analysis**: For each stuck item, hypothesize why it's stuck and suggest one concrete next action.

3. **Inbox Triage**: For each inbox item, recommend: Schedule (with suggested date), Delegate, Defer, or Delete.

4. **Next Week Setup**: Given the calendar preview, what should I protect time for? Any heavy days to watch out for?

5. **One Recommendation**: What's one thing I should do differently next week?

Be honest. Challenge me where appropriate.
```

## Phase 4: Claude Code Integration

### Task 4.1: Create slash commands

Create `.claude/commands/briefing.md`:

```markdown
# Daily Briefing

Run the morning briefing workflow:

1. Execute `~/friday/bin/compile-briefing` to gather and format today's data
2. Analyze the compiled prompt
3. Provide the briefing response
4. Save output to journal/daily/{{date}}.md

Start by running the compile-briefing script.
```

Create `.claude/commands/review.md`:

```markdown
# Weekly Review

Run the weekly review workflow:

1. Execute `~/friday/bin/compile-review` to gather the week's data
2. Analyze accomplishments, stuck items, and inbox
3. Provide the review response
4. Save output to reviews/weekly/{{week}}.md

Start by running the compile-review script.
```

Create `.claude/commands/triage.md`:

```markdown
# Inbox Triage

Process items in the TickTick inbox:

1. Run `tickli task list --project Inbox --json` to get inbox items
2. For each item, recommend one of:
   - **Schedule**: Move to a project with a due date
   - **Delegate**: Note who should own this
   - **Defer**: Move to Someday/Maybe with rationale
   - **Delete**: Explain why this isn't actionable

Present recommendations in a table, then ask for confirmation before making any changes.
```

## Phase 5: Polish & Testing

### Task 5.1: Create README.md

Document the project with:
- Quick start instructions
- Configuration guide
- Command reference
- Architecture overview

### Task 5.2: Add to PATH and test

```bash
# Add to shell profile
echo 'export PATH="$HOME/friday/bin:$PATH"' >> ~/.zshrc
echo 'export FRIDAY_HOME="$HOME/friday"' >> ~/.zshrc
source ~/.zshrc

# Test commands
friday help
friday tasks
friday calendar
friday morning
```

### Task 5.3: Set up TickTick API access

1. Go to https://developer.ticktick.com/manage
2. Create an app, set redirect URI to http://localhost:8080/callback
3. Get client ID and secret
4. Run the CLI's auth flow (depends on which CLI you chose)
5. Store tokens in config/friday.conf

### Task 5.4: Set up icalPal (primary calendar source)

```bash
# Install via Homebrew (recommended)
brew tap ajrosen/tap
brew install icalPal

# Or via gem
gem install icalPal

# Test it works
icalPal eventsToday

# List available calendars
icalPal calendars
```

Note: icalPal reads directly from macOS Calendar database—no authentication needed. Any calendar synced to your Mac (iCloud, Exchange, Google, etc.) will be available.

### Task 5.5: Set up gcalcli (optional, for Google Calendar)

Only needed if you have Google calendars that aren't synced to macOS Calendar app:

```bash
# Install
pip install gcalcli

# Authenticate (opens browser)
gcalcli list

# Test
gcalcli agenda

# Enable in Friday config
# Edit config/friday.conf and set USE_GCALCLI="true"
```

## Implementation Notes

- Start with Phase 1-2, get data fetching working before adding LLM parts
- Test each script independently before wiring them together
- The cache in fetch-tasks prevents hammering the API during development
- All scripts should be idempotent — safe to run multiple times
- Journal files are gitignored but reviews might be worth keeping

## Questions for Andrew

Before starting, confirm:
1. Which TickTick CLI do you want to use? (tickli, tick-tick-cli, or custom API wrapper)
2. Do you have any Google calendars that *aren't* synced to macOS Calendar? (If not, you can skip gcalcli entirely)
3. Any additional data sources to include? (Linear, GitHub issues, etc.)
4. Preferred shell? (bash assumed, but can adapt for zsh/fish)
