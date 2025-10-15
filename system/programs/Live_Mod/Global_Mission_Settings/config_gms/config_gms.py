"""Static configuration for the Global Mission Settings standalone window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


WINDOW_TITLE = "StrategoAI - Global Mission Settings"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 785
WINDOW_MIN_SIZE = (WINDOW_WIDTH, WINDOW_HEIGHT)
WINDOW_MAX_SIZE = (WINDOW_WIDTH, WINDOW_HEIGHT)

LEFT_PANEL_RATIO = 0.33
ROWS_PER_PAGE = 19


@dataclass(frozen=True)
class ParameterEntry:
    """Represents an individual editable mission parameter."""

    label: str
    value: str
    category: str


@dataclass(frozen=True)
class ParameterPage:
    """A single parameter page template inside the table view."""

    title: str
    entries: Sequence[ParameterEntry]


CATEGORY_BUTTONS: Sequence[str] = (
    "Spawning & KI-Count",
    "Health & Stun Damage",
    "Accuracy & Shooting Behavior",
    "Morality & Behavior",
    "Sight-Perception-Reaction",
    "Hearing & Reaction",
    "Weapon Firerates",
)

TEMPLATE_OPTIONS: Sequence[str] = (
    "Select a template...",
    "Live Mod Defaults",
    "Hardcore Suppression",
    "Community Favorites",
)

DIFFICULTY_OPTIONS: Sequence[str] = (
    "Standard",
    "Hard",
    "Elite",
)

DEFAULT_HELP_TEXT = "Select a parameter to see its help."


def current_date_string() -> str:
    """Return the current system date in the expected format (DD.MM.YYYY)."""

    return datetime.now().strftime("%d.%m.%Y")


__all__ = [
    "WINDOW_TITLE",
    "WINDOW_WIDTH",
    "WINDOW_HEIGHT",
    "WINDOW_MIN_SIZE",
    "WINDOW_MAX_SIZE",
    "LEFT_PANEL_RATIO",
    "ROWS_PER_PAGE",
    "ParameterEntry",
    "ParameterPage",
    "CATEGORY_BUTTONS",
    "TEMPLATE_OPTIONS",
    "DIFFICULTY_OPTIONS",
    "DEFAULT_HELP_TEXT",
    "current_date_string",
]
