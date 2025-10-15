"""Mission Settings GUI - 3-column grid with 9 pages for mission-specific parameters.

Visual style and interaction patterns match Global Mission Settings for consistency.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..config_ms.config_ms import TEMPLATE_INI, PICS_DIR
from ..config_ms.actions_ms import (
    extract_missions_from_template,
)
from .base_card_gui import BaseCardGUI


class MissionSettingsApp(BaseCardGUI):
    """Main UI for mission-specific parameter editing."""
    
    def __init__(self, parent: tk.Widget | None = None, main_app=None) -> None:
        self.main_app = main_app
        super().__init__(
            parent,
            extract_missions_func=extract_missions_from_template,
            template_ini_path=TEMPLATE_INI,
            pics_dir_path=PICS_DIR
        )

__all__ = ["MissionSettingsApp"]
