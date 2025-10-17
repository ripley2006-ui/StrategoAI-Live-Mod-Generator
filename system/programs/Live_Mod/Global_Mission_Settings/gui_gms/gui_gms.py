"""Tkinter based standalone window for the Global Mission Settings editor."""

from __future__ import annotations

import math
import sys
import ctypes
import traceback
import datetime
import os
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Iterable
from pathlib import Path
import re
try:
    from PIL import Image, ImageTk  # type: ignore
except Exception:
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

from ..config_gms.config_gms import (
    CATEGORY_BUTTONS,
    DEFAULT_HELP_TEXT,
    DIFFICULTY_OPTIONS,
    ROWS_PER_PAGE,
    TEMPLATE_OPTIONS,
    WINDOW_HEIGHT,
    WINDOW_MAX_SIZE,
    WINDOW_MIN_SIZE,
    WINDOW_TITLE,
    WINDOW_WIDTH,
    current_date_string,
    ParameterEntry,
)
from system.gui_utils.unified_dialogs import show_info, show_error, ask_yes_cancel
from system.config_main.live_sync import LiveSyncManager

from ..config_gms.gms_actions import (
    ActionNotImplementedError,
    alternative_ini_editor_action,
    get_current_difficulty_from_work,
    apply_difficulty_to_work,
    clean_all_action,
    multiplayer_settings_action,
    start_fresh_action,
    update_user_info,
    get_user_info,
    enqueue_user_info,
    read_ini_values,
    write_ini_values,
    read_keys_with_comment_state,
    write_keys_with_comment_state,
    _work_ini_path as _resolve_work_ini_path,
)

from system.config_main.main_actions import get_application_base_path

LOG_PATH = Path(__file__).resolve().parent / 'gms_embed.log'

if sys.platform == "win32":
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_CHILD = 0x40000000
    WS_CLIPSIBLINGS = 0x04000000
    WS_POPUP = 0x80000000
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    SW_SHOW = 5
else:
    GWL_STYLE = GWL_EXSTYLE = 0
    WS_CAPTION = WS_THICKFRAME = WS_SYSMENU = 0
    WS_MINIMIZEBOX = WS_MAXIMIZEBOX = WS_CHILD = WS_CLIPSIBLINGS = WS_POPUP = 0
    WS_EX_APPWINDOW = WS_EX_TOOLWINDOW = 0
    SWP_NOSIZE = SWP_NOMOVE = SWP_NOZORDER = SWP_NOACTIVATE = SWP_FRAMECHANGED = 0
    SW_SHOW = 0



