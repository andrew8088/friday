"""Daily recap data model and utilities.

This module is preserved for backwards compatibility.
New code should import from friday.core.recap.
"""

from pathlib import Path
from datetime import date

# Re-export core types
from friday.core.recap import Recap, RecapMode, determine_recap_mode as _core_determine_mode


def determine_recap_mode(
    target_date: date, journal_dir: Path, ticktick_available: bool
) -> RecapMode:
    """
    Determine which recap mode to use based on available data.

    This wrapper maintains the original signature for backwards compatibility.
    """
    journal_file = journal_dir / f"{target_date.isoformat()}.md"
    has_briefing = journal_file.exists()

    return _core_determine_mode(
        has_briefing=has_briefing,
        has_task_data=ticktick_available,
    )


__all__ = [
    "Recap",
    "RecapMode",
    "determine_recap_mode",
]
