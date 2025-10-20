"""Tkinter based UI for the Mod Juggler - Mod Set Management."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageTk  # type: ignore
except Exception:
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

from ..juggler_config.juggler_config import (
    ACTION_BUTTONS,
    DEFAULT_HELP_TEXT,
    WINDOW_HEIGHT,
    WINDOW_MIN_SIZE,
    WINDOW_MAX_SIZE,
    WINDOW_TITLE,
    WINDOW_WIDTH,
    LEFT_PANEL_RATIO,
    ROWS_PER_PAGE,
    ModSetEntry,
    current_date_string,
)

from system.gui_utils.unified_dialogs import show_info, show_error, ask_yes_cancel

from ..juggler_config.juggler_actions import (
    ActionNotImplementedError,
    create_set_action,
    edit_set_action,
    delete_set_action,
    activate_set_action,
    deactivate_set_action,
    duplicate_set_action,
    export_set_action,
    import_set_action,
    get_mod_sets,
    get_available_templates,
)


class ModJugglerApp:
    """Mod Juggler application for managing mod sets.

    This UI allows users to:
    - Create mod sets from templates
    - Activate/deactivate mod sets
    - Edit and manage existing mod sets
    - Import/export mod set configurations
    """

    def __init__(self, parent: tk.Widget | None = None, main_app=None) -> None:
        """Initialize the Mod Juggler application.

        Args:
            parent: Parent widget (for embedded mode) or None (for standalone mode)
            main_app: Reference to the main application instance
        """
        self.main_app = main_app
        self.root = parent if parent is not None else tk.Tk()

        self._embedded_mode = parent is not None

        # Color palette (matching main app style)
        if main_app and hasattr(main_app, 'palette'):
            # Get main app palette and add missing keys with fallbacks
            base_palette = main_app.palette
            self.palette = {
                "background": base_palette.get("background", "#2a2d33"),
                "content_bg": base_palette.get("content_bg", "#1d1f23"),
                "button_bg": base_palette.get("button_bg", base_palette.get("sub_tab_bg", "#4b5563")),
                "button_hover": base_palette.get("button_hover", "#64748b"),
                "text_primary": base_palette.get("text_primary", "#f9fafb"),
                "text_secondary": base_palette.get("text_secondary", "#e5e7eb"),
                "accent": base_palette.get("accent", base_palette.get("sub_tab_bg", "#3b82f6")),
                "border": base_palette.get("border", "#1f2937"),
            }
        else:
            # Default palette for standalone mode
            self.palette = {
                "background": "#2a2d33",
                "content_bg": "#1d1f23",
                "button_bg": "#4b5563",
                "button_hover": "#64748b",
                "text_primary": "#f9fafb",
                "text_secondary": "#e5e7eb",
                "accent": "#3b82f6",
                "border": "#1f2937",
            }

        # State
        self.mod_sets: list[ModSetEntry] = []
        self.selected_set: Optional[ModSetEntry] = None

        # UI Components
        self.main_frame: Optional[tk.Frame] = None
        self.left_panel: Optional[tk.Frame] = None
        self.right_panel: Optional[tk.Frame] = None
        self.mod_set_listbox: Optional[tk.Listbox] = None
        self.details_text: Optional[tk.Text] = None

        # Initialize UI
        self._setup_window()
        self._build_layout()
        self._load_mod_sets()

    def _setup_window(self) -> None:
        """Configure the window properties."""
        if not self._embedded_mode:
            self.root.title(WINDOW_TITLE)
            self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
            self.root.minsize(*WINDOW_MIN_SIZE)
            self.root.maxsize(*WINDOW_MAX_SIZE)
            self.root.configure(bg=self.palette["background"])

    def _build_layout(self) -> None:
        """Build the main UI layout."""
        # Main container
        self.main_frame = tk.Frame(
            self.root,
            bg=self.palette["background"],
            borderwidth=0,
            highlightthickness=0,
        )
        self.main_frame.pack(fill="both", expand=True)

        # Configure grid
        self.main_frame.grid_columnconfigure(0, weight=1, minsize=int(WINDOW_WIDTH * LEFT_PANEL_RATIO))
        self.main_frame.grid_columnconfigure(1, weight=2)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Left panel (mod set list + actions)
        self._build_left_panel()

        # Right panel (details + template selection)
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        """Build the left panel with mod set list and action buttons."""
        self.left_panel = tk.Frame(
            self.main_frame,
            bg=self.palette["content_bg"],
            borderwidth=1,
            relief="solid",
        )
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=5)

        # Title
        title_label = tk.Label(
            self.left_panel,
            text="Mod Sets",
            font=("Segoe UI", 12, "bold"),
            bg=self.palette["content_bg"],
            fg=self.palette["text_primary"],
        )
        title_label.pack(pady=(10, 5))

        # Mod set listbox
        listbox_frame = tk.Frame(self.left_panel, bg=self.palette["content_bg"])
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side="right", fill="y")

        self.mod_set_listbox = tk.Listbox(
            listbox_frame,
            bg=self.palette["background"],
            fg=self.palette["text_primary"],
            selectbackground=self.palette["accent"],
            selectforeground=self.palette["text_primary"],
            font=("Segoe UI", 10),
            yscrollcommand=scrollbar.set,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )
        self.mod_set_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.mod_set_listbox.yview)

        self.mod_set_listbox.bind("<<ListboxSelect>>", self._on_set_selected)

        # Action buttons
        button_frame = tk.Frame(self.left_panel, bg=self.palette["content_bg"])
        button_frame.pack(fill="x", padx=10, pady=10)

        for btn_text, action_id in ACTION_BUTTONS:
            btn = tk.Button(
                button_frame,
                text=btn_text,
                bg=self.palette["button_bg"],
                fg=self.palette["text_primary"],
                font=("Segoe UI", 9),
                borderwidth=0,
                padx=10,
                pady=5,
                cursor="hand2",
                command=lambda aid=action_id: self._execute_action(aid),
            )
            btn.pack(fill="x", pady=2)

            # Hover effects
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=self.palette["button_hover"]))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=self.palette["button_bg"]))

    def _build_right_panel(self) -> None:
        """Build the right panel with mod set details."""
        self.right_panel = tk.Frame(
            self.main_frame,
            bg=self.palette["content_bg"],
            borderwidth=1,
            relief="solid",
        )
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(2, 5), pady=5)

        # Title
        title_label = tk.Label(
            self.right_panel,
            text="Mod Set Details",
            font=("Segoe UI", 12, "bold"),
            bg=self.palette["content_bg"],
            fg=self.palette["text_primary"],
        )
        title_label.pack(pady=(10, 5))

        # Details text widget
        text_frame = tk.Frame(self.right_panel, bg=self.palette["content_bg"])
        text_frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        self.details_text = tk.Text(
            text_frame,
            bg=self.palette["background"],
            fg=self.palette["text_primary"],
            font=("Consolas", 10),
            wrap="word",
            yscrollcommand=scrollbar.set,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.palette["border"],
            state="disabled",
        )
        self.details_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.details_text.yview)

    def _load_mod_sets(self) -> None:
        """Load mod sets from storage and populate the listbox."""
        try:
            sets_data = get_mod_sets()
            self.mod_sets = [
                ModSetEntry(
                    name=s["name"],
                    templates=s["templates"],
                    active=s["active"],
                    created=s["created"],
                )
                for s in sets_data
            ]

            # Update listbox
            if self.mod_set_listbox:
                self.mod_set_listbox.delete(0, tk.END)
                for mod_set in self.mod_sets:
                    display = f"{'[] ' if mod_set.active else '[ ] '}{mod_set.name}"
                    self.mod_set_listbox.insert(tk.END, display)

        except Exception as e:
            show_error(self.root, "Load Error", f"Failed to load mod sets: {e}")

    def _on_set_selected(self, event) -> None:
        """Handle mod set selection."""
        if not self.mod_set_listbox:
            return

        selection = self.mod_set_listbox.curselection()
        if not selection:
            self.selected_set = None
            self._update_details(None)
            return

        idx = selection[0]
        if 0 <= idx < len(self.mod_sets):
            self.selected_set = self.mod_sets[idx]
            self._update_details(self.selected_set)

    def _update_details(self, mod_set: Optional[ModSetEntry]) -> None:
        """Update the details panel with mod set information."""
        if not self.details_text:
            return

        self.details_text.config(state="normal")
        self.details_text.delete("1.0", tk.END)

        if mod_set is None:
            self.details_text.insert("1.0", DEFAULT_HELP_TEXT)
        else:
            details = f"""Mod Set: {mod_set.name}
