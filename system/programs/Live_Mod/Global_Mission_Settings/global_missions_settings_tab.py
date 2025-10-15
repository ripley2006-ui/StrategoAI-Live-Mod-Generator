"""Standalone entrypoint for the Global Mission Settings window."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parents[3]

for candidate in (CURRENT_DIR, PROJECT_ROOT):
    path_str = str(candidate)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from gui_gms.gui_gms import GlobalMissionSettingsApp  # noqa: E402


def main() -> None:
    app = GlobalMissionSettingsApp()
    app.run()


if __name__ == "__main__":
    main()
