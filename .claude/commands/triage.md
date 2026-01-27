# Inbox Triage

Process items in the TickTick inbox:

1. Run `tickli task list --project Inbox --json` to get inbox items
2. For each item, recommend one of:
   - **Schedule**: Move to a project with a due date
   - **Delegate**: Note who should own this
   - **Defer**: Move to Someday/Maybe with rationale
   - **Delete**: Explain why this isn't actionable

Present recommendations in a table, then ask for confirmation before making any changes.