class GlobalMissionSettingsApp:
    """Standalone Tk application that mirrors the legacy Global Mission Settings UI."""

    def __init__(self, parent: tk.Widget | None = None, main_app=None) -> None:
        # Allow standalone creation without an external parent
        self.main_app = main_app
        self.root = parent if parent is not None else tk.Tk()

        self._embedded_mode = False
        self._child_style_job: str | None = None

        # This palette is now self-contained and doesn't rely on a host.
        self.palette = {
            "background": "#1d1f23",
            "panel_dark": "#2a2d33",
            "panel_light": "#353941",
            "entry_bg": "#3c414b",
            "entry_fg": "#f5f5f5",
            "entry_border": "#3c414b",
            "text_primary": "#f8fafc",
            "text_muted": "#d1d5db",
            "button_green": "#15803d",
            "button_blue": "#1e3a8a",  # Matching footer blue
            "button_red": "#b91c1c",
            "button_orange": "#f97316",
            "button_gray": "#4b5563",
            "button_text": "#f8fafc",
            "tree_bg": "#2b2f37",
            "tree_alt_bg": "#30343c",
            "tree_fg": "#f8fafc",
            "tree_selected": "#1d4ed8",
        }

        self.style = ttk.Style()
        self.fonts: dict[str, tkfont.Font] = {}
        self._init_fonts()
        self._configure_styles()

        self.rows_per_page = ROWS_PER_PAGE
        self.entries_per_page = self.rows_per_page * 2
        self.page_index = 0

        # Start empty; will populate from work.ini [Global] if available
        self.all_entries = []
        self.entry_index_map = {entry: idx for idx, entry in enumerate(self.all_entries)}
        self.filtered_entries: list[ParameterEntry] = list(self.all_entries)
        self.category_positions = self._build_category_positions(self.all_entries)

        self.search_var = tk.StringVar()
        self.metadata_vars = {
            "mod_name": tk.StringVar(),
            "version": tk.StringVar(),
            "date": tk.StringVar(value=current_date_string()),
            "template": tk.StringVar(value=TEMPLATE_OPTIONS[0]),
            "difficulty": tk.StringVar(value=DIFFICULTY_OPTIONS[0]),
        }

        self.notes_widget: tk.Text | None = None
        self.help_widget: tk.Text | None = None
        self.help_texts: dict[str, str] = {}
        self.parameter_tree: ttk.Treeview | None = None
        self.page_label: ttk.Label | None = None
        self.prev_button: ttk.Button | None = None
        self.next_button: ttk.Button | None = None

        self.category_buttons: list[tuple[str, ttk.Button]] = []
        self.active_category: str | None = None
        self.pending_entry_index: int | None = None

        self.row_entries: dict[str, dict[str, ParameterEntry | None]] = {}
        self.entry_positions_in_view: dict[int, tuple[str, str]] = {}
        self.last_selected_item: str | None = None
        self.last_selected_side: str = "left"

        self.original_labels: dict[tuple[str, str], str] = {}
        self.marquee_data: dict[tuple[str, str], dict[str, object]] = {}
        self.marquee_job: str | None = None
        self.marquee_window = 22
        # Smooth marquee cadence (ms per step) - slower for better readability
        self.marquee_delay_ms = 150
        # Moderate spacing for gentle wrap
        self.marquee_spacing = "   "
        # Pause duration at end before restart (ms)
        self.marquee_pause_ms = 3000
        
        # Flag to prevent view refresh during editing
        self._editing_in_progress = False
        # Flag to force full rebuild on next poll (for Clean All, templates, etc.)
        self._force_full_rebuild = False

        self.root.winfo_toplevel().report_callback_exception = self._handle_callback_exception
        # Try to build entries dynamically from work.ini [Global]
        try:
            self._try_build_entries_from_work_global()
        except Exception:
            pass

        # Preload English help texts (if available)
        try:
            self._load_help_texts()
        except Exception:
            self.help_texts = {}

        self._build_layout()
        self.root.bind("<Destroy>", self._on_destroy)
        # Select default category on launch
        try:
            default_cat = "Spawning & KI-Count"
            if default_cat in CATEGORY_BUTTONS:
                self._set_active_category(default_cat)
                self.page_index = 0
        except Exception:
            pass
        self._refresh_parameter_view()
        # Auto-select first visible parameter so help box is populated
        try:
            self._auto_select_first_row()
        except Exception:
            pass
        # Load parameter values from work.ini for the visible parameter entries
        try:
            self._load_parameters_from_work_ini()
            self._refresh_parameter_view()
        except Exception:
            pass
        # Ensure a selection after loading values
        try:
            self._auto_select_first_row()
        except Exception:
            pass
        # Start LiveSync even when running this window standalone, and force one immediate sync
        try:
            self._live_sync = LiveSyncManager()
            self._live_sync.start(self.root)
            # Unconditional one-time sync for standalone window
            self._live_sync.force_sync_now()
        except Exception:
            self._live_sync = None
        # Load initial values from mirror (read-only at startup)
        try:
            from ..config_gms.gms_actions import get_user_ui_info_from_mirror
            initial = get_user_ui_info_from_mirror()
            self.metadata_vars["mod_name"].set(initial.get("Modname") or "")
            self.metadata_vars["version"].set(initial.get("Version") or "")
            # Always update Date to today's system date (ignore stored date)
            self.metadata_vars["date"].set(current_date_string())
            # Template: keep current value (don't override from mirror)
            # self.metadata_vars["template"].set(...) - intentionally not loaded from mirror
            if self.notes_widget is not None:
                self.notes_widget.delete("1.0", tk.END)
                self.notes_widget.insert("1.0", initial.get("Notes") or "")
        except Exception:
            pass

    def _auto_select_first_row(self) -> None:
        if not self.parameter_tree:
            return
        tree = self.parameter_tree
        children = tree.get_children("")
        if not children:
            return
        first = children[0]
        tree.selection_set(first)
        tree.focus(first)
        self.last_selected_item = first
        self.last_selected_side = "left"
        self._update_help_for_selection()

    def _handle_callback_exception(self, exc: type[BaseException], value: BaseException, tb: object) -> None:
        traceback.print_exception(exc, value, tb)
        show_error(f"Unhandled error: {value}", parent=self.root)

    def _on_destroy(self, _event: tk.Event | None = None) -> None:
        """Clean up resources when the widget is destroyed."""
        self._stop_marquee()
        # Stop file watcher
        if getattr(self, "_work_watch_job", None):
            try:
                self.root.after_cancel(self._work_watch_job)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._work_watch_job = None  # type: ignore[attr-defined]
        # Final flush: write current user info to work.ini and mirror once
        try:
            notes_val = ""
            if self.notes_widget is not None:
                notes_val = self.notes_widget.get("1.0", "end-1c")
            values = {
                "Modname": self.metadata_vars.get("mod_name").get(),
                "Version": self.metadata_vars.get("version").get(),
                "Date": self.metadata_vars.get("date").get(),
                "Notes": notes_val,
                "Template": self.metadata_vars.get("template").get(),
            }
            enqueue_user_info(values, write_work=True, write_mirror=True)
        except Exception:
            pass
    # ------------------------------------------------------------------
    # Font helpers    # ------------------------------------------------------------------
    def _init_fonts(self) -> None:
        self.fonts["body"] = self._create_font(
            ("Arial", 11, "bold"),
            ("Segoe UI", 11, "bold"),
        )
        self.fonts["entry"] = self._create_font(
            ("Arial Narrow", 11, "bold"),
            ("Arial", 11, "bold"),
        )
        # Larger bold font for prominent left-side inputs
        try:
            entry_actual = {}
            try:
                entry_actual = self.fonts["entry"].actual()
            except Exception:
                entry_actual = {"family": "Segoe UI", "size": 11, "weight": "bold"}
            self.fonts["entry_large"] = tkfont.Font(
                family=entry_actual.get("family", "Segoe UI"),
                size=int(entry_actual.get("size", 11)) + 2,
                weight=entry_actual.get("weight", "bold"),
            )
        except Exception:
            # Fallback if font creation fails
            self.fonts["entry_large"] = self._create_font(
                ("Arial Narrow", 13, "bold"),
                ("Segoe UI", 13, "bold"),
                ("Arial", 13, "bold"),
            )
        self.fonts["header"] = self._create_font(
            ("Arial Narrow", 11, "bold"),
            ("Segoe UI", 11, "bold"),
        )
        self.fonts["button"] = self._create_font(
            ("Roboto", 11, "bold"),
            ("Bahnschrift", 11, "bold"),
            ("Arial", 11, "bold"),
            ("Segoe UI", 11, "bold"),
        )
        # Test: Arial Narrow, one point larger for readability
        self.fonts["tree"] = self._create_font(
            ("Arial Narrow", 12, "bold"),
            ("Segoe UI", 12, "bold"),
            ("Arial", 12, "bold"),
        )
        # New font specifically for the parameter names in the tree
        self.fonts["tree_param"] = self._create_font(
            ("Arial Narrow", 12, "bold"),
            ("Segoe UI", 12, "bold"),
        )
        self.fonts["tree_heading"] = self._create_font(
            ("Arial Narrow", 12, "bold"),
            ("Segoe UI", 12, "bold"),
            ("Arial", 12, "bold"),
        )
        # Condensed/narrow font for specific buttons
        self.fonts["button_condensed"] = self._create_font(
            ("Roboto Condensed", 11, "bold"),
            ("Arial Narrow", 11, "bold"),
            ("Bahnschrift Condensed", 11, "bold"),
            ("Segoe UI", 11, "bold"),
        )

    def _create_font(self, *candidates: tuple[str, int, str]) -> tkfont.Font:
        for family, size, weight in candidates:
            try:
                font = tkfont.Font(family=family, size=size, weight=weight)
                if family.lower() in font.actual("family").lower():
                    return font
            except tk.TclError:
                continue
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(size=11, weight="bold")
        return base

    # ------------------------------------------------------------------
    # Style configuration
    # ------------------------------------------------------------------
    def _configure_styles(self) -> None:
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure("GMS.Main.TFrame", background=self.palette["background"])
        self.style.configure("GMS.TFrame", background=self.palette["panel_dark"])

        self.style.configure(
            "GMS.TLabel",
            background=self.palette["panel_dark"],
            foreground=self.palette["text_primary"],
            font=self.fonts["body"],
        )
        self.style.configure(
            "GMS.Section.TLabel",
            background=self.palette["panel_dark"],
            foreground=self.palette["text_muted"],
            font=self.fonts["body"],
        )
        self.style.configure(
            "GMS.Header.TLabel",
            background=self.palette["panel_dark"],
            foreground=self.palette["text_primary"],
            font=self.fonts["header"],
        )

        self.style.configure(
            "GMS.TButton",
            background=self.palette["panel_light"],
            foreground=self.palette["button_text"],
            borderwidth=0,
            focusthickness=0,
            relief=tk.FLAT,
            font=self.fonts["button"],
            padding=(10, 8),
            anchor="center",
        )
        # Define darker pressed shades for each button color
        pressed_shades = {
            "button_green": "#0f5c2a",   # darker green
            "button_blue": "#1e3a8a",    # darker blue (matching footer blue)
            "button_red": "#7f1d1d",     # darker red (matching footer dark red)
            "button_orange": "#c2410c",  # darker orange
            "button_gray": "#374151",    # darker gray
        }
        
        for color_name, style_name in (
            ("button_green", "GMS.Green.TButton"),
            ("button_blue", "GMS.Blue.TButton"),
            ("button_red", "GMS.Red.TButton"),
            ("button_orange", "GMS.Orange.TButton"),
            ("button_gray", "GMS.Gray.TButton"),
        ):
            self.style.configure(
                style_name,
                background=self.palette[color_name],
                foreground=self.palette["button_text"],
                borderwidth=0,
                focusthickness=0,
                relief=tk.FLAT,
                font=self.fonts["button"],
                anchor="center",
            )
            self.style.map(
                style_name,
                background=[
                    ("pressed", pressed_shades[color_name]),
                    ("active", self.palette[color_name])
                ],
                foreground=[("disabled", "#6b7280")],
            )
        
        # Special DarkRed style matching footer Uninstall button (#7f1d1d)
        self.style.configure(
            "GMS.DarkRed.TButton",
            background="#7f1d1d",
            foreground=self.palette["button_text"],
            borderwidth=0,
            focusthickness=0,
            relief=tk.FLAT,
            font=self.fonts["button"],
            anchor="center",
        )
        self.style.map(
            "GMS.DarkRed.TButton",
            background=[
                ("pressed", "#5f1515"),  # even darker on press
                ("active", "#7f1d1d")
            ],
            foreground=[("disabled", "#6b7280")],
        )

        # Dedicated condensed styles (same colors, narrower font) for category button override
        for color_name, style_name in (
            ("button_orange", "GMS.OrangeCondensed.TButton"),
            ("button_gray", "GMS.GrayCondensed.TButton"),
        ):
            self.style.configure(
                style_name,
                background=self.palette[color_name],
                foreground=self.palette["button_text"],
                borderwidth=0,
                focusthickness=0,
                relief=tk.FLAT,
                font=self.fonts["button_condensed"],
                anchor="center",
            )
            self.style.map(
                style_name,
                background=[
                    ("pressed", pressed_shades[color_name]),
                    ("active", self.palette[color_name])
                ],
                foreground=[("disabled", "#6b7280")],
            )

        # Variant: orange button with black arrow/text (for pagination)
        self.style.configure(
            "GMS.OrangeBlack.TButton",
            background=self.palette["button_orange"],
            foreground="#000000",
            borderwidth=0,
            focusthickness=0,
            relief=tk.FLAT,
            font=self.fonts["button"],
            anchor="center",
        )
        self.style.map(
            "GMS.OrangeBlack.TButton",
            background=[
                ("pressed", pressed_shades["button_orange"]),
                ("active", self.palette["button_orange"])
            ],
            foreground=[
                ("!disabled", "#000000"),
                ("active", "#000000"),
                ("pressed", "#000000"),
                ("focus", "#000000"),
                ("disabled", "#000000"),
            ],
        )

        # Note: Red button pressed shade already defined in main loop above
        # Additional hover shade for visual richness
        self.style.map(
            "GMS.Red.TButton",
            background=[
                ("pressed", pressed_shades["button_red"]),
                ("active", "#991b1b"),  # slightly lighter hover shade
            ],
            foreground=[("disabled", "#6b7280")],
        )

        entry_style = {
            "fieldbackground": self.palette["entry_bg"],
            "foreground": self.palette["entry_fg"],
            "bordercolor": self.palette["entry_border"],
            "lightcolor": self.palette["entry_border"],
            "darkcolor": self.palette["entry_border"],
            "insertcolor": self.palette["entry_fg"],
            "padding": (8, 6),
            "relief": tk.FLAT, 
            "borderwidth": 0,
            "font": self.fonts["entry"],
        }
        self.style.configure("GMS.TEntry", **entry_style)
        # Larger variant for left-side metadata inputs (Modname, Version, Date)
        large_entry_style = dict(entry_style)
        large_entry_style["font"] = self.fonts["entry_large"]
        self.style.configure("GMS.Large.TEntry", **large_entry_style)
        combo_style = dict(entry_style)
        combo_style["font"] = self.fonts["button"]
        self.style.configure("GMS.TCombobox", **combo_style)

        # Larger Combobox variant with better contrast and wider dropdown button
        large_combo_style = dict(entry_style)
        large_combo_style["font"] = self.fonts.get("entry_large", self.fonts["entry"])
        large_combo_style["fieldbackground"] = self.palette["entry_bg"]
        large_combo_style["foreground"] = self.palette["entry_fg"]
        large_combo_style["insertcolor"] = self.palette["entry_fg"]
        large_combo_style["background"] = self.palette["panel_light"]
        large_combo_style["arrowsize"] = 22  # make the dropdown button wider
        # Try to colorize the arrow itself to orange (theme-dependent)
        large_combo_style["arrowcolor"] = self.palette["button_orange"]
        self.style.configure("GMS.Large.TCombobox", **large_combo_style)
        # Try to colorize arrow; some themes support this option
        self.style.map(
            "GMS.Large.TCombobox",
            fieldbackground=[("readonly", self.palette["entry_bg"])],
            foreground=[("disabled", "#6b7280"), ("!disabled", self.palette["entry_fg"])],
        )

        # Enlarge the dropdown list font when the Combobox opens (option database)
        try:
            # Some Tk builds honor one or the other pattern; set both for reliability
            self.root.option_add('*TCombobox*Listbox.font', self.fonts.get("entry_large", self.fonts["entry"]))
            self.root.option_add('*TCombobox*Listbox*Font', self.fonts.get("entry_large", self.fonts["entry"]))
        except Exception:
            pass

        self.style.configure(
            "GMS.Treeview",
            background=self.palette["tree_bg"],
            fieldbackground=self.palette["tree_bg"],
            foreground=self.palette["tree_fg"],
            rowheight=26,
            bordercolor=self.palette["panel_light"],
            font=self.fonts["tree"],
        )
        self.style.configure(
            "GMS.Treeview.Heading",
            background=self.palette["panel_light"],
            foreground=self.palette["text_primary"],
            font=self.fonts["tree_heading"],
        )
        self.style.map("Treeview", background=[("selected", self.palette["tree_selected"])])

        # Style for inline editing of values (medium tone background)
        value_edit_style = dict(entry_style)
        value_edit_style["fieldbackground"] = self.palette["panel_light"]
        value_edit_style["foreground"] = self.palette["entry_fg"]
        value_edit_style["insertcolor"] = self.palette["entry_fg"]
        # Match the table font for consistency
        value_edit_style["font"] = self.fonts.get("tree", self.fonts["entry"])
        self.style.configure("GMS.ValueEdit.TEntry", **value_edit_style)

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, style="GMS.Main.TFrame", padding=0, borderwidth=0)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1, uniform="column")
        container.columnconfigure(1, weight=2, uniform="column")
        container.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(container, style="GMS.TFrame", padding=(14, 14, 12, 14))
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.columnconfigure(0, weight=1)

        right_panel = ttk.Frame(container, style="GMS.TFrame", padding=(14, 14, 14, 14))
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)

        self._build_left_panel(left_panel)
        self._build_right_panel(right_panel)
        # Start background watcher to refresh fields when work.ini changes externally
        self._work_watch_job: str | None = None
        self._last_work_mtime: float | None = None
        try:
            self._schedule_work_watch()
        except Exception:
            pass

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Modname:", style="GMS.TLabel").grid(row=0, column=0, sticky="w")
        mod_entry = ttk.Entry(
            parent,
            textvariable=self.metadata_vars["mod_name"],
            style="GMS.Large.TEntry",
            font=self.fonts["entry_large"],
        )
        mod_entry.grid(row=1, column=0, sticky="ew", pady=(2, 8))

        ttk.Label(parent, text="Version:", style="GMS.TLabel").grid(row=2, column=0, sticky="w")
        version_entry = ttk.Entry(
            parent,
            textvariable=self.metadata_vars["version"],
            style="GMS.Large.TEntry",
            font=self.fonts["entry_large"],
        )
        version_entry.grid(row=3, column=0, sticky="ew", pady=(2, 8))

        ttk.Label(parent, text="Date:", style="GMS.TLabel").grid(row=4, column=0, sticky="w")
        date_entry = ttk.Entry(
            parent,
            textvariable=self.metadata_vars["date"],
            style="GMS.Large.TEntry",
            font=self.fonts["entry_large"],
            state="readonly",
        )
        date_entry.grid(row=5, column=0, sticky="ew", pady=(2, 8))

        ttk.Label(parent, text="Notes:", style="GMS.TLabel").grid(row=6, column=0, sticky="w")
        notes = tk.Text(
            parent,
            height=4,
            bg=self.palette["entry_bg"],
            fg=self.palette["entry_fg"],
            insertbackground=self.palette["entry_fg"],
            borderwidth=0,
            highlightthickness=0,
            relief=tk.FLAT,
            font=self.fonts["entry"],
            wrap=tk.WORD,
        )
        notes.grid(row=7, column=0, sticky="ew", pady=(2, 10))
        self.notes_widget = notes
        # Enforce a strict 4-line limit in the Notes field
        def _limit_notes_lines(_evt=None):
            try:
                content = notes.get("1.0", "end-1c")
                if not content:
                    return
                norm = content.replace("\r\n", "\n").replace("\r", "\n")
                lines = norm.split("\n")
                if len(lines) > 4:
                    trimmed = "\n".join(lines[:4])
                    notes.delete("1.0", tk.END)
                    notes.insert("1.0", trimmed)
                    return "break"
            except Exception:
                pass
            return None

        def _on_notes_return(evt):
            # If already 4 lines, block adding a new one
            try:
                content = notes.get("1.0", "end-1c").replace("\r\n", "\n").replace("\r", "\n")
                if content.count("\n") >= 3:
                    try:
                        if hasattr(self, "search_entry") and self.search_entry is not None:
                            self.search_entry.focus_set()
                    except Exception:
                        pass
                    return "break"
            except Exception:
                pass
            return None

        def _on_notes_paste(evt):
            try:
                # Let paste happen, then trim in idle to avoid flicker
                self.root.after_idle(_limit_notes_lines)
            except Exception:
                pass
            return None

        try:
            notes.bind("<KeyRelease>", _limit_notes_lines)
            notes.bind("<Return>", _on_notes_return)
            notes.bind("<<Paste>>", _on_notes_paste)
        except Exception:
            pass
        # Persist when leaving the Notes field (mouse/tab)
        def _on_notes_focus_out(_evt=None):
            self._persist_user_info()
        notes.bind('<FocusOut>', _on_notes_focus_out)

        ttk.Label(parent, text="Grab User Template:", style="GMS.TLabel").grid(row=8, column=0, sticky="w")
        
        # Template dropdown - will be dynamically updated
        self.template_box = ttk.Combobox(
            parent,
            textvariable=self.metadata_vars["template"],
            values=["Select a template..."],  # Start with placeholder
            state="readonly",
            style="GMS.Large.TCombobox",
            font=self.fonts["entry_large"],
        )
        self.template_box.grid(row=9, column=0, sticky="ew", pady=(2, 8))
        
        # Refresh template list when dropdown is opened
        def _on_dropdown_open(evt):
            try:
                # Force immediate refresh of templates
                from ..config_gms.gms_actions import get_available_templates
                templates = get_available_templates()  # Returns list of filenames
                available_templates = ["Select a template..."] + templates
                self.template_box.configure(values=available_templates)
            except Exception:
                pass
        
        # Bind to button press to refresh before opening
        self.template_box.bind('<Button-1>', _on_dropdown_open)
        
        # Load initial templates
        self._refresh_template_dropdown()
        
        # Bind template selection to load action
        def _on_template_selected(evt):
            selected = self.metadata_vars["template"].get()
            if not selected or selected == "Select a template...":
                return
            # Load the template immediately
            self._load_selected_template(selected)
            # Keep the selected template name in the dropdown (don't reset)
        
        self.template_box.bind('<<ComboboxSelected>>', _on_template_selected)

        ttk.Label(parent, text="Difficulty:", style="GMS.TLabel").grid(row=10, column=0, sticky="w")
        difficulty_box = ttk.Combobox(
            parent,
            textvariable=self.metadata_vars["difficulty"],
            values=("Casual", "Standard", "Hard"),
            state="readonly",
            style="GMS.Large.TCombobox",
            font=self.fonts["entry_large"],
        )
        difficulty_box.grid(row=11, column=0, sticky="ew", pady=(2, 10))
        # Initialize difficulty from work.ini ([Inffo] preferred, fallback [Info])
        try:
            self.metadata_vars["difficulty"].set(get_current_difficulty_from_work())
        except Exception:
            pass
        # Apply selected difficulty by replacing only the two target sections
        def _on_difficulty_selected(_evt=None):
            try:
                label = self.metadata_vars["difficulty"].get()
                if label:
                    apply_difficulty_to_work(label)
                    # Force immediate refresh after difficulty change
                    self._force_immediate_refresh()
            except Exception:
                pass
        try:
            difficulty_box.bind('<<ComboboxSelected>>', _on_difficulty_selected)
        except Exception:
            pass

        # Persist when leaving fields (mouse/tab)
        def _bind_focusout(widget: tk.Widget):
            try:
                widget.bind('<FocusOut>', lambda _e: self._persist_user_info())
            except Exception:
                pass
        _bind_focusout(mod_entry)
        _bind_focusout(version_entry)
        _bind_focusout(date_entry)
        # Note: template_box does NOT get focusout binding to avoid conflicts with load action

        # Use tk.Button here to allow centered multi-line text (ttk.Button lacks justify)
        # Add visual pressed feedback
        start_button = tk.Button(
            parent,
            text="Start fresh\n(no Template selected)",
            justify="center",
            bg=self.palette["button_green"],
            fg=self.palette["button_text"],
            activebackground="#0f5c2a",  # darker green when pressed
            activeforeground=self.palette["button_text"],
            relief=tk.FLAT,
            borderwidth=0,
            font=self.fonts["button"],
            command=lambda: self._invoke_action(
                lambda: start_fresh_action(self.metadata_vars.get("difficulty").get()),
                "Start fresh",
            ),
        )
        start_button.grid(row=12, column=0, sticky="ew", pady=(0, 8))

        multiplayer_button = ttk.Button(
            parent,
            text="Multiplayer Settings",
            style="GMS.Blue.TButton",
            command=self._open_multiplayer_settings,
        )
        multiplayer_button.grid(row=13, column=0, sticky="ew", pady=(0, 8))
        # keep a reference for positioning the popup next to this button
        self._multiplayer_button = multiplayer_button

        bottom_buttons = ttk.Frame(parent, style="GMS.TFrame")
        bottom_buttons.grid(row=14, column=0, sticky="ew")
        bottom_buttons.columnconfigure(0, weight=1)
        bottom_buttons.columnconfigure(1, weight=1)

        alt_ini_button = ttk.Button(
            bottom_buttons,
            text="Alternative ini editor",
            style="GMS.Green.TButton",
            command=lambda: self._invoke_action(alternative_ini_editor_action, "Alternative ini editor"),
        )
        alt_ini_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        clean_button = ttk.Button(
            bottom_buttons,
            text="Clean all",
            style="GMS.DarkRed.TButton",
            command=lambda: self._invoke_action(clean_all_action, "Clean all"),
        )
        clean_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Logo area under the bottom buttons (fills remaining space)
        parent.rowconfigure(15, weight=1)
        try:
            logo_frame = ttk.Frame(parent, style="GMS.TFrame")
            logo_frame.grid(row=15, column=0, sticky="nsew")
            logo_frame.columnconfigure(0, weight=1)
            logo_frame.rowconfigure(0, weight=1)

            # Resolve 'system' dir for both dev and frozen builds
            app_base = get_application_base_path()
            logo_path = None
            if app_base is not None:
                logo_path = app_base / 'system' / 'Pic' / 'OtherPic' / 'Logo.png'
            if logo_path and logo_path.exists():
                # Create a wrapper frame to control padding/positioning
                wrapper_frame = tk.Frame(logo_frame, bg=self.palette["panel_dark"])
                wrapper_frame.grid(row=0, column=0, pady=(20, 0))

                # Build the actual logo label inside the wrapper
                self._logo_label = tk.Label(
                    wrapper_frame,
                    bg=self.palette["panel_dark"],
                    borderwidth=0,
                    highlightthickness=0,
                )
                self._logo_label.pack()

                # Store resources for dynamic scaling
                self._logo_src_path = str(logo_path)
                self._logo_pil = None
                self._logo_mode = 'tk'
                if Image is not None:
                    try:
                        self._logo_pil = Image.open(self._logo_src_path).convert("RGBA")
                        self._logo_mode = 'pil'
                    except Exception:
                        self._logo_pil = None
                        self._logo_mode = 'tk'

                def _render_logo_to_size(w: int, h: int) -> None:
                    if w <= 1 or h <= 1:
                        return
                    try:
                        if self._logo_mode == 'pil' and self._logo_pil is not None and ImageTk is not None:
                            iw, ih = self._logo_pil.size
                            if iw <= 0 or ih <= 0:
                                return
                            scale = min(w / iw, h / ih)
                            new_w = max(1, int(iw * scale))
                            new_h = max(1, int(ih * scale))
                            img = self._logo_pil.resize((new_w, new_h), Image.LANCZOS)
                            self._logo_image = ImageTk.PhotoImage(img)
                            self._logo_label.configure(image=self._logo_image)
                        else:
                            # Fallback: Tk PhotoImage with integer subsample (downscale only)
                            base_img = tk.PhotoImage(file=self._logo_src_path)
                            iw, ih = base_img.width(), base_img.height()
                            if iw <= 0 or ih <= 0:
                                return
                            fx = max(1, int((iw + w - 1) / w))
                            fy = max(1, int((ih + h - 1) / h))
                            factor = max(fx, fy)
                            # subsample reduces by integer factor; ensure >=1
                            scaled = base_img.subsample(factor, factor)
                            self._logo_image = scaled  # keep ref
                            self._logo_label.configure(image=self._logo_image)
                    except Exception:
                        pass

                # Debounced resize handler
                self._logo_resize_job = None
                def _on_logo_configure(_event=None):
                    try:
                        if self._logo_resize_job:
                            self.root.after_cancel(self._logo_resize_job)  # type: ignore[arg-type]
                    except Exception:
                        pass
                    def _do():
                        try:
                            w = max(1, logo_frame.winfo_width())
                            h = max(1, logo_frame.winfo_height())
                            # Add small padding so it doesn’t touch borders
                            _render_logo_to_size(max(1, w - 8), max(1, h - 8))
                        except Exception:
                            pass
                    self._logo_resize_job = self.root.after(100, _do)

                # Initial render and bind
                logo_frame.bind('<Configure>', _on_logo_configure)
                _on_logo_configure()
                try:
                    logo_frame.configure(style="GMS.TFrame")
                except Exception:
                    pass
        except Exception:
            # Non-fatal if image cannot be loaded
            pass

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        table_frame = ttk.Frame(parent, style="GMS.TFrame")
        table_frame.grid(row=0, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            table_frame,
            columns=("param_left", "value_left", "param_right", "value_right"),
            show="",  # hide column headers; show only data rows
            style="GMS.Treeview",
            height=self.rows_per_page,
            selectmode="browse",
        )
        # Columns: set value width to fit exactly ~15 chars for space efficiency
        # Target 16-char width to ensure mindestens 15 sichtbar (Padding/Centering einkalkuliert)
        value_width = self._compute_value_column_width(chars=18)
        tree.column("param_left", width=240, anchor="w", stretch=True)
        tree.column("value_left", width=value_width, anchor="center", stretch=False)
        tree.column("param_right", width=240, anchor="w", stretch=True)
        tree.column("value_right", width=value_width, anchor="center", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        tree.bind("<<TreeviewSelect>>", self._on_parameter_selected)
        tree.bind("<ButtonRelease-1>", self._on_row_click)
        tree.bind("<Up>", self._on_arrow_up)
        tree.bind("<Down>", self._on_arrow_down)
        
        # Intercept Tab on the treeview itself to prevent focus loss
        def _tree_tab_handler(event):
            # Check if we have an active editor
            editor = getattr(self, "_value_editor", None)
            if editor and editor.winfo_exists():
                # Let the editor handle it
                return "break"
            return None
        
        tree.bind("<Tab>", _tree_tab_handler)
        tree.bind("<Shift-Tab>", _tree_tab_handler)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        self.parameter_tree = tree

        buttons_frame = ttk.Frame(parent, style="GMS.TFrame")
        buttons_frame.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        buttons_frame.columnconfigure((0, 1, 2, 3), weight=1, uniform="btnrow")
        buttons_frame.rowconfigure((0, 1), weight=1)

        for idx, label in enumerate(CATEGORY_BUTTONS):
            row = 0 if idx < 4 else 1
            col = idx if idx < 4 else idx - 4
            # Use condensed style only for the specific category
            initial_style = (
                "GMS.GrayCondensed.TButton" if label == "Accuracy & Shooting Behavior" else "GMS.Gray.TButton"
            )
            button = ttk.Button(
                buttons_frame,
                text=label,
                style=initial_style,
                command=lambda name=label: self._handle_category_click(name),
            )
            button.grid(row=row, column=col, sticky="ew", padx=4, pady=4)
            self.category_buttons.append((label, button))

        pagination = ttk.Frame(buttons_frame, style="GMS.TFrame")
        pagination.grid(row=1, column=3, sticky="nsew", padx=4, pady=4)
        pagination.columnconfigure(1, weight=1)

        prev_button = ttk.Button(
            pagination,
            text="◄",
            style="GMS.OrangeBlack.TButton",
            command=lambda: self._change_page(-1),
            width=4,
        )
        prev_button.grid(row=0, column=0, sticky="w")

        page_label = ttk.Label(pagination, text="Page 1 / 1", style="GMS.TLabel", anchor="center")
        page_label.grid(row=0, column=1, sticky="ew")

        next_button = ttk.Button(
            pagination,
            text="►",
            style="GMS.OrangeBlack.TButton",
            command=lambda: self._change_page(1),
            width=4,
        )
        next_button.grid(row=0, column=2, sticky="e")

        self.page_label = page_label
        self.prev_button = prev_button
        self.next_button = next_button

        search_label = ttk.Label(parent, text="Search parameter...", style="GMS.Section.TLabel")
        search_label.grid(row=2, column=0, sticky="w", pady=(6, 2))

        # Search field container (38% entry + 10% clear button = 48% total, rest is space)
        search_container = ttk.Frame(parent, style="GMS.TFrame")
        search_container.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        search_container.columnconfigure(0, weight=38)  # 38% for entry (reduced from 45%)
        search_container.columnconfigure(1, weight=62)  # 62% remaining space

        search_entry = ttk.Entry(search_container, textvariable=self.search_var, style="GMS.TEntry")
        search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        # Keep a reference so other handlers (e.g., Notes Enter) can focus it
        try:
            self.search_entry = search_entry
        except Exception:
            pass
        self.search_var.trace_add("write", self._on_search_changed)

        # Clear button
        def _clear_search():
            self.search_var.set("")
            try:
                search_entry.focus_set()
            except Exception:
                pass

        clear_btn = ttk.Button(
            search_container,
            text="Clear",
            style="GMS.Orange.TButton",
            command=_clear_search,
            width=8
        )
        clear_btn.grid(row=0, column=1, sticky="w")

        help_box = tk.Text(
            parent,
            height=4,
            bg=self.palette["entry_bg"],
            fg=self.palette["entry_fg"],
            insertbackground=self.palette["entry_fg"],
            borderwidth=0,
            highlightthickness=0,
            relief=tk.FLAT,
            font=self.fonts["body"],
            wrap=tk.WORD,
        )
        help_box.grid(row=4, column=0, sticky="ew")
        help_box.insert("1.0", DEFAULT_HELP_TEXT)
        help_box.configure(state=tk.DISABLED)
        self.help_widget = help_box

        self._set_active_category(None)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_category_positions(entries: Iterable[ParameterEntry]) -> dict[str, int]:
        positions: dict[str, int] = {}
        for index, entry in enumerate(entries):
            positions.setdefault(entry.category, index)
        return positions

    def _get_filtered_entries(self) -> list[ParameterEntry]:
        query = self.search_var.get().strip().lower()
        entries = self.all_entries
        if self.active_category:
            entries = [e for e in entries if e.category == self.active_category]
        if not query:
            return list(entries)
        return [entry for entry in entries if query in entry.label.lower()]

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_arrow_up(self, event: tk.Event) -> str | None:
        """Navigate up in the tree and start editing."""
        if not self.parameter_tree: return "break"
        
        selection = self.parameter_tree.selection()
        if not selection: return "break"
        
        prev_item = self.parameter_tree.prev(selection[0])
        if not prev_item: return "break"
        
        self.parameter_tree.selection_set(prev_item)
        self.parameter_tree.focus(prev_item)
        
        # Start editing the value in the same column side (left/right)
        self.root.after_idle(lambda: self._begin_value_edit(prev_item, self.last_selected_side))
        return "break"

    def _on_arrow_down(self, event: tk.Event) -> str | None:
        """Navigate down in the tree and start editing."""
        if not self.parameter_tree: return "break"
        
        selection = self.parameter_tree.selection()
        if not selection: return "break"
        
        next_item = self.parameter_tree.next(selection[0])
        if not next_item: return "break"
        
        self.parameter_tree.selection_set(next_item)
        self.parameter_tree.focus(next_item)
        
        # Start editing the value in the same column side (left/right)
        self.root.after_idle(lambda: self._begin_value_edit(next_item, self.last_selected_side))
        return "break"

    def _refresh_template_dropdown(self) -> None:
        """Refresh the template dropdown with available templates."""
        try:
            from ..config_gms.gms_actions import get_available_templates
            templates = get_available_templates()  # Returns list of filenames
            available_templates = ["Select a template..."] + templates
            # Update the dropdown values
            if hasattr(self, 'template_box'):
                self.template_box.configure(values=available_templates)
        except Exception:
            pass

    def _load_selected_template(self, template_name: str) -> None:
        """Load a selected template from the dropdown."""
        try:
            from ..config_gms.gms_actions import load_template
            # template_name is already the filename (e.g., "Strat_RealLife_357.ini")
            success, message = load_template(template_name)
            if success:
                # Keep the template name selected (don't reset to placeholder)
                # The template_name is already set in metadata_vars["template"]
                # Force immediate refresh after template load
                self._force_immediate_refresh()
                show_info(message, parent=self.root)
            else:
                show_error(message, parent=self.root)
        except Exception as exc:
            show_error(f"Failed to load template: {exc}", parent=self.root)

    def _force_immediate_refresh(self) -> None:
        """Force an immediate refresh by calling the poll function directly."""
        # Set the flag first
        self._force_full_rebuild = True
        # Then trigger the poll immediately (don't wait for the 1-second timer)
        try:
            # Cancel any pending poll
            if self._work_watch_job:
                self.root.after_cancel(self._work_watch_job)
        except Exception:
            pass
        # Call poll directly
        try:
            self._poll_work_ini()
        except Exception:
            pass

    def _invoke_action(self, action, label: str) -> None:
        try:
            # Safety confirmation before destructive Clean all action
            if action is clean_all_action:
                resp = ask_yes_cancel(
                    "Do you really want to delete all current parameters?",
                    title="StrategoAI",
                    parent=self.root
                )
                if resp is not True:
                    return
            action()
            # Force immediate refresh for structural changes
            # Check by label name since start_fresh_action is wrapped in lambda
            if action is clean_all_action or label == "Start fresh":
                # Reset template dropdown to placeholder since previous template is no longer active
                try:
                    if "template" in self.metadata_vars:
                        self.metadata_vars["template"].set("Select a template...")
                        if hasattr(self, 'template_box') and self.template_box is not None:
                            # Ensure dropdown values are up to date
                            self._refresh_template_dropdown()
                except Exception:
                    pass
                self._force_immediate_refresh()
        except ActionNotImplementedError as exc:
            show_info(str(exc), parent=self.root)
        except Exception as exc:
            show_error(f"Failed to run '{label}': {exc}", parent=self.root)

    def _handle_category_click(self, category: str) -> None:
        if self.search_var.get().strip():
            show_info(
                "Bitte Suchtext leeren, um Kategorien zu verwenden.",
                parent=self.root
            )
            return

        # Activate category and force start at first page of that category
        self._set_active_category(category)

        # Always show page 1 of the filtered category
        self.page_index = 0

        # Find the index of the first entry in this category (global index for focusing)
        index = self.category_positions.get(category)
        self.pending_entry_index = index if index is not None else None
        # default focus to left side
        self.last_selected_side = "left"
        # refresh filtered view (now limited to this category) and show page 1
        self._refresh_parameter_view()

    def _on_parameter_selected(self, _event: tk.Event | None) -> None:
        if not self.parameter_tree:
            return
        selection = self.parameter_tree.selection()
        if not selection:
            return
        item_id = selection[0]
        self.last_selected_item = item_id
        row = self.row_entries.get(item_id, {})
        if not row.get(self.last_selected_side):
            if row.get("left"):
                self.last_selected_side = "left"
            elif row.get("right"):
                self.last_selected_side = "right"
        self._update_help_for_selection()
        # Activate marquee only for selected row
        try:
            self._stop_marquee()
            self.marquee_data = {}
            left = row.get('left')
            right = row.get('right')
            if left and getattr(left, 'label', ''):
                self._setup_marquee_for_item(item_id, 'left', getattr(left, 'label', ''))
            if right and getattr(right, 'label', ''):
                self._setup_marquee_for_item(item_id, 'right', getattr(right, 'label', ''))
            self._start_marquee_if_needed()
        except Exception:
            pass

    def _on_row_click(self, event: tk.Event) -> None:
        if not self.parameter_tree:
            return
        item_id = self.parameter_tree.identify_row(event.y)
        column = self.parameter_tree.identify_column(event.x)
        if not item_id:
            return
        self.last_selected_item = item_id
        side = "left" if column in ("#1", "#2") else "right"
        row = self.row_entries.get(item_id, {})
        if side == "left" and not row.get("left") and row.get("right"):
            side = "right"
        elif side == "right" and not row.get("right") and row.get("left"):
            side = "left"
        self.last_selected_side = side
        self.parameter_tree.selection_set(item_id)
        self.parameter_tree.focus(item_id)
        self._update_help_for_selection()
        # Start edit immediately when clicking a Value cell
        # Special case: open external INI editor on BoneTargetZones
        try:
            row_ctx = self.row_entries.get(item_id, {})
            model_ctx = row_ctx.get(side)
            ini_key = None
            if model_ctx is not None:
                ini_key = getattr(model_ctx, 'ini_key', None)
            key_guess = (ini_key or self._label_to_ini_key(getattr(model_ctx, 'label', '') if model_ctx is not None else '') or '')
            key_norm = key_guess.replace(' ', '').lstrip('+').strip('"').lower()
            if key_norm == 'bonetargetzones':
                # Launch alternative INI editor and bypass the standard cell editor
                try:
                    alternative_ini_editor_action(jump="BoneTargetZones=")
                except Exception:
                    pass
                return  # IMPORTANT: Stop further processing
        except Exception:
            pass
        if column in ("#2", "#4"):
            edit_side = "left" if column == "#2" else "right"
            # Skip editing when this side has no parameter (blank separator rows)
            try:
                row_ctx = self.row_entries.get(item_id, {})
                if not row_ctx.get(edit_side):
                    return
            except Exception:
                return
            # Use after_idle to ensure Treeview has finalized focus/selection
            self.root.after_idle(lambda: self._begin_value_edit(item_id, edit_side))
        # Activate marquee for hovered/selected row
        try:
            row = self.row_entries.get(item_id, {})
            self._stop_marquee()
            self.marquee_data = {}
            left = row.get('left')
            right = row.get('right')
            if left and getattr(left, 'label', ''):
                self._setup_marquee_for_item(item_id, 'left', getattr(left, 'label', ''))
            if right and getattr(right, 'label', ''):
                self._setup_marquee_for_item(item_id, 'right', getattr(right, 'label', ''))
            self._start_marquee_if_needed()
        except Exception:
            pass

    

    def _on_search_changed(self, *_: object) -> None:
        self.page_index = 0
        self.pending_entry_index = None
        self._set_active_category(None)
        self._refresh_parameter_view()

    def _change_page(self, delta: int) -> None:
        entries_count = len(self.filtered_entries)
        total_pages = max(math.ceil(entries_count / self.entries_per_page), 1) if self.entries_per_page else 1
        if total_pages <= 1:
            return
        self.page_index = (self.page_index + delta) % total_pages
        if self.active_category:
            index = self.category_positions.get(self.active_category)
            if index is not None:
                self.pending_entry_index = index
        self._refresh_parameter_view()

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------
    def _update_tree_values_only(self) -> None:
        """Update only the values in the existing tree view without rebuilding.
        
        This prevents breaking navigation when values change externally.
        """
        if not self.parameter_tree:
            return
        
        # Update values in the tree based on current entry values
        for item_id in self.parameter_tree.get_children(""):
            row = self.row_entries.get(item_id, {})
            left_entry = row.get("left")
            right_entry = row.get("right")
            
            # Update left column value if entry exists
            if left_entry:
                try:
                    self.parameter_tree.set(item_id, "value_left", left_entry.value)
                except Exception:
                    pass
            
            # Update right column value if entry exists
            if right_entry:
                try:
                    self.parameter_tree.set(item_id, "value_right", right_entry.value)
                except Exception:
                    pass

    def _refresh_parameter_view(self) -> None:
        # Skip refresh if currently editing to avoid breaking navigation
        if self._editing_in_progress:
            return
            
        if not self.parameter_tree:
            return

        self._stop_marquee()
        self.parameter_tree.delete(*self.parameter_tree.get_children())
        self.row_entries = {}
        self.entry_positions_in_view = {}
        self.original_labels = {}
        self.marquee_data = {}

        entries = self._get_filtered_entries()
        self.filtered_entries = entries

        total_pages = max(math.ceil(len(entries) / self.entries_per_page), 1) if self.entries_per_page else 1
        if self.page_index >= total_pages:
            self.page_index = total_pages - 1

        start = self.page_index * self.entries_per_page
        end = start + self.entries_per_page if self.entries_per_page else len(entries)
        visible_entries = entries[start:end]

        # Vertical fill: left column top->bottom, then continue in right column top->bottom
        for row_idx in range(self.rows_per_page):
            left_pos = row_idx
            right_pos = row_idx + self.rows_per_page
            left_entry = visible_entries[left_pos] if left_pos < len(visible_entries) else None
            right_entry = visible_entries[right_pos] if right_pos < len(visible_entries) else None
            # Treat blank separators (empty label) as no-entry so navigation skips them
            if left_entry and not str(getattr(left_entry, 'label', '')).strip():
                left_entry = None
            if right_entry and not str(getattr(right_entry, 'label', '')).strip():
                right_entry = None

            if not left_entry and not right_entry:
                values = ("", "", "", "")
            else:
                values = (
                    left_entry.label if left_entry else "",
                    left_entry.value if left_entry else "",
                    right_entry.label if right_entry else "",
                    right_entry.value if right_entry else "",
                )

            item_id = self.parameter_tree.insert(
                "",
                tk.END,
                values=values,
                tags=("odd" if row_idx % 2 else "even",),
            )

            self.row_entries[item_id] = {"left": left_entry, "right": right_entry} 
            
            if left_entry:
                index = self.entry_index_map[left_entry]
                self.entry_positions_in_view[index] = (item_id, "left")
                self.original_labels[(item_id, "left")] = left_entry.label
            if right_entry:
                index = self.entry_index_map[right_entry]
                self.entry_positions_in_view[index] = (item_id, "right")
                self.original_labels[(item_id, "right")] = right_entry.label

        # Configure tags with fonts
        self.parameter_tree.tag_configure(
            "even", background=self.palette["tree_bg"], font=self.fonts["tree"]
        )
        self.parameter_tree.tag_configure(
            "odd", background=self.palette["tree_alt_bg"], font=self.fonts["tree"]
        )
        # Apply the specific font for parameter names to the entire tree
        # The values will inherit this, but since they are in separate columns, it's the standard way.
        self.parameter_tree.configure(style="GMS.Treeview")

        current_page = min(self.page_index + 1, total_pages) if total_pages else 0
        self._update_page_controls(current_page, total_pages)
        self._focus_pending_entry()
        # Marquee is activated lazily on hover/selection

    def _update_page_controls(self, current: int, total: int) -> None:
        if not self.page_label or not self.prev_button or not self.next_button:
            return
        total = max(total, 1)
        current = max(current, 1)
        self.page_label.configure(text=f"Page {current} / {total}")
        state = tk.DISABLED if total <= 1 else tk.NORMAL
        self.prev_button.configure(state=state)
        self.next_button.configure(state=state)

    def _compute_value_column_width(self, *, chars: int = 15) -> int:
        try:
            char_px = int(self.fonts["tree"].measure("0"))
        except Exception:
            char_px = 8
        # small padding for inner cell spacing and selection highlight
        return max(96, chars * char_px + 16)

    def _focus_pending_entry(self) -> None:
        if self.pending_entry_index is None or not self.parameter_tree:
            return
        target = self.entry_positions_in_view.get(self.pending_entry_index)
        if not target:
            self.pending_entry_index = None
            return
        item_id, side = target
        self.parameter_tree.see(item_id)
        self.parameter_tree.selection_set(item_id)
        self.parameter_tree.focus(item_id)
        self.last_selected_item = item_id
        self.last_selected_side = side
        self._update_help_for_selection()
        self.pending_entry_index = None

    def _update_help_box(self, text: str) -> None:
        if not self.help_widget:
            return
        self.help_widget.configure(state=tk.NORMAL)
        self.help_widget.delete("1.0", tk.END)
        self.help_widget.insert("1.0", text)
        self.help_widget.configure(state=tk.DISABLED)

    def _update_help_for_selection(self) -> None:
        if not self.parameter_tree:
            return
        item_id = self.last_selected_item
        if not item_id:
            selection = self.parameter_tree.selection()
            if not selection:
                return
            item_id = selection[0]
        row = self.row_entries.get(item_id, {})
        entry = row.get(self.last_selected_side) or row.get("left") or row.get("right")
        if not entry:
            self._update_help_box("No parameter selected.")
            return
        # Lookup help text by ini key first, then label variants
        keys_to_try: list[str] = []
        try:
            ini_key = getattr(entry, 'ini_key', None)
        except Exception:
            ini_key = None
        if ini_key:
            keys_to_try.append(ini_key)
        # Also try the display label and normalized variants
        lbl = getattr(entry, 'label', '') or ''
        if lbl:
            keys_to_try.append(lbl)
            keys_to_try.append(lbl.replace(' ', ''))
        # Case-insensitive fallback map
        lower_map = {k.lower(): v for k, v in self.help_texts.items()}
        for k in keys_to_try:
            if k in self.help_texts:
                self._update_help_box(self.help_texts[k])
                return
            lk = k.lower()
            if lk in lower_map:
                self._update_help_box(lower_map[lk])
                return
        self._update_help_box(f"No documentation available for '{lbl or ini_key}'.")

    # ------------------------------------------------------------------
    # Help text loading
    # ------------------------------------------------------------------
    def _load_help_texts(self) -> None:
        """Load help texts from system/Help/E_StrategoAI_Help.ini into a dict.

        Sections are marked as [ParamName]. Content continues until next section
        or a '---' separator line. Leading tabs are stripped for readability.
        """
        app_base = get_application_base_path()
        if not app_base:
            return
        help_path = app_base / 'system' / 'Help' / 'E_StrategoAI_Help.ini'
        if not help_path.exists():
            return
        lines = help_path.read_text(encoding='utf-8', errors='ignore').splitlines()
        current: str | None = None
        buf: list[str] = []
        result: dict[str, str] = {}

        def flush() -> None:
            nonlocal current, buf
            if current is None:
                buf = []
                return
            content_lines: list[str] = []
            for ln in buf:
                if ln.strip() == '---':
                    continue
                content_lines.append(ln.lstrip('\t'))
            text = "\n".join(content_lines).strip()
            if text:
                result[current] = text
            buf = []

        for ln in lines:
            st = ln.strip()
            if st.startswith('[') and st.endswith(']') and len(st) > 2:
                flush()
                current = st[1:-1].strip()
                continue
            buf.append(ln)
        flush()
        self.help_texts = result

    def _open_multiplayer_settings(self) -> None:
        keys = [
            "ROEViolationGracePeriod",
            "FriendlyFireEnabled",
            "FriendlyFire",
            "FriendlyTeamKill",
            "UnauthorizedUseofForce",
            "UnauthorizedUseofDeadlyForce",
            "CivilianKilled",
            "KilledanIncapacitatedHuman",
        ]
        state = read_keys_with_comment_state(keys)
        win = tk.Toplevel(self.root)
        win.title("Multiplayer Settings")
        try:
            win.configure(bg=self.palette["panel_dark"])  # type: ignore[index]
        except Exception:
            pass
        frame = ttk.Frame(win, style="GMS.TFrame", padding=(14, 14, 14, 14))
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(2, weight=1)

        # Helpers to write immediately
        def _write_single(k: str, enabled: bool, value: str) -> None:
            try:
                write_keys_with_comment_state({k: (enabled, value)})
            except Exception:
                pass

        # One column list: label + (optional checkbox) + value entry per row
        rows_vars: dict[str, tuple[tk.BooleanVar, tk.StringVar]] = {}
        for r, k in enumerate(keys):
            enabled, val = state.get(k, (True, ""))
            var_en = tk.BooleanVar(value=enabled)
            var_val = tk.StringVar(value=val)

            # Label in column 0
            ttk.Label(frame, text=k, style="GMS.TLabel").grid(row=r, column=0, sticky="w", pady=2)

            # Only ROEViolationGracePeriod gets a checkbox (left of the value field)
            if k == "ROEViolationGracePeriod":
                # Use tk.Checkbutton to avoid white background rectangle and allow visual tuning
                chk = tk.Checkbutton(
                    frame,
                    variable=var_en,
                    bg=self.palette.get("panel_dark", "#2a2d33"),
                    activebackground=self.palette.get("panel_dark", "#2a2d33"),
                    highlightthickness=0,
                    bd=0,
                    padx=4,
                    pady=0,
                    relief=tk.FLAT,
                )
                chk.grid(row=r, column=1, sticky="w", padx=(6, 6))
                def _on_chk_changed(var=var_en, key=k, v=var_val):
                    _write_single(key, var.get(), v.get())
                var_en.trace_add('write', lambda *_: _on_chk_changed())
            else:
                # For other rows, keep enabled state as-is (no checkbox in UI)
                var_en.set(enabled)

            # Value entry in column 2
            ent = ttk.Entry(frame, textvariable=var_val, style="GMS.ValueEdit.TEntry", justify="center", width=7)
            # Match main list font for consistency
            try:
                ent.configure(font=self.fonts.get("tree", self.fonts["entry"]))
            except Exception:
                pass
            ent.grid(row=r, column=2, sticky="w")
            # Live write on focus out
            def _bind_focus_out(e=ent, key=k, en_var=var_en, v_var=var_val):
                try:
                    e.bind('<FocusOut>', lambda _ev: _write_single(key, en_var.get(), v_var.get()))
                    e.bind('<Return>', lambda _ev: (_write_single(key, en_var.get(), v_var.get()), e.selection_clear()))
                except Exception:
                    pass
            _bind_focus_out()

            rows_vars[k] = (var_en, var_val)

        # Close button only; on close ensure a final write of all states
        def _close() -> None:
            data = {k: (en.get(), vv.get()) for k, (en, vv) in rows_vars.items()}
            try:
                write_keys_with_comment_state(data)
            except Exception:
                pass
            win.destroy()

        btns = ttk.Frame(frame, style="GMS.TFrame")
        btns.grid(row=len(keys), column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Close", style="GMS.Gray.TButton", command=_close).grid(row=0, column=0)

        # Position window: to the right of the button, bottom-aligned to button under-edge
        try:
            btn = getattr(self, "_multiplayer_button", None)
            if btn is not None and btn.winfo_ismapped():
                btn.update_idletasks()
                win.update_idletasks()
                # Compute required size after populating
                w = max(420, win.winfo_reqwidth())
                h = max(8 * 28 + 80, win.winfo_reqheight())  # 8 rows + padding heuristic
                x = btn.winfo_rootx() + btn.winfo_width() + 8
                # Align bottom edge with button's bottom edge
                y = btn.winfo_rooty() + btn.winfo_height() - h
                if y < 0:
                    y = 0
                win.geometry(f"{w}x{h}+{x}+{y}")
                try:
                    win.minsize(w, h)
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Parameter <-> work.ini helpers
    # ------------------------------------------------------------------
    def _pretty_label_from_key(self, key: str) -> str:
        try:
            s = key.replace("_", " ").replace(".", " ")
            s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s
        except Exception:
            return key

    def _label_to_ini_key(self, label: str) -> str:
        """Map label to INI key. If label already equals the key, return as-is.
        Fallback: remove spaces only (keep dots for keys like X.Y).
        """
        try:
            return label.replace(" ", "")
        except Exception:
            return label

    def _collect_ini_keys_for_entries(self, entries: Iterable[ParameterEntry]) -> list[str]:
        keys: list[str] = []
        for e in entries:
            ini_key = getattr(e, 'ini_key', None)
            keys.append(ini_key if ini_key else self._label_to_ini_key(e.label))
        return keys

    def _load_parameters_from_work_ini(self) -> None:
        entries = list(self.all_entries)
        keys = self._collect_ini_keys_for_entries(entries)
        values = {}
        try:
            values = read_ini_values(keys)
        except Exception:
            values = {}
        for entry in entries:
            # Use the same key resolution as when writing: prefer explicit ini_key
            k = getattr(entry, 'ini_key', None) or self._label_to_ini_key(entry.label)
            if k in values and values[k] != "":
                try:
                    entry.value = values[k]  # type: ignore[attr-defined]
                except Exception:
                    pass

    def _try_build_entries_from_work_global(self) -> None:
        """Replace demo entries with real [Global] keys from work.ini, preserving category headers.

        - Parses the active work.ini [Global] block
        - Uses comment header lines starting with '# ' to set category if matching known buttons
        - Creates ParameterEntry(label=<key>, value=<value>, category=<detected or last>)
        """
        path = _resolve_work_ini_path()
        if not path.exists():
            return
        text = ""
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return
        # Extract [Global] block
        start = text.find("[Global]")
        if start < 0:
            return
        rest = text[start:]
        end_idx = rest.find("\n[")
        block = rest if end_idx < 0 else rest[: end_idx + 1]
        lines = block.splitlines()
        entries: list[ParameterEntry] = []
        current_cat: str = CATEGORY_BUTTONS[0] if CATEGORY_BUTTONS else "Global"
        known_cats = set(CATEGORY_BUTTONS)
        multiplayer_keys = {
            "ROEViolationGracePeriod",
            "FriendlyFireEnabled",
            "FriendlyFire",
            "FriendlyTeamKill",
            "UnauthorizedUseofForce",
            "UnauthorizedUseofDeadlyForce",
            "CivilianKilled",
            "KilledanIncapacitatedHuman",
        }
        # spacing control flags
        last_was_blank = False
        have_param_in_cat = False
        for ln in lines:
            s = ln.strip()
            if not s:
                # Only keep a single blank after at least one parameter in this category
                if have_param_in_cat and not last_was_blank:
                    entries.append(ParameterEntry("", "", current_cat))
                    last_was_blank = True
                continue
            if s.startswith("#"):
                title = s.lstrip("# ")
                if title in known_cats:
                    current_cat = title
                    have_param_in_cat = False
                    last_was_blank = False
                continue
            if "=" in ln and not s.startswith("["):
                try:
                    key, val = ln.split("=", 1)
                except ValueError:
                    continue
                key = key.strip()
                # Remove leading semicolon (commented lines) before checking against multiplayer_keys
                key_normalized = key.lstrip(';').strip()
                # take raw value (left side of inline comment)
                val = val.split(";", 1)[0].split("#", 1)[0].strip()
                # Skip obviously non-parameter lines
                if not key_normalized:
                    continue
                # Skip multiplayer keys from main list; handled in separate view
                # Use normalized key (without semicolon) for comparison
                if key_normalized in multiplayer_keys:
                    continue
                # Use normalized key for display
                key = key_normalized
                # Store display label prettified, but keep original ini key on the model
                display = self._pretty_label_from_key(key)
                pe = ParameterEntry(display, val, current_cat)
                try:
                    setattr(pe, 'ini_key', key)
                except Exception:
                    pass
                entries.append(pe)
                have_param_in_cat = True
                last_was_blank = False
        if entries:
            self.all_entries = entries
            self.filtered_entries = list(entries)
            self.entry_index_map = {entry: idx for idx, entry in enumerate(self.all_entries)}
            self.category_positions = self._build_category_positions(self.all_entries)

    def _persist_user_info(self, *, immediate: bool = False) -> None:
        """Collect user info fields and persist them.

        - Writes work.ini immediately to avoid losing changes.
        - Mirrors to user_mission_info.json with slight delay to keep UI responsive.
        """
        notes_val = ""
        try:
            if self.notes_widget is not None:
                notes_val = self.notes_widget.get("1.0", "end-1c")
        except Exception:
            notes_val = ""
        values = {
            "Modname": self.metadata_vars.get("mod_name").get(),
            "Version": self.metadata_vars.get("version").get(),
            "Date": self.metadata_vars.get("date").get(),
            "Notes": notes_val,
            "Template": self.metadata_vars.get("template").get(),
        }
        # Primary: update work.ini immediately; mirror is debounced (3s inactivity)
        try:
            enqueue_user_info(values, write_work=True, write_mirror=False)
        except Exception:
            pass
        # Debounced mirror update: after 3s without further edits
        try:
            if hasattr(self, '_mirror_job') and self._mirror_job:
                self.root.after_cancel(self._mirror_job)  # type: ignore[attr-defined]
        except Exception:
            pass
        def _do_mirror():
            try:
                enqueue_user_info(values, write_work=False, write_mirror=True)
            except Exception:
                pass
            finally:
                try:
                    self._mirror_job = None  # type: ignore[attr-defined]
                except Exception:
                    pass
        try:
            self._mirror_job = self.root.after(3000, _do_mirror)  # type: ignore[attr-defined]
        except Exception:
            _do_mirror()

    # ------------------------------------------------------------------
    # External changes watcher (work.ini)
    # ------------------------------------------------------------------
    def _schedule_work_watch(self) -> None:
        # poll every 1000 ms
        self._work_watch_job = self.root.after(1000, self._poll_work_ini)

    def _poll_work_ini(self) -> None:
        try:
            path = _resolve_work_ini_path()
            if not path.exists():
                self._last_work_mtime = None
                self._schedule_work_watch()
                return
            stat = path.stat()
            mtime = stat.st_mtime
            if self._last_work_mtime is None or mtime > self._last_work_mtime:
                # CRITICAL: Update mtime BEFORE any processing to prevent infinite reload loops
                # If we return early during editing, we still need to mark this mtime as "seen"
                self._last_work_mtime = mtime

                # Skip refresh entirely if currently editing (but mtime was already updated above)
                if self._editing_in_progress:
                    return

                # Refresh fields from file
                try:
                    # Check if we need a FULL rebuild (Clean All, Template load, etc.)
                    if self._force_full_rebuild:
                        # Full rebuild: reload structure and values
                        try:
                            self._try_build_entries_from_work_global()
                        except Exception:
                            pass
                        try:
                            self._load_parameters_from_work_ini()
                        except Exception:
                            pass
                        try:
                            self._refresh_parameter_view()
                        except Exception:
                            pass
                        # Clear the UI fields if mirror was deleted
                        try:
                            from ..config_gms.gms_actions import mirror_exists
                            if not mirror_exists():
                                self.metadata_vars["mod_name"].set("")
                                self.metadata_vars["version"].set("")
                                self.metadata_vars["template"].set(self.metadata_vars["template"].get())
                                self.metadata_vars["date"].set(current_date_string())
                                if self.notes_widget is not None:
                                    self.notes_widget.delete("1.0", tk.END)
                        except Exception:
                            pass
                        # Reset the flag
                        self._force_full_rebuild = False
                        return

                    # Small change: only reload VALUES without rebuilding structure
                    try:
                        self._load_parameters_from_work_ini()
                    except Exception:
                        pass

                    # Update only the visible values in the tree without rebuilding
                    try:
                        self._update_tree_values_only()
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            try:
                self._schedule_work_watch()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Category button helpers
    # ------------------------------------------------------------------
    def _set_active_category(self, category: str | None) -> None:
        self.active_category = category
        for label, button in self.category_buttons:
            if category and label == category:
                # Active state
                if label == "Accuracy & Shooting Behavior":
                    button.configure(style="GMS.OrangeCondensed.TButton")
                else:
                    button.configure(style="GMS.Orange.TButton")
            else:
                # Inactive state
                if label == "Accuracy & Shooting Behavior":
                    button.configure(style="GMS.GrayCondensed.TButton")
                else:
                    button.configure(style="GMS.Gray.TButton")

    # ------------------------------------------------------------------
    # Marquee helpers
    # ------------------------------------------------------------------
    def _start_marquee_if_needed(self) -> None:
        if not self.marquee_data or not self.parameter_tree:
            return
        self.marquee_job = self.root.after(self.marquee_delay_ms, self._animate_marquee)

    def _stop_marquee(self) -> None:
        if self.marquee_job:
            self.root.after_cancel(self.marquee_job)
            self.marquee_job = None
        if not self.parameter_tree or not self.parameter_tree.winfo_exists():
            return  # Treeview widget itself is gone
        for (item_id, side), label in self.original_labels.items():
            column = "param_left" if side == "left" else "param_right"
            if self.parameter_tree.exists(item_id):
                self.parameter_tree.set(item_id, column, label)

    def _handle_tab_commit(self, entry: ttk.Entry, item_id: str, side: str, column: str, mode: str) -> str:
        """Handle commit and navigation when Tab/Enter is pressed.
        
        This is separate from the commit callback to ensure _move_to_next_cell
        is called AFTER the entry widget is destroyed.
        
        Returns 'break' to prevent the Tab key from propagating to other widgets.
        """
        # CRITICAL: Calculate the NEXT cell BEFORE destroying the widget
        # because the view might refresh between destroy and the after() callback
        next_target = self._calculate_next_cell(item_id, side, mode=mode)
        
        # Get the value before destroying the widget
        try:
            new_val = entry.get()
        except Exception:
            return "break"
        
        # Update the tree
        try:
            if self.parameter_tree and self.parameter_tree.exists(item_id):
                self.parameter_tree.set(item_id, column, new_val)
        except Exception:
            pass
        
        # Update the model
        row = self.row_entries.get(item_id, {})
        model = row.get(side)
        if model:
            try:
                model.value = new_val  # type: ignore[attr-defined]
            except Exception:
                pass
            # Persist to work.ini
            try:
                ini_key = getattr(model, 'ini_key', None) or self._label_to_ini_key(getattr(model, 'label', ''))
                if ini_key:
                    write_ini_values({ini_key: new_val})
            except Exception:
                pass
        
        # Clean up the entry widget
        try:
            entry.unbind("<Tab>")
            entry.unbind("<ISO_Left_Tab>")
            entry.unbind("<Shift-Tab>")
            entry.unbind("<Return>")
            entry.unbind("<Escape>")
            entry.unbind("<FocusOut>")
            entry.destroy()
        except Exception:
            pass
        self._finalize_edit(next_target)
        
        # NOW move to next cell after the widget is destroyed
        # Use a small delay to ensure the destroy is complete
        if next_target:
            next_item_id, next_side = next_target
            self.root.after(10, lambda: self._navigate_to_cell(next_item_id, next_side))
        
        # CRITICAL: Return 'break' to stop Tab propagation to other widgets
        return "break"

    def _finalize_edit(self, next_target: tuple[str, str] | None = None) -> None:
        """Finalizes the editing process, clears flags, and moves to the next cell if specified."""
        self._value_editor = None  # type: ignore[attr-defined]

        # Keep the editing flag True for a short duration to prevent the file watcher
        # from causing a disruptive refresh immediately after a save.
        def _clear_editing_flag():
            self._editing_in_progress = False

        self.root.after(1500, _clear_editing_flag)

        # If a next target is specified (from Tab navigation), move to it.
        # This is done after a short delay to ensure the UI has processed the destruction
        # of the previous editor widget.
        if next_target:
            self.root.after(10, lambda: self._navigate_to_cell(*next_target))

    def _calculate_next_cell(self, item_id: str, side: str, *, mode: str) -> tuple[str, str] | None:
        """Calculate which cell should be next, without navigating there.
        
        Returns (next_item_id, next_side) or None if no next cell.
        """
        if not self.parameter_tree:
            return None
        items = self.parameter_tree.get_children("")
        try:
            idx = items.index(item_id)
        except ValueError:
            return None

        # Build valid cells list
        valid_cells = []
        for iid in items:
            row = self.row_entries.get(iid, {})
            if row.get("left"):
                valid_cells.append((iid, "left"))
        for iid in items:
            row = self.row_entries.get(iid, {})
            if row.get("right"):
                valid_cells.append((iid, "right"))

        if not valid_cells:
            return None

        # Find current position
        try:
            current_pos = valid_cells.index((item_id, side))
        except ValueError:
            return None

        # Calculate next position
        if mode == "tab" or mode == "enter":
            next_pos = (current_pos + 1)
            if mode == "enter" and next_pos >= len(valid_cells):
                return None
            next_pos %= len(valid_cells)
        elif mode == "shift-tab":
            next_pos = (current_pos - 1 + len(valid_cells)) % len(valid_cells)
        else:
            return None

        return valid_cells[next_pos]

    def _navigate_to_cell(self, item_id: str, side: str) -> None:
        """Navigate to a specific cell and start editing."""
        if not self.parameter_tree:
            return
        # Check if the item still exists
        if not self.parameter_tree.exists(item_id):
            return
        
        self.parameter_tree.see(item_id)
        self.parameter_tree.selection_set(item_id)
        self.parameter_tree.focus(item_id)
        self.last_selected_item = item_id
        self.last_selected_side = side
        self.root.after_idle(lambda: self._begin_value_edit(item_id, side))

    def _begin_value_edit(self, item_id: str, side: str) -> None:
        # Set flag to prevent view refresh during editing
        self._editing_in_progress = True
        
        if not self.parameter_tree:
            self._editing_in_progress = False
            return
        # Do not allow editing on blank separator rows
        try:
            row_ctx = self.row_entries.get(item_id, {})
            if not row_ctx.get(side):
                return
        except Exception:
            return
        # Remove existing editor if present
        editor = getattr(self, "_value_editor", None)
        if editor is not None:
            try:
                editor.destroy()
            except Exception:
                pass
            self._value_editor = None  # type: ignore[attr-defined]

        column = "value_left" if side == "left" else "value_right"
        bbox = self.parameter_tree.bbox(item_id, column)
        if not bbox:
            return
        x, y, w, h = bbox
        current = self.parameter_tree.set(item_id, column)
        # Special editors: TrapType and booleans
        try:
            row_ctx = self.row_entries.get(item_id, {})
            model_ctx = row_ctx.get(side)
            ini_key2 = None
            if model_ctx is not None:
                try:
                    ini_key2 = getattr(model_ctx, 'ini_key', None)
                except Exception:
                    ini_key2 = None
            label_text2 = getattr(model_ctx, 'label', '') if model_ctx is not None else ''
            key_guess2 = (ini_key2 or self._label_to_ini_key(label_text2) or '')
            key_norm2 = key_guess2.replace(' ', '').lstrip('+').strip('"').lower()
            lc2 = (current or '').strip().lower()
            if key_norm2 == 'traptype':
                self._open_traptype_popup(item_id, side, current, x, y, w, h)
                return
            bool_key = False
            try:
                if key_guess2 and (key_guess2.endswith('Enabled') or key_guess2.startswith('Use') or key_guess2.startswith('Enable')):
                    bool_key = True
            except Exception:
                bool_key = False
            if lc2 in ('true','false') or bool_key:
                self._open_bool_popup(
                    item_id,
                    side,
                    (lc2 if lc2 in ('true','false') else ('true' if (current or '').strip().lower() in ('1','yes','on') else 'false')),
                    x, y, w, h,
                    ini_key2 or key_guess2,
                )
                return
        except Exception:
            pass

        # Use a minimal, borderless Entry that visually blends into the cell
        # This avoids the feeling that a big input box appears on click
        row_tags = ()
        try:
            row_tags = tuple(self.parameter_tree.item(item_id, 'tags') or ())
        except Exception:
            row_tags = ()
        cell_bg = self.palette.get('tree_alt_bg') if ('odd' in row_tags) else self.palette.get('tree_bg')
        entry = tk.Entry(
            self.parameter_tree,
            bg=cell_bg,
            fg=self.palette.get('tree_fg'),
            insertbackground=self.palette.get('tree_fg'),
            borderwidth=0,
            highlightthickness=0,
            relief=tk.FLAT,
            justify="center",
        )
        try:
            entry.configure(font=self.fonts.get("tree", self.fonts["entry"]))
        except Exception:
            pass
        entry.insert(0, current)
        entry.icursor(tk.END)
        try:
            entry.focus_set()
        except Exception:
            pass
        entry.place(x=x, y=y, width=w, height=h)

        def commit(_evt: tk.Event | None = None) -> None:
            new_val = entry.get()
            try:
                if self.parameter_tree and self.parameter_tree.exists(item_id):
                    self.parameter_tree.set(item_id, column, new_val)
            except Exception:
                # Row may have been refreshed; ignore
                pass
            row = self.row_entries.get(item_id, {})
            model = row.get(side)
            if model:
                try:
                    model.value = new_val  # type: ignore[attr-defined]
                except Exception:
                    pass
                # Persist this single value to work.ini using derived INI key
                try:
                    ini_key = getattr(model, 'ini_key', None) or self._label_to_ini_key(getattr(model, 'label', ''))
                    if ini_key:
                        write_ini_values({ini_key: new_val})
                        # Don't reload immediately - let the editing flag protect the value
                        # The file watcher will update when editing_in_progress becomes False
                except Exception:
                    pass
            try:
                # Unbind only from this specific entry widget, not all widgets
                entry.unbind("<Tab>")
                entry.unbind("<ISO_Left_Tab>")
                entry.unbind("<Shift-Tab>")
                entry.unbind("<Return>")
                entry.unbind("<Escape>")
                entry.unbind("<FocusOut>")
                entry.destroy()
            finally:
                self._finalize_edit()

        def cancel(_evt: tk.Event | None = None) -> None:
            try:
                entry.destroy()
            finally:
                self._value_editor = None  # type: ignore[attr-defined]

        entry.bind("<Return>", lambda e: self._handle_tab_commit(entry, item_id, side, column, mode="enter") or "break")
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)
        # Tab navigation: Tab forward, Shift+Tab backward
        entry.bind("<Tab>", lambda e: self._handle_tab_commit(entry, item_id, side, column, mode="tab") or "break")
        entry.bind("<ISO_Left_Tab>", lambda e: self._handle_tab_commit(entry, item_id, side, column, mode="shift-tab") or "break")
        entry.bind("<Shift-Tab>", lambda e: self._handle_tab_commit(entry, item_id, side, column, mode="shift-tab") or "break")
        self._value_editor = entry  # type: ignore[attr-defined]

    def _open_bone_single_popup(self, item_id: str, side: str, current: str, x: int, y: int, w: int, h: int) -> None:
        """Popup editor for a single BoneTargetZones= line (similar to TrapType)."""
        options = [
            "head", "spine_3", "spine_2", "spine_1",
            "upperarm_RI", "upperarm_LE", "calf_LE", "calf_RI",
        ]
        selected = {v.strip() for v in (current or '').split(',') if v.strip()}
        win = tk.Toplevel(self.parameter_tree)
        # Track as active editor and ensure navigation works after close
        try:
            self._value_editor = win  # type: ignore[attr-defined]
        except Exception:
            pass
        def _bone_popup_closed(_e=None):
            try:
                self._value_editor = None  # type: ignore[attr-defined]
            except Exception:
                self._finalize_edit()
        try:
            win.bind("<Destroy>", _bone_popup_closed, add=True)
        except Exception:
            pass
        try:
            win.configure(bg=self.palette.get("panel_dark", "#2a2d33"))
        except Exception:
            pass
        # Centered under the edited cell
        try:
            desired_w, desired_h = 320, 180
            rx = self.parameter_tree.winfo_rootx() + x + max(0, (w - desired_w) // 2)
            ry = self.parameter_tree.winfo_rooty() + y + h
            win.geometry(f"{desired_w}x{desired_h}+{rx}+{ry}")
        except Exception:
            pass
        frame = ttk.Frame(win, style="GMS.TFrame", padding=(8, 8, 8, 8))
        frame.pack(fill=tk.BOTH, expand=True)
        vars_map: dict[str, tk.BooleanVar] = {}
        # grid 4 columns x 2 rows
        c = r = 0
        for name in options:
            var = tk.BooleanVar(value=(name in selected))
            vars_map[name] = var
            chk = tk.Checkbutton(
                frame,
                text=name,
                variable=var,
                bg=self.palette.get("panel_dark", "#2a2d33"),
                fg=self.palette.get("button_text", "#f8fafc"),
                activebackground=self.palette.get("panel_dark", "#2a2d33"),
                activeforeground=self.palette.get("button_text", "#f8fafc"),
                highlightthickness=0,
                bd=0,
                selectcolor=self.palette.get("panel_light", "#353941"),
                anchor='w', padx=4, pady=2,
            )
            try:
                chk.configure(font=self.fonts.get("tree", self.fonts["entry"]))
            except Exception:
                pass
            chk.grid(row=r, column=c, sticky="w", padx=(0,10))
            c += 1
            if c >= 4:
                c = 0
                r += 1

        def apply_close() -> None:
            values = [name for name, v in vars_map.items() if v.get()]
            val = ", ".join(values)
            column = "value_left" if side == "left" else "value_right"
            self.parameter_tree.set(item_id, column, val)
            row = self.row_entries.get(item_id, {})
            model = row.get(side)
            if model:
                try:
                    model.value = val  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    # persist to work.ini
                    key = getattr(model, 'ini_key', None) or self._label_to_ini_key(getattr(model, 'label', ''))
                    if key:
                        write_ini_values({key: val})
                except Exception:
                    pass
            try:
                win.destroy()
            finally:
                _bone_popup_closed()
        btns = ttk.Frame(frame, style="GMS.TFrame")
        btns.grid(row=r+1, column=0, columnspan=4, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="OK", style="GMS.Green.TButton", command=apply_close).grid(row=0, column=0)
        ttk.Button(btns, text="Cancel", style="GMS.Gray.TButton", command=win.destroy).grid(row=0, column=1, padx=(6, 0))

    def _open_bool_popup(self, item_id: str, side: str, current_bool: str, x: int, y: int, w: int, h: int, key_guess: str | None) -> None:
        win = tk.Toplevel(self.parameter_tree)
        self._editing_in_progress = True
        # Track as active editor and ensure navigation works after close
        try:
            self._value_editor = win  # type: ignore[attr-defined]
        except Exception:
            pass
        def _bool_popup_closed(_e=None):
            try:
                self._value_editor = None  # type: ignore[attr-defined]
                # Keep editing flag True for a short duration to prevent file watcher
                # from reloading immediately after save
                def _clear_editing_flag():
                    self._editing_in_progress = False
                self.root.after(1500, _clear_editing_flag)
            except Exception: pass
        try:
            win.bind("<Destroy>", _bool_popup_closed, add=True)
        except Exception:
            pass
        try:
            win.configure(bg=self.palette.get("panel_dark", "#2a2d33"))
        except Exception:
            pass
        try:
            rx = self.parameter_tree.winfo_rootx() + x
            ry = self.parameter_tree.winfo_rooty() + y + h
            win.geometry(f"120x80+{rx}+{ry}")
        except Exception:
            pass
        frame = ttk.Frame(win, style="GMS.TFrame", padding=(6,6,6,6))
        frame.pack(fill=tk.BOTH, expand=True)
        def choose(val: str) -> None:
            column = "value_left" if side == "left" else "value_right"
            self.parameter_tree.set(item_id, column, val)
            row = self.row_entries.get(item_id, {})
            model = row.get(side)
            if model:
                try:
                    model.value = val  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    key = (getattr(model, 'ini_key', None) or key_guess or self._label_to_ini_key(getattr(model, 'label', '')))
                    if key:
                        write_ini_values({key: val})
                        # Don't reload immediately - let the editing flag protect the value
                        # The file watcher will update when editing_in_progress becomes False
                except Exception:
                    pass # ignore write errors
            win.destroy()
        # Highlight current value in green
        cur_is_true = (str(current_bool).strip().lower() == 'true')
        true_style = "GMS.Green.TButton" if cur_is_true else "GMS.Gray.TButton"
        false_style = "GMS.Green.TButton" if not cur_is_true else "GMS.Gray.TButton"
        b_true = ttk.Button(frame, text="true", style=true_style, command=lambda: choose('true'))
        b_false = ttk.Button(frame, text="false", style=false_style, command=lambda: choose('false'))
        b_true.pack(fill=tk.X, pady=(0,4))
        b_false.pack(fill=tk.X)

    def _open_traptype_popup(self, item_id: str, side: str, current: str, x: int, y: int, w: int, h: int) -> None:
        options = ["Explosive", "Flashbang", "Alarm"]
        self._editing_in_progress = True
        selected = {v.strip() for v in (current or '').split(',') if v.strip()}
        win = tk.Toplevel(self.parameter_tree)
        # Track as active editor and ensure navigation works after close
        try:
            self._value_editor = win  # type: ignore[attr-defined]
        except Exception:
            pass
        def _trap_popup_closed(_e=None):
            try:
                self._value_editor = None  # type: ignore[attr-defined]
                # Keep editing flag True for a short duration to prevent file watcher
                # from reloading immediately after save
                def _clear_editing_flag():
                    self._editing_in_progress = False
                self.root.after(1500, _clear_editing_flag)
            except Exception: pass
        try:
            win.bind("<Destroy>", _trap_popup_closed, add=True)
        except Exception:
            pass
        try:
            win.configure(bg=self.palette.get("panel_dark", "#2a2d33"))
        except Exception:
            pass
        # Position below the edited cell
        try:
            rx = self.parameter_tree.winfo_rootx() + x
            ry = self.parameter_tree.winfo_rooty() + y + h
            win.geometry(f"240x150+{rx}+{ry}")
        except Exception:
            pass
        frame = ttk.Frame(win, style="GMS.TFrame", padding=(8, 8, 8, 8))
        frame.pack(fill=tk.BOTH, expand=True)
        vars_map: dict[str, tk.BooleanVar] = {}
        for i, name in enumerate(options):
            var = tk.BooleanVar(value=(name in selected))
            vars_map[name] = var
            chk = tk.Checkbutton(
                frame,
                text=name,
                variable=var,
                bg=self.palette.get("panel_dark", "#2a2d33"),
                fg=self.palette.get("button_text", "#f8fafc"),
                activebackground=self.palette.get("panel_dark", "#2a2d33"),
                activeforeground=self.palette.get("button_text", "#f8fafc"),
                highlightthickness=0,
                bd=0,
                selectcolor=self.palette.get("panel_light", "#353941"),
                anchor='w',
                padx=4,
                pady=2,
            )
            try:
                chk.configure(font=self.fonts.get("tree", self.fonts["entry"]))
            except Exception:
                pass
            chk.grid(row=i, column=0, sticky="ew")
        def apply_close() -> None:
            values = [k for k, v in vars_map.items() if v.get()]
            val = ", ".join(values)
            column = "value_left" if side == "left" else "value_right"
            self.parameter_tree.set(item_id, column, val)
            row = self.row_entries.get(item_id, {})
            model = row.get(side)
            if model:
                try:
                    model.value = val  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    key = getattr(model, 'ini_key', None) or self._label_to_ini_key(getattr(model, 'label', ''))
                    if key:
                        write_ini_values({key: val})
                        # Don't reload immediately - let the editing flag protect the value
                        # The file watcher will update when editing_in_progress becomes False
                except Exception: pass
            win.destroy()
        btns = ttk.Frame(frame, style="GMS.TFrame")
        btns.grid(row=len(options), column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="OK", style="GMS.Green.TButton", command=apply_close).grid(row=0, column=0)
        ttk.Button(btns, text="Cancel", style="GMS.Gray.TButton", command=lambda: (win.destroy(), _trap_popup_closed())).grid(row=0, column=1, padx=(6, 0))

    def _move_to_next_cell(self, item_id: str, side: str, *, mode: str) -> None:
        if not self.parameter_tree:
            return
        items = self.parameter_tree.get_children("")
        try:
            idx = items.index(item_id)
        except ValueError:
            return
        target_side = side
        target_idx = idx

        # Build a flat, ordered list of all valid (non-empty) cells in the current view
        # Format: (item_id, side)
        # Column-wise order: all left cells top-to-bottom, then all right cells top-to-bottom
        valid_cells = []
        for iid in items:
            row = self.row_entries.get(iid, {})
            if row.get("left"):
                valid_cells.append((iid, "left"))
        for iid in items:
            row = self.row_entries.get(iid, {})
            if row.get("right"):
                valid_cells.append((iid, "right"))

        if not valid_cells:
            return

        # Find the index of the current cell in the flat list
        try:
            current_pos = valid_cells.index((item_id, side))
        except ValueError:
            # Current cell not found - should not happen in normal operation
            return

        # Determine the next position
        if mode == "tab" or mode == "enter":
            next_pos = (current_pos + 1)
            # For Enter, stop at the very last cell
            if mode == "enter" and next_pos >= len(valid_cells):
                return
            # For Tab, wrap around
            next_pos %= len(valid_cells)
        elif mode == "shift-tab":
            next_pos = (current_pos - 1 + len(valid_cells)) % len(valid_cells)
        else:
            return

        next_item_id, next_side = valid_cells[next_pos]
        self.parameter_tree.see(next_item_id)
        self.parameter_tree.selection_set(next_item_id)
        self.parameter_tree.focus(next_item_id)
        self.last_selected_item = next_item_id
        self.last_selected_side = next_side
        # Force the edit to start with after_idle to ensure UI is ready
        self.root.after_idle(lambda: self._begin_value_edit(next_item_id, next_side))

    def _animate_marquee(self) -> None:
        if not self.parameter_tree or not self.marquee_data:
            self.marquee_job = None
            return

        # Sicherheitsprüfung: Bricht ab, wenn das Widget zerstört wurde.
        if not self.parameter_tree.winfo_exists():
            self.marquee_job = None
            return
        for (item_id, side), data in list(self.marquee_data.items()):
            # Ensure item still exists; drop if not
            try:
                if (not self.parameter_tree) or (not self.parameter_tree.exists(item_id)):
                    self.marquee_data.pop((item_id, side), None)
                    continue
            except Exception:
                self.marquee_data.pop((item_id, side), None)
                continue
            text = str(data.get("text", ""))
            index = int(data.get("index", 0))
            window = int(data.get("window", self.marquee_window))
            nowrap = bool(data.get("nowrap", True))
            pause_counter = int(data.get("pause_counter", 0))
            cycle = len(text) + len(self.marquee_spacing)
            cycles_left = int(data.get("cycles_left", 1))
            column = "param_left" if side == "left" else "param_right"
            if len(text) <= window:
                self.parameter_tree.set(item_id, column, text)
                continue
            if nowrap:
                # Non-wrapping: slide left until the last fully-visible window, then pause, then restore
                end_index = max(0, len(text) - window)
                
                # Check if we're at the end and pausing
                if index >= end_index and pause_counter < self.marquee_pause_ms:
                    # Show final position and increment pause counter
                    slice_text = text[-window:] if window > 0 else text
                    try:
                        self.parameter_tree.set(item_id, column, slice_text)
                    except Exception:
                        self.marquee_data.pop((item_id, side), None)
                        continue
                    data["pause_counter"] = pause_counter + self.marquee_delay_ms
                elif index >= end_index and pause_counter >= self.marquee_pause_ms:
                    # Pause complete: restore to beginning
                    try:
                        if self.parameter_tree and self.parameter_tree.exists(item_id):
                            self.parameter_tree.set(item_id, column, text[:window])
                    except Exception:
                        pass
                    self.marquee_data.pop((item_id, side), None)
                    continue
                else:
                    # Normal scrolling
                    slice_text = text[index : index + window]
                    try:
                        self.parameter_tree.set(item_id, column, slice_text)
                    except Exception:
                        self.marquee_data.pop((item_id, side), None)
                        continue
                    data["index"] = index + 1
                    data["pause_counter"] = 0
            else:
                # Legacy wrapping mode (not used by default now)
                extended = text + self.marquee_spacing + text
                display = extended[index : index + window]
                try:
                    self.parameter_tree.set(item_id, column, display)
                except Exception:
                    self.marquee_data.pop((item_id, side), None)
                    continue
                new_index = (index + 1) % (len(text) + len(self.marquee_spacing))
                cycles_left = max(0, cycles_left - 1) if new_index == 0 else cycles_left
                data["cycles_left"] = cycles_left
                if cycles_left == 0 and new_index == 0:
                    try:
                        if self.parameter_tree and self.parameter_tree.exists(item_id):
                            self.parameter_tree.set(item_id, column, text)
                    except Exception:
                        pass
                    self.marquee_data.pop((item_id, side), None)
                    continue
                data["index"] = new_index
        self.marquee_job = self.root.after(self.marquee_delay_ms, self._animate_marquee)

    def _setup_marquee_for_item(self, item_id: str, side: str, text: str) -> None:
        if not self.parameter_tree:
            return
        column = "param_left" if side == "left" else "param_right"
        try:
            col_width_px = int(self.parameter_tree.column(column, option="width"))
        except Exception:
            col_width_px = 260
        # Determine if text truly exceeds visible width by measuring pixel width
        try:
            text_px = int(self.fonts["tree"].measure(text))
        except Exception:
            text_px = len(text) * 8
        # Allow a small padding margin; also fallback to char-count heuristic
        avg_char_px = max(1, int(self.fonts["tree"].measure("0")))
        window_chars = max(5, (col_width_px - 12) // avg_char_px)
        needs_scroll = (text_px > max(0, col_width_px - 12)) or (len(text) > window_chars)
        if not needs_scroll:
            # Ensure full text is shown and do not start marquee
            try:
                self.parameter_tree.set(item_id, column, text)
            except Exception:
                pass
            return
        # window_chars already computed above
        # Initialize marquee for a single pass (non-wrapping) with pause counter
        self.marquee_data[(item_id, side)] = {
            "text": text,
            "index": 0,
            "window": window_chars,
            "cycles_left": 1,
            "nowrap": True,
            "pause_counter": 0,
        }
        try:
            if self.parameter_tree and self.parameter_tree.exists(item_id):
                self.parameter_tree.set(item_id, column, text[:window_chars])
        except Exception:
            pass

    def _load_selected_template(self, template_name: str) -> None:
        """Load the selected template file.
        
        Shows error dialog if template is invalid format.
        Refreshes the UI after successful load.
        """
        # print(f"[GMS] Loading template: {template_name}")
        
        try:
            from ..config_gms.gms_actions import load_template
            
            success, message = load_template(template_name)
            
            if not success:
                # print(f"[GMS] Template load failed: {message}")
                # Show styled error dialog
                self._show_template_error(message)
                # Reset dropdown to default
                self.metadata_vars["template"].set("Select a template...")
            else:
                # print(f"[GMS] Template loaded successfully, refreshing UI...")
                # Success - reload all parameter data
                try:
                    # Rebuild entries from new work.ini
                    self._try_build_entries_from_work_global()
                    # Reload parameter values
                    self._load_parameters_from_work_ini()
                    # Refresh the view
                    self._refresh_parameter_view()
                    # Reset dropdown to default after loading
                    if self.main_app and hasattr(self.main_app, "refresh_all_live_mod_tabs"):
                        try:
                            self.main_app.refresh_all_live_mod_tabs()
                        except Exception:
                            pass
                    # print(f"[GMS] UI refresh complete")
                except Exception as e:
                    # print(f"[GMS] Error during UI refresh: {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            # print(f"[GMS] Exception in _load_selected_template: {e}")
            import traceback
            traceback.print_exc()
            self._show_template_error(f"Failed to load template: {str(e)}")
            self.metadata_vars["template"].set("Select a template...")

    def _show_template_error(self, message: str) -> None:
        """Show a styled error dialog matching the program design."""
        show_error(message, title="Template Error", parent=self.root)


__all__ = ["GlobalMissionSettingsApp"]
