"""GUI layer for the StrategoAI Live Generator."""

from __future__ import annotations

import importlib
import subprocess
import sys
import traceback
import os
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import datetime
import logging
import tkinter as tk
from tkinter import messagebox

# Statische Imports für Nuitka - Module müssen zur Compile-Zeit bekannt sein
# Diese Imports ermöglichen es Nuitka, die Module einzubinden, auch wenn sie
# später dynamisch mit importlib.import_module() geladen werden
try:
    import system.programs.live_Mod.Mission_settings_tab
    import system.programs.live_Mod.Optional_settings_tab
    # Weitere Sub-Tab Module hier hinzufügen, falls vorhanden
except ImportError:
    pass  # Falls Module fehlen, trotzdem weitermachen

from system.config_main.config_main import get_config
from system.config_main.main_actions import (
    ActionExecutionError,
    ActionNotFound,
    ButtonState,
    resolve_action_state,
    run_action,
)
from system.programs.Live_Mod.Global_Mission_Settings.gui_gms.gui_gms import GlobalMissionSettingsApp
from system.gui_utils.custom_titlebar import CustomTitleBar
from system.config_main.live_sync import LiveSyncManager

CONFIG_RELATIVE = Path("system/config_main/config_main.py")

CONFIG_RELATIVE = Path("system/config_main/config_main.py")

def _resolve_project_root() -> Path:
    """Get the application root directory.
    - When frozen (EXE): Directory where the EXE is located.
    - When in development: Project root (parent of 'system' folder).
    """
    if getattr(sys, "frozen", False):
        # Running as a bundled EXE from PyInstaller or Nuitka
        return Path(sys.executable).resolve().parent
    # Running as a script in a development environment
    # Walk up from this file until we find the directory containing 'system'
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "system").is_dir():
            return parent
    return p.parents[2]  # Fallback


try:
    _dwmapi = ctypes.windll.dwmapi
except Exception:  # pragma: no cover
    _dwmapi = None

try:
    _uxtheme = ctypes.windll.uxtheme
except Exception:  # pragma: no cover
    _uxtheme = None

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
PREFERRED_APP_MODE_ALLOW_DARK = 1


def _set_process_app_theme() -> None:
    """Set the application theme to allow dark mode.
 This should be called before creating the main Tk window.
 """
    if sys.platform != "win32" or not _uxtheme:
        return

    try:
        # Explicitly load functions by their ordinal number for maximum compatibility.
        # SetPreferredAppMode (135) is for Win10 1903+
        # AllowDarkModeForApp (133) is for Win10 1809+
        set_preferred_app_mode = _uxtheme[135]
        set_preferred_app_mode.argtypes = (ctypes.c_int,)
        set_preferred_app_mode.restype = ctypes.c_int

    
        allow_dark_mode_for_app = _uxtheme[133]
        allow_dark_mode_for_app.argtypes = (ctypes.c_bool,)
        allow_dark_mode_for_app.restype = ctypes.c_int

        set_preferred_app_mode(PREFERRED_APP_MODE_ALLOW_DARK)
        allow_dark_mode_for_app(True)

    except Exception:
        pass


def enable_dark_title_bar(window: tk.Misc, *, caption_color: str = "#0f172a", text_color: str = "#f9fafb") -> None:
    """Enable dark mode title bar on supported Windows versions."""

    if sys.platform != "win32":
        return

    
  # This function is called via `after`, so the window should be ready.
    try:
        hwnd = window.winfo_id()
    except tk.TclError:
        # Window might be destroyed, so we can't get an ID.
        return

    if _uxtheme:
        try:
            set_app_mode = getattr(_uxtheme, "SetPreferredAppMode", None)
            allow_app = getattr(_uxtheme, "AllowDarkModeForApp", None)
            allow_window = getattr(_uxtheme, "AllowDarkModeForWindow", None)

            if set_app_mode:
                set_app_mode(PREFERRED_APP_MODE_ALLOW_DARK)
            
            elif allow_app:
                allow_app(True)

            if allow_window:
                allow_window(hwnd, True)
        except Exception:
            pass

    if _dwmapi:
        # Request immersive dark title bar where supported
        value = ctypes.c_int(1)
        for attr in (DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1):
            try:
                _dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass

        # Explicitly set caption (title bar) and text colors when available (Win 11)
        try:
            caption_ref = ctypes.c_int(_hex_to_colorref(caption_color))
            text_ref = ctypes.c_int(_hex_to_colorref(text_color))
            _dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(caption_ref), ctypes.sizeof(caption_ref))
            _dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text_ref), ctypes.sizeof(text_ref))
        except Exception:
            # Older Windows versions may not support these attributes
            pass


def _hex_to_colorref(color: str) -> int:
    r, g, b = _hex_to_rgb(color)
    return (b << 16) | (g << 8) | r