Status: {'Active' if mod_set.active else 'Inactive'}
Created: {mod_set.created}

Templates ({len(mod_set.templates)}):
"""
            for i, template in enumerate(mod_set.templates, 1):
                details += f"  {i}. {template}\n"

            self.details_text.insert("1.0", details)

        self.details_text.config(state="disabled")

    def _execute_action(self, action_id: str) -> None:
        """Execute an action by its ID."""
        try:
            if action_id == "create_set":
                self._handle_create_set()
            elif action_id == "edit_set":
                self._handle_edit_set()
            elif action_id == "delete_set":
                self._handle_delete_set()
            elif action_id == "activate_set":
                self._handle_activate_set()
            elif action_id == "deactivate_set":
                self._handle_deactivate_set()
            elif action_id == "duplicate_set":
                self._handle_duplicate_set()
            elif action_id == "export_set":
                self._handle_export_set()
            elif action_id == "import_set":
                self._handle_import_set()
            else:
                show_info(self.root, "Info", f"Action '{action_id}' not implemented yet.")

        except ActionNotImplementedError as e:
            show_info(self.root, "Not Implemented", str(e))
        except Exception as e:
            show_error(self.root, "Error", f"Action failed: {e}")

    # Action handlers (placeholders for now)

    def _handle_create_set(self) -> None:
        """Handle create new mod set action."""
        show_info(self.root, "Create Set", "Create Set dialog will be implemented here.")

    def _handle_edit_set(self) -> None:
        """Handle edit mod set action."""
        if not self.selected_set:
            show_info(self.root, "No Selection", "Please select a mod set to edit.")
            return
        show_info(self.root, "Edit Set", f"Edit dialog for '{self.selected_set.name}' will be implemented here.")

    def _handle_delete_set(self) -> None:
        """Handle delete mod set action."""
        if not self.selected_set:
            show_info(self.root, "No Selection", "Please select a mod set to delete.")
            return

        if ask_yes_cancel(self.root, "Confirm Delete", f"Delete mod set '{self.selected_set.name}'?"):
            show_info(self.root, "Delete", "Delete functionality will be implemented here.")

    def _handle_activate_set(self) -> None:
        """Handle activate mod set action."""
        if not self.selected_set:
            show_info(self.root, "No Selection", "Please select a mod set to activate.")
            return
        show_info(self.root, "Activate", f"Activate '{self.selected_set.name}' will be implemented here.")

    def _handle_deactivate_set(self) -> None:
        """Handle deactivate mod set action."""
        if not self.selected_set:
            show_info(self.root, "No Selection", "Please select a mod set to deactivate.")
            return
        show_info(self.root, "Deactivate", f"Deactivate '{self.selected_set.name}' will be implemented here.")

    def _handle_duplicate_set(self) -> None:
        """Handle duplicate mod set action."""
        if not self.selected_set:
            show_info(self.root, "No Selection", "Please select a mod set to duplicate.")
            return
        show_info(self.root, "Duplicate", f"Duplicate '{self.selected_set.name}' will be implemented here.")

    def _handle_export_set(self) -> None:
        """Handle export mod set action."""
        if not self.selected_set:
            show_info(self.root, "No Selection", "Please select a mod set to export.")
            return
        show_info(self.root, "Export", f"Export '{self.selected_set.name}' will be implemented here.")

    def _handle_import_set(self) -> None:
        """Handle import mod set action."""
        show_info(self.root, "Import", "Import mod set dialog will be implemented here.")

    def run(self) -> None:
        """Start the application main loop (standalone mode only)."""
        if not self._embedded_mode:
            self.root.mainloop()


def create_app(parent: tk.Widget, main_app=None) -> ModJugglerApp:
    """Factory function to create a Mod Juggler app instance.

    Args:
        parent: Parent widget for embedded mode
        main_app: Reference to main application

    Returns:
        ModJugglerApp instance
    """
    return ModJugglerApp(parent, main_app=main_app)


__all__ = ["ModJugglerApp", "create_app"]
