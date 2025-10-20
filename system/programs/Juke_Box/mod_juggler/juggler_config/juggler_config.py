"""Static configuration for the Mod Juggler UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


WINDOW_TITLE = "StrategoAI - Mod Juggler"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 785
WINDOW_MIN_SIZE = (WINDOW_WIDTH, WINDOW_HEIGHT)
WINDOW_MAX_SIZE = (WINDOW_WIDTH, WINDOW_HEIGHT)

LEFT_PANEL_RATIO = 0.33
ROWS_PER_PAGE = 19


@dataclass
class ModSetEntry:
    """Represents a mod set configuration.

    Attributes:
        name: Display name of the mod set
        templates: List of template filenames included in this set
        active: Whether this mod set is currently active
        created: Creation date string
    """
    name: str
    templates: list[str]
    active: bool
    created: str

    def __hash__(self):
        """Hash based only on name."""
        return hash(self.name)

    def __eq__(self, other):
        """Equality based only on name."""
        if not isinstance(other, ModSetEntry):
            return False
        return self.name == other.name


# Action buttons for the left panel
ACTION_BUTTONS: Sequence[tuple[str, str]] = (
    ("Create New Set", "create_set"),
    ("Edit Selected Set", "edit_set"),
    ("Delete Selected Set", "delete_set"),
    ("Activate Set", "activate_set"),
    ("Deactivate Set", "deactivate_set"),
    ("Duplicate Set", "duplicate_set"),
    ("Export Set", "export_set"),
    ("Import Set", "import_set"),
)

DEFAULT_HELP_TEXT = "Select a mod set to see details."


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
    "ModSetEntry",
    "ACTION_BUTTONS",
    "DEFAULT_HELP_TEXT",
    "current_date_string",
]
