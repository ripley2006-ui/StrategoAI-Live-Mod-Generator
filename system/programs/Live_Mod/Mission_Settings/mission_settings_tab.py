"""Entry point for the Mission Settings tab."""

from __future__ import annotations

import tkinter as tk

from .gui_ms.gui_ms import MissionSettingsApp


def create_app(parent: tk.Widget, main_app=None) -> MissionSettingsApp:
    """Create and return an instance of the Mission Settings application."""
    return MissionSettingsApp(parent, main_app=main_app)