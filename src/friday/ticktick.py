"""TickTick API client with OAuth token management.

This module is preserved for backwards compatibility.
New code should import from friday.core.tasks and friday.adapters.ticktick_api.
"""

# Re-export core Task class
from friday.core.tasks import Task

# Re-export adapter and auth utilities
from friday.adapters.ticktick_api import (
    TickTickAdapter as TickTickClient,
    AuthenticationError,
    authorize,
)

__all__ = [
    "Task",
    "TickTickClient",
    "AuthenticationError",
    "authorize",
]
