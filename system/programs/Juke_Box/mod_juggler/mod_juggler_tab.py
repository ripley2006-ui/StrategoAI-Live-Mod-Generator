"""Standalone entrypoint for the Mod Juggler window."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[3]

# Add project root to path for proper imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from system.programs.Juke_Box.mod_juggler.juggler_gui.juggler_gui import ModJugglerApp, create_app  # noqa: E402


def main() -> None:
    """Run Mod Juggler as standalone application."""
    app = ModJugglerApp()
    app.run()


if __name__ == "__main__":
    main()
