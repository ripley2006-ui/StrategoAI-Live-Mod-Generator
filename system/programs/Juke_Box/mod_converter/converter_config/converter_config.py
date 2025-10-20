"""Static configuration for the Mod Converter UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


WINDOW_TITLE = "StrategoAI - Mod Converter"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 785
WINDOW_MIN_SIZE = (WINDOW_WIDTH, WINDOW_HEIGHT)
WINDOW_MAX_SIZE = (WINDOW_WIDTH, WINDOW_HEIGHT)

LEFT_PANEL_RATIO = 0.40


@dataclass
class ConversionJob:
    """Represents a mod conversion job.

    Attributes:
        source_path: Path to the source file (.ini or .pak)
        source_type: Type of source ("ini" or "pak")
        mod_name: Detected or user-provided mod name
        status: Current status of conversion
        output_path: Path where converted mod will be saved
    """
    source_path: str
    source_type: str
    mod_name: str
    status: str
    output_path: str = ""

    def __hash__(self):
        """Hash based on source path."""
        return hash(self.source_path)

    def __eq__(self, other):
        """Equality based on source path."""
        if not isinstance(other, ConversionJob):
            return False
        return self.source_path == other.source_path


# Conversion source types
SOURCE_TYPES: Sequence[str] = (
    "Foreign Mod INI File",
    "Packed Mod (.pak)",
)

# Conversion status values
STATUS_PENDING = "Pending"
STATUS_EXTRACTING = "Extracting..."
STATUS_CONVERTING = "Converting..."
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"

# Action buttons for the conversion panel
ACTION_BUTTONS: Sequence[tuple[str, str]] = (
    ("Add INI File", "add_ini"),
    ("Add PAK File", "add_pak"),
    ("Start Conversion", "start_conversion"),
    ("Clear Completed", "clear_completed"),
    ("Open Output Folder", "open_output"),
)

DEFAULT_HELP_TEXT = """Mod Converter

This tool converts foreign mod files into Live Mod format.

Supported Sources:
- Foreign Mod INI files (direct conversion)
- Packed Mod .pak files (extract then convert)

Steps:
1. Add files using the buttons on the left
2. Review detected mod names
3. Click "Start Conversion" to process
4. Converted mods will be saved to your templates folder
"""


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
    "ConversionJob",
    "SOURCE_TYPES",
    "STATUS_PENDING",
    "STATUS_EXTRACTING",
    "STATUS_CONVERTING",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "ACTION_BUTTONS",
    "DEFAULT_HELP_TEXT",
    "current_date_string",
]
