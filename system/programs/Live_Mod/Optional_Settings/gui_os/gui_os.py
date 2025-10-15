"""Optional Settings GUI - 3-column grid for mission-specific optional parameters."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from system.programs.Live_Mod.Mission_Settings.gui_ms.base_card_gui import BaseCardGUI
from ..config_os.actions_os import MissionDef, extract_missions_from_template
from ..config_os.config_os import TEMPLATE_INI, PICS_DIR


class OptionalSettingsApp(BaseCardGUI):
    """Main UI for mission-specific parameter editing."""
    
    def __init__(self, parent: tk.Widget | None = None, main_app=None) -> None:
        self.main_app = main_app
        super().__init__(
            parent,
            extract_missions_func=extract_missions_from_template,
            template_ini_path=TEMPLATE_INI,
            pics_dir_path=PICS_DIR
        )

    def _build_card_content(self, card: ttk.Frame, mission: MissionDef) -> None:
        """Override to remove the 'Grab Template' dropdown for Optional Settings."""
        # Skip row 2 (no template dropdown) and go straight to parameters in row 3
        # Row 3 is already configured with weight=1 in _build_mission_card
        self._build_parameters_list(card, mission)


__all__ = ["OptionalSettingsApp"]