@dataclass
class ProgramConfig:
    """Structured data for a launchable program."""

    title: str
    enabled: bool
    program_path: str
    program_args: List[str]
    run_with_python: bool
    working_dir: str


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in range(0, 6, 2))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{min(max(v, 0), 255):02x}" for v in rgb)


def adjust_color(color: str, factor: float) -> str:
    
    """Lighten (>1) or darken (<1) a hex color."""

    r, g, b = _hex_to_rgb(color)
    adjusted = (int(r * factor), int(g * factor), int(b * factor))
    return _rgb_to_hex(adjusted)


class StrategoAILiveGeneratorApp:
    def __init__(self, root: Optional[tk.Tk] = None) -> None:
        _set_process_app_theme()
        self.root = root or tk.Tk()
        self.config = get_config()
        self.palette = self.config["palette"]
        self.button_styles: Dict[str, Dict[str, str]] = self.config.get("button_styles", {})
        self.window_config = self.config["window"]
        self.project_root = _resolve_project_root()

        self.root.title(self.window_config.get("title", "StrategoAI Live Generator"))
        
        # Set application icon
        icon_path = self.project_root / "system" / "Pic" / "OtherPic" / "strategoai.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass  # Ignore if icon cannot be loaded
        
        width = self.window_config.get('width', 1280)
        height = self.window_config.get('height', 880)
        x = self.window_config.get('x')
        y = self.window_config.get('y')
        if x is not None and y is not None:
            geometry = f"{width}x{height}+{x}+{y}"
        else:
            geometry = f"{width}x{height}"
        self.root.geometry(geometry)
        if not self.window_config.get("resizable", False):
            self.root.resizable(False, False)
        self.root.configure(bg=self.palette["background"])

        # Disable custom title bar for reliability (Taskbar/Alt-Tab, rendering)
        self._custom_title_enabled = False
        self._title_bar_height = int(self.window_config.get("title_bar_height", 36))
        if self._custom_title_enabled:
            try:
                # Hide native decorations
                self.root.overrideredirect(True)
            except Exception:
                self._custom_title_enabled = False

        # Build title bar if enabled
        self._title_bar_frame: Optional[tk.Frame] = None
        if self._custom_title_enabled:
            self._build_custom_title_bar()
        else:
            # Try native dark title bar as a best-effort fallback
            self.root.after(10, lambda: enable_dark_title_bar(
                self.root,
                caption_color=self.palette["background"],
                text_color=self.palette["text_primary"],
            ))

        self.main_tabs_config = self.config["main_tabs"]

        # Track Ctrl key state for modifier-sensitive actions
        self._ctrl_down = False
        self._hover_footer_idx: Optional[int] = None
        self.root.bind_all("<KeyPress-Control_L>", self._on_ctrl_press)
        self.root.bind_all("<KeyRelease-Control_L>", self._on_ctrl_release)
        self.root.bind_all("<KeyPress-Control_R>", self._on_ctrl_press)
        self.root.bind_all("<KeyRelease-Control_R>", self._on_ctrl_release)

        self.selected_main_idx = 0
        self.selected_sub_idx = 0

        self.main_tab_buttons: List[Optional[tk.Button]] = []
        self.sub_tab_buttons: List[Optional[tk.Button]] = []
        self.footer_buttons: List[Optional[tk.Button]] = []
   
        self._missing_actions: set[str] = set()
        self._current_content_widget: Optional[tk.Widget] = None
        # Cache for preloaded sub-tab UIs: key = (main_idx, sub_idx) -> container Frame
        self._sub_ui_cache: Dict[tuple[int, int], tk.Frame] = {}

        self._build_layout()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._select_first_available_tab()

        # Start live sync manager immediately; it is idle if not installed
        self._live_sync = LiveSyncManager()
        self._live_sync.start(self.root)
        # Force an immediate pre-game sync so Difficulties files are up to date
        try:
            # Perform an unconditional one-time sync at startup
            self._live_sync.force_sync_now()
        except Exception:
            pass

    def _is_live_mod_installed(self) -> bool:
        try:
            base = os.environ.get("LOCALAPPDATA")
            if base:
                root = Path(base)
            else:
                root = Path.home() / "AppData" / "Local"
            return (root / "ReadyOrNot" / "Saved" / "Config" / "Difficulties").exists()
        except Exception:
            return False

    def _should_hide_live_mod_subs(self, main_idx: int) -> bool:
        try:
            main_tab = self.main_tabs_config[main_idx]
            is_live_mod = str(main_tab.get("title", "")).strip().lower() == "live mod"
            return is_live_mod and not self._is_live_mod_installed()
        except Exception:
            return False

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        top_row = 1 if self._custom_title_enabled else 0
        content_row = (top_row + 2) if self._custom_title_enabled else 2
        self.root.grid_rowconfigure(content_row, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        # Determine base row index offset when custom title bar is present
        base = 1 if self._custom_title_enabled else 0

        self.main_tab_frame = tk.Frame(self.root, bg=self.palette["background"])
        self.main_tab_frame.grid(row=base + 0, column=0, sticky="ew")

        self.sub_tab_frame = tk.Frame(self.root, bg=self.palette["background"])
        self.sub_tab_frame.grid(row=base + 1, column=0, sticky="ew")

        self.content_frame = tk.Frame(
            self.root,
            bg=self.palette["content_bg"],
            borderwidth=0,
            highlightthickness=0,
        )
        self.content_frame.grid(row=base + 2, column=0, sticky="nsew")

        self.footer_frame = tk.Frame(self.root, bg=self.palette["background"])
        self.footer_frame.grid(row=base + 3, column=0, sticky="ew")

        self._build_main_tabs()
        self._build_footer_buttons(self.selected_main_idx)

    def _build_main_tabs(self) -> None:
        for col in range(7):
            self.main_tab_frame.grid_columnconfigure(col, weight=1, uniform="main_tabs")
        self.main_tab_frame.grid_rowconfigure(0, weight=1)

        self.main_tab_buttons.clear()
        for idx, tab_cfg in enumerate(self.main_tabs_config):
            container = tk.Frame(self.main_tab_frame, bg=self.palette["background"], borderwidth=0)
            container.grid(row=0, column=idx, sticky="nsew", padx=1, pady=1)
            if tab_cfg.get("enabled", False):
                btn = tk.Button(
                    container,
               
                    text=tab_cfg.get("title", f"Tab {idx + 1}"),
                    bg=self.palette["main_tab_bg"],
                    fg=self.palette["main_tab_fg"],
                    activebackground=adjust_color(self.palette["main_tab_bg"], 1.1),
                    activeforeground=self.palette["text_primary"],
          
                    borderwidth=0,
                    highlightthickness=0,
                    relief="flat",
                    font=("Segoe UI", 11, "bold"),
                    command=lambda i=idx: self._on_main_tab_click(i),
     
                )
                btn.pack(fill="both", expand=True)
                self._set_button_style(
                    btn,
                    tab_cfg.get("style", "orange"),
               
                    self.palette["main_tab_bg"],
                    self.palette["main_tab_fg"],
                )
                self.main_tab_buttons.append(btn)
            else:
                placeholder = tk.Frame(container, bg=self.palette["background"])
            
                placeholder.pack(fill="both", expand=True)
                self.main_tab_buttons.append(None)

    def _build_sub_tabs(self, main_idx: int) -> None:
        for child in self.sub_tab_frame.winfo_children():
            child.destroy()
        for col in range(7):
            self.sub_tab_frame.grid_columnconfigure(col, weight=1, uniform="sub_tabs")
        self.sub_tab_frame.grid_rowconfigure(0, weight=1)

        self.sub_tab_buttons = []
   
        main_tab = self.main_tabs_config[main_idx]
        live_mod_tab = str(main_tab.get("title", "")).strip().lower() == "live mod"
        hide_subs = self._should_hide_live_mod_subs(main_idx)

        for idx, sub_cfg in enumerate(main_tab.get("sub_tabs", [])):
            container = tk.Frame(self.sub_tab_frame, bg=self.palette["background"], borderwidth=0)
            container.grid(row=0, column=idx, sticky="nsew", padx=1, pady=1)
            if sub_cfg.get("enabled", False) and not hide_subs:
                btn = tk.Button(
                
                    container,
                    text=sub_cfg.get("title", f"Sub {idx + 1}"),
                    bg=self.palette["sub_tab_bg"],
                    fg=self.palette["sub_tab_fg"],
                    activebackground=adjust_color(self.palette["sub_tab_bg"], 1.1),
           
                    activeforeground=self.palette["text_primary"],
                    borderwidth=0,
                    highlightthickness=0,
                    relief="flat",
                    font=("Segoe UI", 10),
         
                    command=lambda i=idx: self._on_sub_tab_click(main_idx, i, trigger_action=True),
                )
                btn.pack(fill="both", expand=True)
                self._set_button_style(
                    btn,
                
                    sub_cfg.get("style", "gray"),
                    self.palette["sub_tab_bg"],
                    self.palette["sub_tab_fg"],
                )
                self.sub_tab_buttons.append(btn)
                self._apply_sub_action_state(main_idx, idx)
            
            else:
                placeholder = tk.Frame(container, bg=self.palette["background"], borderwidth=0, highlightthickness=0)
                placeholder.pack(fill="both", expand=True)
                self.sub_tab_buttons.append(None)

        if hide_subs:
            self._clear_content_frame()

    def _build_footer_buttons(self, main_idx: Optional[int] = None) -> None:
        if main_idx is None:
            main_idx = self.selected_main_idx
      
        for col in range(6):
            self.footer_frame.grid_columnconfigure(col, weight=1, uniform="footer")
        self.footer_frame.grid_rowconfigure(0, weight=1)
        for child in self.footer_frame.winfo_children():
            child.destroy()

        self.footer_buttons = []
        footer_list = self._footer_list(main_idx)
        for idx, footer_cfg in enumerate(footer_list[:6]):
            container = tk.Frame(self.footer_frame, bg=self.palette["background"], borderwidth=0)
 
            container.grid(row=0, column=idx, sticky="nsew", padx=1, pady=6)
            if footer_cfg.get("enabled", False):
                btn = tk.Button(
                    container,
                    text=footer_cfg.get("title", f"Footer {idx + 1}"),
         
                    bg=self.palette["footer_bg"],
                    fg=self.palette["footer_fg"],
                    activebackground=adjust_color(self.palette["footer_bg"], 1.1),
                    activeforeground=self.palette["text_primary"],
                    borderwidth=0,
        
                    highlightthickness=0,
                    relief="flat",
                    font=("Segoe UI", 10, "bold"),
                    command=lambda i=idx: self._on_footer_click(i),
                )
       
                btn.pack(fill="both", expand=True)
                self._set_button_style(
                    btn,
                    footer_cfg.get("style", "blue"),
                    self.palette["footer_bg"],
             
                    self.palette["footer_fg"],
                )
                # Hover tracking for footer button
                btn.bind('<Enter>', lambda e, i=idx: self._on_footer_hover(i, True))
                btn.bind('<Leave>', lambda e, i=idx: self._on_footer_hover(i, False))
                self.footer_buttons.append(btn)
                self._apply_footer_action_state(idx, main_idx=main_idx)
            else:
                placeholder = tk.Frame(container, bg=self.palette["background"])
             
                placeholder.pack(fill="both", expand=True)
                self.footer_buttons.append(None)


    def _on_main_tab_click(self, main_idx: int) -> None:
        if not self.main_tabs_config[main_idx].get("enabled", False):
            return
        self.selected_main_idx = main_idx
        self.selected_sub_idx = 0
        self._highlight_main_tabs()
        self._build_sub_tabs(main_idx)
        self._build_footer_buttons(main_idx)
    
        self._select_first_available_sub(main_idx, trigger_action=False)

    def _clear_content_frame(self) -> None:
        # Hide all cached sub containers if present; destroy non-cached widgets
        cached = set(self._sub_ui_cache.values())
        for widget in list(self.content_frame.winfo_children()):
            if widget in cached:
                widget.place_forget()
                widget.pack_forget()
                widget.grid_forget()
                widget.lower()
            else:
                widget.destroy()
        self._current_content_widget = None

    def _hide_all_sub_containers(self) -> None:
        for frame in self._sub_ui_cache.values():
            try:
                frame.place_forget()
                frame.pack_forget()
                frame.grid_forget()
                frame.lower()
            except Exception:
                pass

    def _show_sub_container(self, main_idx: int, sub_idx: int) -> None:
        container = self._sub_ui_cache.get((main_idx, sub_idx))
        if not container:
            return
        self._hide_all_sub_containers()
        container.pack(fill="both", expand=True)
        container.lift()
        self._current_content_widget = container

    def _on_sub_tab_click(self, main_idx: int, sub_idx: int, *, trigger_action: bool = True) -> None:
        if self._should_hide_live_mod_subs(main_idx):
            self._clear_content_frame()
            return
        sub_cfg = self.main_tabs_config[main_idx]["sub_tabs"][sub_idx]
        self.selected_main_idx = main_idx
        self.selected_sub_idx = sub_idx
        self._highlight_main_tabs()
        self._highlight_sub_tabs()
        # Do not destroy cached content; hide others instead
        self._hide_all_sub_containers()

        # Dynamische Integration von UI-Komponenten, falls in der Konfiguration definiert
        if sub_cfg.get("integration_type") == "direct_ui":
            module_path = sub_cfg.get("module_path")
            class_name = sub_cfg.get("class_name")
            if module_path and class_name:
                try:
                    key = (main_idx, sub_idx)
                    container = self._sub_ui_cache.get(key)
                    if not container:
                        # This instance will be created fresh
                        instance = None
                        container = tk.Frame(self.content_frame, bg=self.palette["content_bg"], borderwidth=0, highlightthickness=0)
                        container.pack_forget()
                        module = importlib.import_module(module_path) # e.g., mission_settings_tab
                        
                        if hasattr(module, "create_app"):
                            # Use the factory function, which correctly handles imports
                            instance = module.create_app(container, main_app=self)
                        else:
                            # Fallback for older components without a factory
                            ui_class = getattr(module, class_name)
                            instance = ui_class(container)

                        self._sub_ui_cache[key] = container
                    else:
                        # Load instance from the cached container
                        instance = getattr(container, '_ui_instance', None)
                    setattr(container, '_ui_instance', instance)
                    # Ensure live sync is started whenever a direct_ui editor is shown
                    self._ensure_live_sync_started()
                    self._show_sub_container(main_idx, sub_idx)
                    return
                except (ImportError, AttributeError) as e:
                    traceback.print_exc()  # Print full error to console
                    messagebox.showerror("Integration Error", f"Could not load UI component '{class_name}' from '{module_path}':\n{e}")
                except Exception as e:
                    traceback.print_exc()
                    messagebox.showerror("UI Error", f"An unexpected error occurred while loading the tab '{class_name}':\n{e}")
            return

        action_id = sub_cfg.get("action_id")
        if action_id and not trigger_action:
            return

        if action_id:
            button = self.sub_tab_buttons[sub_idx]
            if not button:
                return
           
            context = self._build_sub_action_context(main_idx, sub_idx)
            try:
                result = run_action(action_id, context)
            except ActionNotFound:
                self._handle_action_missing(action_id)
                return
            except ActionExecutionError as exc:
     
                messagebox.showerror("StrategoAI", str(exc))
                return
            # Aktionen können jetzt direkt Widgets im content_frame erstellen
            # oder Nachrichten über ein Label anzeigen, das wir hier verwalten.
          
            self._apply_button_state(
                button,
                result,
                sub_cfg.get("title", f"Sub {sub_idx + 1}"),
                sub_cfg.get("style", "gray"),
                fallback_bg=self.palette["sub_tab_bg"],
             
                fallback_fg=self.palette["sub_tab_fg"],
                highlight_scope="sub",
            )
            return
        # Fallback für andere externe Programme (falls noch benötigt)

    def _on_footer_click(self, footer_idx: int) -> None:
        main_idx = self.selected_main_idx
        footer_list = self._footer_list(main_idx)
        if footer_idx >= len(footer_list) or footer_idx >= len(self.footer_buttons):
         
            return
        footer_cfg = footer_list[footer_idx]
        if not footer_cfg.get("enabled", False):
            return
        button = self.footer_buttons[footer_idx]
        if not button:
            return

        action_id = footer_cfg.get("action_id")
        if action_id:
            context = self._build_footer_action_context(footer_idx, main_idx)
            try:
                result = run_action(action_id, context)
            except ActionNotFound:
                self._handle_action_missing(action_id)
                return
          
            except ActionExecutionError as exc:
                messagebox.showerror("StrategoAI", str(exc))
                return
            if result:
                self._apply_button_state(
                    button,
                    result,
                    footer_cfg.get("title", f"Footer {footer_idx + 1}"),
                    footer_cfg.get("style", "blue"),
                    fallback_bg=self.palette["footer_bg"],
                    fallback_fg=self.palette["footer_fg"],
                )
            # After any footer action, refresh state of all footer buttons
            # Reset ctrl to avoid latched modifier state after dialogs
            self._ctrl_down = False
            
            # Check if uninstall was actually completed (not cancelled)
            uninstall_completed = False
            if action_id == "uninstall_live_mod" and result and result.message:
                if "entfernt" in result.message.lower():
                    uninstall_completed = True
            
            try:
                total = min(6, len(self._footer_list(main_idx)))
                for idx in range(total):
                    self._apply_footer_action_state(idx, main_idx=main_idx)
                # Only rebuild sub tabs when install/uninstall state actually changes
                # This prevents hiding the GMS window when canceling uninstall
                needs_rebuild = (action_id == "install_live_mod" or 
                                uninstall_completed or 
                                action_id == "toggle_live_mod_activation")
                if needs_rebuild:
                    # Rebuild sub tabs for current main to reflect visibility
                    self._build_sub_tabs(main_idx)
                    self._highlight_sub_tabs()
                    if not self._should_hide_live_mod_subs(main_idx):
                        self._select_first_available_sub(main_idx, trigger_action=True)
                # If Live Mod was just installed, switch to Live Mod main tab and show its first sub immediately
                if action_id == "install_live_mod":
                    live_idx = None
                    for i, tab in enumerate(self.main_tabs_config):
                        if str(tab.get("title", "")).strip().lower() == "live mod":
                            live_idx = i
                            break
                    if live_idx is not None:
                        self.selected_main_idx = live_idx
                        self._highlight_main_tabs()
                        self._build_sub_tabs(live_idx)
                        self._build_footer_buttons(live_idx)
                        if not self._should_hide_live_mod_subs(live_idx):
                            self._select_first_available_sub(live_idx, trigger_action=True)
            except Exception:
                # Fallback to at least refresh the clicked one
                self._apply_footer_action_state(footer_idx, main_idx=main_idx)
            # Manage LiveSync lifecycle based on actions
            try:
                if uninstall_completed:
                    # Fully stop LiveSync when mod was actually uninstalled
                    self._live_sync.stop()
                    # Destroy any cached sub UIs to ensure embedded watchers are cancelled
                    try:
                        for frame in list(self._sub_ui_cache.values()):
                            try:
                                # If embedded UIs bind to <Destroy>, this will trigger their cleanup
                                frame.destroy()
                            except Exception:
                                pass
                        self._sub_ui_cache.clear()
                        # Also clear current content frame
                        self._clear_content_frame()
                    except Exception:
                        pass
                elif action_id in ("install_live_mod", "toggle_live_mod_activation"):
                    # Ensure LiveSync is started (idempotent). It will remain idle if files are missing/paused.
                    self._live_sync.start(self.root)
                    self._live_sync.refresh_now()
                else:
                    self._live_sync.refresh_now()
            except Exception:
                pass
            return


    def _highlight_main_tabs(self) -> None:
        for idx, btn in enumerate(self.main_tab_buttons):
            if not btn:
     
                continue
            base_bg = getattr(btn, "_base_bg", self.palette["main_tab_bg"])
            base_fg = getattr(btn, "_base_fg", self.palette["main_tab_fg"])
            if idx == self.selected_main_idx:
                btn.configure(
                    bg=adjust_color(base_bg, 1.2),
     
                    fg=self.palette["text_primary"],
                    activebackground=adjust_color(base_bg, 1.25),
                )
            else:
                btn.configure(
                    
                    bg=base_bg,
                    fg=base_fg,
                    activebackground=adjust_color(base_bg, 1.1),
                )

    def _highlight_sub_tabs(self) -> None:
        for idx, btn in enumerate(self.sub_tab_buttons):
            if not btn:
          
                continue
            base_bg = getattr(btn, "_base_bg", self.palette["sub_tab_bg"])
            base_fg = getattr(btn, "_base_fg", self.palette["sub_tab_fg"])
            if idx == self.selected_sub_idx:
                btn.configure(
                    bg=adjust_color(base_bg, 1.2),
          
                    fg=self.palette["text_primary"],
                    activebackground=adjust_color(base_bg, 1.25),
                )
            else:
                btn.configure(
                    bg=base_bg,
     
                    fg=base_fg,
                    activebackground=adjust_color(base_bg, 1.1),
                )

    def _select_first_available_tab(self) -> None:
        for idx, tab in enumerate(self.main_tabs_config):
            if tab.get("enabled", False):
               
                self.selected_main_idx = idx
                self._highlight_main_tabs()
                self._build_sub_tabs(idx)
                self._build_footer_buttons(idx)
                self._select_first_available_sub(idx, trigger_action=False)
                return
        self._clear_content_frame()

    
    def _select_first_available_sub(self, main_idx: int, *, trigger_action: bool) -> None:
        main_tab = self.main_tabs_config[main_idx]
        for idx, sub in enumerate(main_tab.get("sub_tabs", [])):
            if sub.get("enabled", False):
                self.selected_sub_idx = idx
                self._highlight_sub_tabs()
                self._on_sub_tab_click(main_idx, idx, trigger_action=trigger_action)
   
                return
        self._clear_content_frame()

    def _on_close(self) -> None:
        self._clear_content_frame()
        self.root.destroy()

    # ------------------------------ Custom Title Bar ------------------------------
    def _build_custom_title_bar(self) -> None:
        # Top-level frame spanning full width
        bar_bg = "#242852"  # Custom blue-purple color
        bar = tk.Frame(self.root, bg=bar_bg, height=self._title_bar_height, highlightthickness=0, borderwidth=0)
        bar.grid(row=0, column=0, sticky="ew")
        # Ensure row 0 has fixed height
        try:
            self.root.grid_rowconfigure(0, minsize=self._title_bar_height)
        except Exception:
            pass

        # Title label (left)
        title = tk.Label(
            bar, text=self.window_config.get("title", "StrategoAI Live Mod Generator"),
            bg=bar_bg, fg=self.palette["text_primary"],
            font=("Segoe UI", 10, "bold")
        )
        title.pack(side=tk.LEFT, padx=10)

        # Close button (far right, red)
        def _sys_close() -> None:
            self._on_close()

        close_btn = tk.Label(
            bar, text="✕", width=3,
            bg="#b91c1c", fg="#ffffff",  # Red background
            font=("Segoe UI", 12, "bold")
        )
        close_btn.bind("<Button-1>", lambda _e: _sys_close())
        close_btn.bind("<Enter>", lambda _e: close_btn.configure(bg="#991b1b"))  # Darker red on hover
        close_btn.bind("<Leave>", lambda _e: close_btn.configure(bg="#b91c1c"))
        close_btn.pack(side=tk.RIGHT, padx=(0, 4))

        # Minimize button (right, left of close button)
        def _sys_minimize() -> None:
            try:
                # Remove overrideredirect temporarily to allow minimize
                self.root.overrideredirect(False)
                self.root.update_idletasks()
                self.root.iconify()
                # Restore overrideredirect when window is restored
                def _restore_override():
                    try:
                        if self.root.state() == 'normal':
                            self.root.overrideredirect(True)
                            self.root.unbind('<Map>', bind_id)
                    except Exception:
                        pass
                bind_id = self.root.bind('<Map>', lambda e: _restore_override())
            except Exception:
                pass

        minimize_btn = tk.Label(
            bar, text="−", width=3,
            bg=bar_bg, fg=self.palette["text_primary"],
            font=("Segoe UI", 12, "bold")
        )
        minimize_btn.bind("<Button-1>", lambda _e: _sys_minimize())
        minimize_btn.bind("<Enter>", lambda _e: minimize_btn.configure(bg="#2f3460"))  # Slightly lighter on hover
        minimize_btn.bind("<Leave>", lambda _e: minimize_btn.configure(bg=bar_bg))
        minimize_btn.pack(side=tk.RIGHT, padx=(0, 2))

        # Dragging the window by the title area
        def _start_move(event):
            self._drag_start = (event.x_root, event.y_root)
            try:
                self._win_start = (self.root.winfo_x(), self.root.winfo_y())
            except Exception:
                self._win_start = (0, 0)

        def _on_drag(event):
            try:
                dx = event.x_root - self._drag_start[0]
                dy = event.y_root - self._drag_start[1]
                nx = self._win_start[0] + dx
                ny = self._win_start[1] + dy
                self.root.geometry(f"+{nx}+{ny}")
            except Exception:
                pass

        for w in (bar, title):
            w.bind("<ButtonPress-1>", _start_move)
            w.bind("<B1-Motion>", _on_drag)

        self._title_bar_frame = bar

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------
    def _resolve_style_colors(self, style_name: Optional[str], fallback_bg: str, fallback_fg: str) -> tuple[str, str]:
        if style_name:
            style = self.button_styles.get(style_name)
 
            if isinstance(style, dict):
                bg = style.get("bg", fallback_bg)
                fg = style.get("fg", fallback_fg)
                return bg, fg
        return fallback_bg, fallback_fg

    def _set_button_style(
        self,
        
        button: tk.Button,
        style_name: Optional[str],
        fallback_bg: str,
        fallback_fg: str,
    ) -> None:
        bg, fg = self._resolve_style_colors(style_name, fallback_bg, fallback_fg)
        button.configure(
            bg=bg,
            fg=fg,
            activebackground=adjust_color(bg, 1.1),
        
            activeforeground=self.palette["text_primary"],
        )
        button._base_bg = bg  # type: ignore[attr-defined]
        button._base_fg = fg  # type: ignore[attr-defined]
        button._style_name = style_name  # type: ignore[attr-defined]

    def _apply_button_state(
        self,
        button: tk.Button,
        state: Optional[ButtonState],
        default_text: str,
      
        default_style: str,
        *,
        fallback_bg: str,
        fallback_fg: str,
        highlight_scope: Optional[str] = None,
    ) -> None:
        target_text = default_text
        target_style = default_style
        if state:
            if state.text is not None:
         
                target_text = state.text
            if state.style is not None:
                target_style = state.style
            if state.enabled is not None:
                button.configure(state="normal" if state.enabled else "disabled")
        else:
            button.configure(state="normal")
 
        button.configure(text=target_text)
        self._set_button_style(button, target_style, fallback_bg, fallback_fg)
        if highlight_scope == "main":
            self._highlight_main_tabs()
        elif highlight_scope == "sub":
            self._highlight_sub_tabs()

    # ------------------------------------------------------------------
    # Action helpers
    # ------------------------------------------------------------------
    def _footer_list(self, main_idx: int) -> List[Dict[str, Any]]:
        if main_idx < 0 or main_idx >= len(self.main_tabs_config):
            return []
        footers = self.main_tabs_config[main_idx].setdefault("footer_buttons", [])
        while len(footers) < 6:
            footers.append(
                {
                    "id": f"{self.main_tabs_config[main_idx].get('id', 'footer')}_{len(footers) + 1}",
        
                    "title": f"Footer {len(footers) + 1}",
                    "enabled": False,
                    "program_path": "",
                    "program_args": [],
                    "run_with_python": False,
                    "working_dir": "",
                }
            )
        return footers

    def _build_sub_action_context(self, main_idx: int, sub_idx: int) -> Dict[str, Any]:
        return {
            "project_root": self.project_root,
        
            "scope": "sub_tab",
            "main_index": main_idx,
            "sub_index": sub_idx,
            "config_entry": self.main_tabs_config[main_idx]["sub_tabs"][sub_idx],
            "config": self.config,
        }

    def _build_footer_action_context(self, footer_idx: int, main_idx: Optional[int] = None) -> Dict[str, Any]:
        if main_idx is None:
          
            main_idx = self.selected_main_idx
        footer_list = self._footer_list(main_idx)
        config_entry = footer_list[footer_idx] if footer_idx < len(footer_list) else {}
        # include button absolute geometry if available
        btn = self.footer_buttons[footer_idx] if footer_idx < len(self.footer_buttons) else None
        bx = by = bw = bh = 0
        if btn is not None:
            try:
                btn.update_idletasks()
                bx = btn.winfo_rootx()
                by = btn.winfo_rooty()
                bw = btn.winfo_width()
                bh = btn.winfo_height()
            except Exception:
                pass
        return {
            "project_root": self.project_root,
            "scope": "footer",
            "main_index": main_idx,
            "footer_index": footer_idx,
            "ctrl": self._ctrl_down,
            "hover": (self._hover_footer_idx == footer_idx),
            "button_abs_x": bx,
            "button_abs_y": by,
            "button_width": bw,
            "button_height": bh,
            
            "config_entry": config_entry,
            "config": self.config,
        }

    def _on_ctrl_press(self, _event: tk.Event) -> None:
        self._ctrl_down = True
        if self._hover_footer_idx is not None:
            self._apply_footer_action_state(self._hover_footer_idx, main_idx=self.selected_main_idx)

    def _on_ctrl_release(self, _event: tk.Event) -> None:
        self._ctrl_down = False
        if self._hover_footer_idx is not None:
            self._apply_footer_action_state(self._hover_footer_idx, main_idx=self.selected_main_idx)

    def _on_footer_hover(self, idx: int, is_hover: bool) -> None:
        self._hover_footer_idx = idx if is_hover else None
        self._apply_footer_action_state(idx, main_idx=self.selected_main_idx)

    # Live sync helpers
    def _ensure_live_sync_started(self) -> None:
        try:
            if hasattr(self, "_live_sync") and self._live_sync and getattr(self._live_sync, "_root", None):
                return
            # Start when any editor UI (direct_ui) is opened
            self._live_sync.start(self.root)
        except Exception:
            pass


    def _apply_sub_action_state(self, main_idx: int, sub_idx: int) -> None:
        sub_cfg = self.main_tabs_config[main_idx]["sub_tabs"][sub_idx]
        action_id = sub_cfg.get("action_id")
        button = self.sub_tab_buttons[sub_idx]
        if not action_id or not button:
            return
        try:
 
            state = resolve_action_state(action_id, self._build_sub_action_context(main_idx, sub_idx))
        except ActionNotFound:
            self._handle_action_missing(action_id)
            return
        if state:
            self._apply_button_state(
                button,
               
                state,
                sub_cfg.get("title", f"Sub {sub_idx + 1}"),
                sub_cfg.get("style", "gray"),
                fallback_bg=self.palette["sub_tab_bg"],
                fallback_fg=self.palette["sub_tab_fg"],
            )

    def _apply_footer_action_state(self, footer_idx: int, *, main_idx: Optional[int] = None) -> None:
    
        if main_idx is None:
            main_idx = self.selected_main_idx
        footer_list = self._footer_list(main_idx)
        if footer_idx >= len(footer_list) or footer_idx >= len(self.footer_buttons):
            return
        footer_cfg = footer_list[footer_idx]
        button = self.footer_buttons[footer_idx]
        action_id = footer_cfg.get("action_id")
        if not action_id or not button:
            return
        try:
            state = resolve_action_state(action_id, self._build_footer_action_context(footer_idx, main_idx))
        except ActionNotFound:
            self._handle_action_missing(action_id)
            return
        if state:
            self._apply_button_state(
         
                button,
                state,
                footer_cfg.get("title", f"Footer {footer_idx + 1}"),
                footer_cfg.get("style", "blue"),
                fallback_bg=self.palette["footer_bg"],
                fallback_fg=self.palette["footer_fg"],
        
            )

    def _handle_action_missing(self, action_id: str) -> None:
        if action_id in self._missing_actions:
            return
        self._missing_actions.add(action_id)
    
        messagebox.showwarning(
            "StrategoAI",
            f"Die Aktion '{action_id}' ist in main_actions.py nicht registriert.",
        )

    def refresh_all_live_mod_tabs(self) -> None:
        """Calls the 'refresh_data' method on all active Live Mod sub-tab UIs."""
        live_mod_main_tab_idx = -1
        for i, tab in enumerate(self.main_tabs_config):
            if str(tab.get("title", "")).strip().lower() == "live mod":
                live_mod_main_tab_idx = i
                break
        
        if live_mod_main_tab_idx == -1:
            return

        for (main_idx, sub_idx), container in self._sub_ui_cache.items():
            if main_idx == live_mod_main_tab_idx and hasattr(container, '_ui_instance'):
                instance = getattr(container, '_ui_instance', None)
                if instance and hasattr(instance, 'refresh_data'):
                    instance.refresh_data()

__all__ = ["StrategoAILiveGeneratorApp"]
