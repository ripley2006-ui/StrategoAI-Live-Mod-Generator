"""Standalone entrypoint for the Mod Converter window."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[3]

# Add project root to path for proper imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from system.programs.Juke_Box.mod_converter.converter_gui.converter_gui import ModConverterApp, create_app  # noqa: E402


def main() -> None:
    """Run Mod Converter as standalone application."""
    app = ModConverterApp()
    app.run()


if __name__ == "__main__":
    main()
