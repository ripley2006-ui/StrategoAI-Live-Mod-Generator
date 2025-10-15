"""Configuration constants for the Mission Settings GUI."""

from __future__ import annotations

from pathlib import Path
import sys

from system.config_main.main_actions import get_application_base_path


APP_BASE = get_application_base_path()
SYSTEM_DIR = APP_BASE / "system"
TEMPLATE_INI = SYSTEM_DIR / "templates" / "mod_install" / "Difficulties" / "StandardDifficulty.ini"
PICS_DIR = SYSTEM_DIR / "Pic"