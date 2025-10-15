"""Entry point for the Mission Settings tab."""

from __future__ import annotations

import tkinter as tk

from .gui_os.gui_os import OptionalSettingsApp


def create_app(parent: tk.Widget, main_app=None) -> OptionalSettingsApp:
    """Create and return an instance of the Mission Settings application."""
    return OptionalSettingsApp(parent, main_app=main_app)