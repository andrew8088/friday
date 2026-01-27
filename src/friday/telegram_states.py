"""Conversation states for Telegram bot."""

from enum import IntEnum, auto


class RecapStates(IntEnum):
    """States for the recap conversation."""

    CONFIRM_OVERWRITE = auto()
    WINS = auto()
    BLOCKERS = auto()
    ENERGY = auto()
    TOMORROW = auto()
