"""Base class for 3-column card-based GUIs like Mission and Optional Settings."""

from __future__ import annotations
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import re

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

from system.programs.Live_Mod.Global_Mission_Settings.config_gms.gms_actions import (
    get_available_templates,
    alternative_ini_editor_action,
    _work_ini_path,
)
try:
    from system.config_main.main_actions import get_application_base_path
    from system.gui_utils import event_bus as _event_bus  # type: ignore
except Exception:
    _event_bus = None  # type: ignore
from system.gui_utils.unified_dialogs import show_error

# Sticky shared page index so newly opened sibling tabs can align immediately
_LAST_CARD_PAGE: int = 0
from ..config_ms.actions_ms import (
    MissionDef,
    write_mission_parameter,
)
from typing import Dict as _DictAlias  # for type hints inside methods

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


def _normalize_section_key(name: str) -> str:
    s = name.strip()
    try:
        if "_" in s and s.split("_", 1)[0].isdigit():
            s = s.split("_", 1)[1]
    except Exception:
        pass
    return s.lower()


def _build_pic_map(pic_dir: Path) -> Dict[str, Path]:
    """Build map from normalized section key to image path."""
    pic_map: Dict[str, Path] = {}
    if not pic_dir.exists():
        return pic_map
    try:
        for pic in pic_dir.iterdir():
            if not pic.is_file() or pic.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp"}:
                continue
            key = _normalize_section_key(pic.stem)
            pic_map[key] = pic
    except Exception:
        pass
    return pic_map


class BaseCardGUI:
    """Base class for Mission/Optional Settings GUIs."""

    def __init__(self, parent: tk.Widget | None = None, *, extract_missions_func, template_ini_path, pics_dir_path) -> None:
        self.root = parent if parent is not None else tk.Tk()

        self.extract_missions_func = extract_missions_func
        self.template_ini_path = template_ini_path

        self.palette = {
            "background": "#2a2d33", "panel_dark": "#2a2d33", "panel_light": "#353941",
            "entry_bg": "#3c414b", "entry_fg": "#f5f5f5", "text_primary": "#f8fafc",
            "text_muted": "#d1d5db", "button_green": "#15803d", "button_orange": "#f97316",
            "button_gray": "#4b5563", "button_text": "#f8fafc",
        }

        self.fonts: dict[str, tkfont.Font] = {}
        self._init_fonts()

        self.style = ttk.Style()
        self._configure_styles()

        self.missions: List[MissionDef] = self.extract_missions_func(self.template_ini_path)
        self.pic_map: Dict[str, Path] = _build_pic_map(pics_dir_path)

        self.page_index = 0
        self.cols_per_page = 3
        self.pages = 9

        self.card_widgets: Dict[str, Dict[str, tk.Entry]] = {}
        # Remember last selected template per mission so the dropdown keeps selection
        self._last_template_choice: Dict[str, str] = {}
        
        # Marquee state for individual parameter labels
        self._param_marquee_job: str | None = None
        self._param_marquee_widget: tk.Label | None = None
        self._param_marquee_text: str = ""
        self._param_marquee_index: int = 0
        self._param_marquee_window_chars: int = 28

        # Marquee state for single-line helptext
        self.helptext_label: tk.Label | None = None
        self.helptext_original = ""
        self.helptext_index = 0
        self.marquee_job: str | None = None
        self.marquee_window = 80  # characters visible
        self.marquee_delay_ms = 100  # smooth scrolling speed
        self.marquee_spacing = "   "  # spacing before wrap
        self.marquee_pause_ms = 3000  # pause at end before restart

        # Load help texts from E_StrategoAI_Help.ini
        self.help_texts: Dict[str, str] = {}
        try:
            self._load_help_texts()
        except Exception:
            pass

        self._build_layout()

        # Sync paging across sibling tabs (Mission/Optional Settings)
        self._sync_id = f"{self.__class__.__name__}:{id(self)}"
        self._suppress_broadcast = False
        try:
            if _event_bus is not None:
                _event_bus.subscribe("card_page_changed", self._on_external_page_change)
                # Adopt last known shared page on first build to sync immediately
                global _LAST_CARD_PAGE
                target = max(0, min(_LAST_CARD_PAGE, max(0, self.pages - 1)))
                if target != self.page_index:
                    self._suppress_broadcast = True
                    self.page_index = target
                    self._render_page()
                    self._suppress_broadcast = False
                # Broadcast our current page (now aligned) for others
                self.root.after(0, self._broadcast_page)
        except Exception:
            pass

        # Keyboard shortcuts: Left/Right to change pages (non-intrusive)
        try:
            self._bind_keyboard_shortcuts()
        except Exception:
            pass

        # Live watch: refresh when work.ini changes externally (fallback to polling if no event bus)
        self._watch_job: str | None = None
        self._last_work_mtime: float | None = None
        try:
            if _event_bus is None:
                self._init_work_watch()
        except Exception:
            # Non-fatal if watcher can't start
            self._watch_job = None

        # Subscribe to clean event if available (preferred over polling)
        try:
            if _event_bus is not None:
                _event_bus.subscribe("work_ini_changed", self._on_work_ini_changed)
                _event_bus.subscribe("work_ini_reset", self._on_work_ini_reset)
                # Debounce handle
                self._refresh_job: str | None = None
        except Exception:
            pass

        try:
            self.root.bind("<Destroy>", self._on_destroy, add=True)
        except Exception:
            pass

        # Start helptext marquee
        self._update_helptext("Hover over mission cards to see parameter information")
        self._start_marquee()

    def _on_work_ini_changed(self) -> None:
        # Debounce and perform value-only refresh to avoid flicker
        try:
            if getattr(self, "_refresh_job", None) is not None:
                return
            def _do_refresh():
                setattr(self, "_refresh_job", None)
                try:
                    self._refresh_values_only()
                except Exception:
                    try:
                        self.refresh_data()
                    except Exception:
                        pass
            self._refresh_job = self.root.after(120, _do_refresh)
        except Exception:
            try:
                self._refresh_values_only()
            except Exception:
                try:
                    self.refresh_data()
                except Exception:
                    pass

    def _on_work_ini_reset(self) -> None:
        # On full reset (clean all), rebuild structure to avoid transient blanks
        try:
            # Cancel any pending values-only refresh
            if getattr(self, "_refresh_job", None) is not None:
                try:
                    self.root.after_cancel(self._refresh_job)
                except Exception:
                    pass
                self._refresh_job = None
            # Debounce a full rebuild slightly to coalesce any follow-up writes
            def _do_full_refresh():
                try:
                    self.refresh_data()
                except Exception:
                    pass
            self.root.after(100, _do_full_refresh)
        except Exception:
            try:
                self.refresh_data()
            except Exception:
                pass

    def _init_work_watch(self) -> None:
        try:
            p = _work_ini_path()
            if p.exists():
                self._last_work_mtime = p.stat().st_mtime
            else:
                self._last_work_mtime = None
        except Exception:
            self._last_work_mtime = None
        self._schedule_watch(1000)

    def _schedule_watch(self, delay_ms: int) -> None:
        try:
            if self._watch_job is not None:
                self.root.after_cancel(self._watch_job)
        except Exception:
            pass
        try:
            self._watch_job = self.root.after(delay_ms, self._watch_work_ini)
        except Exception:
            self._watch_job = None

    def _watch_work_ini(self) -> None:
        # Poll mtime; refresh data if changed
        delay = 1000
        try:
            p = _work_ini_path()
            exists = p.exists()
            mtime = p.stat().st_mtime if exists else None
            if mtime != self._last_work_mtime:
                # Update and refresh view
                self._last_work_mtime = mtime
                try:
                    self._refresh_values_only()
                except Exception:
                    try:
                        self.refresh_data()
                    except Exception:
                        pass
            # If file missing, back off a bit
            delay = 3000 if not exists else 1000
        except Exception:
            delay = 3000
        finally:
            self._schedule_watch(delay)

    def _read_work_values(self) -> _DictAlias[str, _DictAlias[str, str]]:
        values: _DictAlias[str, _DictAlias[str, str]] = {}
        try:
            p = _work_ini_path()
            text = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
        except Exception:
            text = ""
        current_section = ""
        for line in text.splitlines():
            s = line.strip()
            if s.startswith('[') and s.endswith(']'):
                current_section = s[1:-1]
                if current_section not in values:
                    values[current_section] = {}
                continue
            if not current_section or not s or s.startswith(('#', ';')) or '=' not in s:
                continue
            try:
                k, v = s.split('=', 1)
                values[current_section][k.strip()] = v.split(';', 1)[0].split('#', 1)[0].strip()
            except Exception:
                pass
        return values

    def _refresh_values_only(self) -> None:
        work_vals = self._read_work_values()
        for section, widgets in self.card_widgets.items():
            section_values = work_vals.get(section, {})
            for key, entry in widgets.items():
                # Accept tk.Entry or ttk.Entry; fallback to duck-typing
                is_entry = isinstance(entry, tk.Entry)
                try:
                    from tkinter import ttk as _ttk
                    is_entry = is_entry or isinstance(entry, _ttk.Entry)  # type: ignore
                except Exception:
                    pass
                if not is_entry and not (hasattr(entry, 'get') and hasattr(entry, 'delete') and hasattr(entry, 'insert')):
                    continue
                try:
                    new_val = section_values.get(key, entry.get())
                    if entry.get() != new_val:
                        state = None
                        try:
                            state = entry.cget('state')
                        except Exception:
                            state = None
                        try:
                            if state == 'readonly':
                                entry.config(state='normal')
                            entry.delete(0, tk.END)
                            entry.insert(0, new_val)
                        finally:
                            if state == 'readonly':
                                entry.config(state='readonly', readonlybackground=self.palette["entry_bg"], fg=self.palette["entry_fg"])  # type: ignore
                except Exception:
                    pass

    def _on_destroy(self, _event=None) -> None:
        # Stop marquee
        self._stop_marquee()
        try:
            if self._watch_job is not None:
                self.root.after_cancel(self._watch_job)
                self._watch_job = None
        except Exception:
            pass
        try:
            if _event_bus is not None:
                _event_bus.unsubscribe("work_ini_changed", self._on_work_ini_changed)
                _event_bus.unsubscribe("work_ini_reset", self._on_work_ini_reset)
        except Exception:
            pass
        try:
            if getattr(self, "_refresh_job", None) is not None:
                self.root.after_cancel(self._refresh_job)
                self._refresh_job = None
        except Exception:
            pass

    def refresh_data(self) -> None:
        """Reloads mission data from the INI and refreshes the view."""
        # Reload missions from work.ini to get fresh parameter values
        self.missions = self.extract_missions_func(self.template_ini_path)
        # Re-render current page with updated mission data
        self._render_page()

    def _init_fonts(self) -> None:
        self.fonts["title"] = self._create_font(("Arial Narrow", 13, "bold"), ("Segoe UI", 13, "bold"))
        self.fonts["label"] = self._create_font(("Arial Narrow", 12, "bold"), ("Segoe UI", 12, "bold"))
        self.fonts["entry"] = self._create_font(("Arial Narrow", 11, "bold"), ("Arial", 11, "bold"))
        self.fonts["button"] = self._create_font(("Roboto", 11, "bold"), ("Bahnschrift", 11, "bold"), ("Segoe UI", 11, "bold"))
        self.fonts["helptext"] = self._create_font(("Arial Narrow", 11, "normal"), ("Segoe UI", 11, "normal"))

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

    def _configure_styles(self) -> None:
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("MS.TFrame", background=self.palette["background"])
        self.style.configure("MS.Card.TFrame", background=self.palette["panel_light"])
        self.style.configure("MS.TLabel", background=self.palette["panel_light"], foreground=self.palette["text_primary"], font=self.fonts["label"])
        entry_style = {
            "fieldbackground": self.palette["entry_bg"], "foreground": self.palette["entry_fg"],
            "insertcolor": self.palette["entry_fg"], "bordercolor": self.palette["entry_bg"],
            "lightcolor": self.palette["entry_bg"], "darkcolor": self.palette["entry_bg"],
            "relief": tk.FLAT, "borderwidth": 0, "font": self.fonts["entry"],
        }
        self.style.configure("MS.TEntry", **entry_style)
        self.style.configure("MS.TCombobox", **entry_style, arrowcolor=self.palette["text_primary"])
        self.style.map("MS.TCombobox", fieldbackground=[("readonly", self.palette["entry_bg"])], foreground=[("readonly", self.palette["entry_fg"])])

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, style="MS.TFrame")
        container.pack(fill="both", expand=True, padx=0, pady=0)
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(container, style="MS.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        editor_btn = tk.Button(
            header, text="Alternative ini editor", bg=self.palette["button_green"], fg=self.palette["button_text"],
            activebackground="#0f5c2a", activeforeground=self.palette["button_text"], relief=tk.FLAT,
            borderwidth=0, font=self.fonts["button"], command=lambda: alternative_ini_editor_action(None),
        )
        editor_btn.pack(side=tk.LEFT, padx=(0, 8))

        # Helptext marquee in the middle
        helptext_container = tk.Frame(header, bg=self.palette["entry_bg"], height=32)
        helptext_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        helptext_container.pack_propagate(False)  # CRITICAL: Keep fixed height

        self.helptext_label = tk.Label(
            helptext_container, text="", bg=self.palette["entry_bg"], fg=self.palette["text_muted"],
            font=self.fonts["helptext"], anchor="w", padx=8
        )
        self.helptext_label.pack(fill=tk.BOTH, expand=True)

        # Pagination buttons on the right
        pagination_frame = tk.Frame(header, bg=self.palette["background"])
        pagination_frame.pack(side=tk.RIGHT)

        self.prev_btn = tk.Button(
            pagination_frame, text="◀ Prev", bg=self.palette["button_orange"], fg=self.palette["button_text"],
            activebackground="#c2410c", activeforeground=self.palette["button_text"], relief=tk.FLAT,
            borderwidth=0, font=self.fonts["button"], command=self._prev_page,
        )
        self.prev_btn.pack(side=tk.LEFT)

        self.page_label = tk.Label(pagination_frame, text="", bg=self.palette["background"], fg=self.palette["text_primary"], font=self.fonts["button"])
        self.page_label.pack(side=tk.LEFT, padx=8)

        self.next_btn = tk.Button(
            pagination_frame, text="Next ▶", bg=self.palette["button_orange"], fg=self.palette["button_text"],
            activebackground="#c2410c", activeforeground=self.palette["button_text"], relief=tk.FLAT,
            borderwidth=0, font=self.fonts["button"], command=self._next_page,
        )
        self.next_btn.pack(side=tk.LEFT)

        # Cards frame
        self.cards_frame = ttk.Frame(container, style="MS.TFrame")
        self.cards_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=(8, 0))
        container.grid_rowconfigure(1, weight=1)
        self.cards_frame.grid_rowconfigure(0, weight=1)
        for c in range(self.cols_per_page):
            self.cards_frame.grid_columnconfigure(c, weight=1, uniform="col")

        self._render_page()

    # ------------------------------------------------------------------
    # Marquee helptext animation
    # ------------------------------------------------------------------
    def _load_help_texts(self) -> None:
        """Load help texts from system/Help/E_StrategoAI_Help.ini."""
        try:            
            app_base = get_application_base_path()
            if not app_base:
                return
            help_path = app_base / 'system' / 'Help' / 'E_StrategoAI_Help.ini'
            if not help_path.exists():
                return
            
            text = help_path.read_text(encoding='utf-8', errors='ignore')
            lines = text.splitlines()
            current_key = None
            buf = []
            
            def flush():
                nonlocal current_key, buf
                if current_key is None:
                    buf = []
                    return
                content_lines = []
                for ln in buf:
                    if ln.strip() == '---':
                        continue
                    content_lines.append(ln.lstrip('\t'))
                content = "\n".join(content_lines).strip()
                if content:
                    self.help_texts[current_key] = content
                buf = []
            
            for ln in lines:
                st = ln.strip()
                if st.startswith('[') and st.endswith(']') and len(st) > 2:
                    flush()
                    current_key = st[1:-1].strip()
                    continue
                buf.append(ln)
            flush()
        except Exception:
            pass

    def _get_help_for_key(self, key: str) -> str:
        """Get help text for a parameter key."""
        # Try exact match first
        if key in self.help_texts:
            return self.help_texts[key]
        # Try case-insensitive match
        lower_map = {k.lower(): v for k, v in self.help_texts.items()}
        if key.lower() in lower_map:
            return lower_map[key.lower()]
        # Try without spaces
        key_nospace = key.replace(' ', '')
        if key_nospace in self.help_texts:
            return self.help_texts[key_nospace]
        if key_nospace.lower() in lower_map:
            return lower_map[key_nospace.lower()]
        return f"No documentation available for '{key}'."

    def _update_helptext(self, text: str) -> None:
        """Update the helptext and restart marquee if needed."""
        self.helptext_original = text
        self.helptext_index = 0
        if not self.helptext_label:
            return
        
        # Always start marquee for any text
        self._stop_marquee()
        self._start_marquee()

    def _start_marquee(self) -> None:
        """Start marquee animation for helptext."""
        if not self.helptext_label or not self.helptext_original:
            return
        # Always animate, calculate window size dynamically
        self.marquee_job = self.root.after(self.marquee_delay_ms, self._animate_helptext_marquee)

    def _stop_marquee(self) -> None:
        """Stop marquee animation."""
        if self.marquee_job:
            try:
                self.root.after_cancel(self.marquee_job)
            except Exception:
                pass
            self.marquee_job = None

    def _animate_helptext_marquee(self) -> None:
        """Animate helptext marquee - slide left, pause at end, then restart."""
        if not self.helptext_label or not self.helptext_original:
            self.marquee_job = None
            return
        
        text = self.helptext_original
        
        # Calculate dynamic window size based on label width
        try:
            label_width = self.helptext_label.winfo_width()
            if label_width > 16:
                char_width = self.fonts["helptext"].measure("0")
                window = max(10, (label_width - 16) // char_width)
            else:
                window = self.marquee_window
        except Exception:
            window = self.marquee_window
        
        # If text fits, show static
        if len(text) <= window:
            try:
                self.helptext_label.config(text=text)
            except Exception:
                pass
            self.marquee_job = self.root.after(self.marquee_pause_ms, self._animate_helptext_marquee)
            return
        
        # Non-wrapping: slide left until end is visible, pause, then restart
        end_index = max(0, len(text) - window)
        
        if self.helptext_index < end_index:
            # Normal scrolling
            display_text = text[self.helptext_index : self.helptext_index + window]
            try:
                self.helptext_label.config(text=display_text)
            except Exception:
                self.marquee_job = None
                return
            self.helptext_index += 1
            self.marquee_job = self.root.after(self.marquee_delay_ms, self._animate_helptext_marquee)
        elif self.helptext_index == end_index:
            # At end - show final position and pause
            display_text = text[-window:] if window > 0 else text
            try:
                self.helptext_label.config(text=display_text)
            except Exception:
                self.marquee_job = None
                return
            self.helptext_index += 1
            self.marquee_job = self.root.after(self.marquee_pause_ms, self._animate_helptext_marquee)
        else:
            # Pause complete - restart from beginning
            self.helptext_index = 0
            try:
                self.helptext_label.config(text=text[:window])
            except Exception:
                pass
            self.marquee_job = self.root.after(self.marquee_delay_ms, self._animate_helptext_marquee)

    # ------------------------------------------------------------------
    # Page navigation
    # ------------------------------------------------------------------
    def _prev_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._render_page()
            self._broadcast_page()

    def _next_page(self) -> None:
        if self.page_index + 1 < self.pages:
            self.page_index += 1
            self._render_page()
            self._broadcast_page()

    def _render_page(self) -> None:
        self.card_widgets.clear()
        for w in self.cards_frame.winfo_children():
            w.destroy()

        start = self.page_index * self.cols_per_page
        end = min(len(self.missions), start + self.cols_per_page)

        # Safety check: if start is beyond missions list, reset to first page
        if start >= len(self.missions) and len(self.missions) > 0:
            self.page_index = 0
            start = 0
            end = min(len(self.missions), self.cols_per_page)

        self.page_label.config(text=f"Page {self.page_index + 1} / {self.pages}")
        self.prev_btn.config(state=tk.NORMAL if self.page_index > 0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if self.page_index + 1 < self.pages else tk.DISABLED)

        # Build mission cards for this page
        col = 0
        for mission in self.missions[start:end]:
            self._build_mission_card(mission, col)
            col += 1

        # Fill remaining columns with empty placeholder frames
        while col < self.cols_per_page:
            ttk.Frame(self.cards_frame, style="MS.Card.TFrame").grid(row=0, column=col, sticky="nsew", padx=0)
            col += 1

    # ------------------------- Page sync helpers -------------------------
    def _broadcast_page(self) -> None:
        if getattr(self, "_suppress_broadcast", False):
            return
        try:
            if _event_bus is not None:
                # Update sticky state and notify listeners
                global _LAST_CARD_PAGE
                _LAST_CARD_PAGE = self.page_index
                _event_bus.publish("card_page_changed", page=self.page_index, sender=self._sync_id)
        except Exception:
            pass

    def _on_external_page_change(self, *, page: int, sender: str | None = None, **_kwargs) -> None:
        # Ignore self-originated events
        if sender == getattr(self, "_sync_id", None):
            return
        try:
            if not isinstance(page, int):
                return
            target = max(0, min(int(page), max(0, self.pages - 1)))
            if target == self.page_index:
                return
            self._suppress_broadcast = True
            self.page_index = target
            self._render_page()
        except Exception:
            pass
        finally:
            self._suppress_broadcast = False

    # ------------------------- Keyboard shortcuts ------------------------
    def _bind_keyboard_shortcuts(self) -> None:
        # Bind on toplevel so it works regardless of focus, but guard when typing
        tl = self.root.winfo_toplevel()
        tl.bind_all('<Left>', self._on_key_left, add=True)
        tl.bind_all('<Right>', self._on_key_right, add=True)

    def _focused_in_edit_widget(self) -> bool:
        try:
            w = self.root.focus_get()
            if w is None:
                return False
            cls = w.winfo_class().lower()
            # Common editable widgets where arrow keys should not page
            if cls in ('entry', 'text'):
                return True
            # ttk.Entry/Combobox detection via widget class names
            if 'combobox' in cls:
                return True
            return False
        except Exception:
            return False

    def _on_key_left(self, event=None):  # noqa: D401
        if self._focused_in_edit_widget():
            return
        # Check if the event is for the currently visible tab
        if self.root.winfo_viewable():
            self._prev_page()
            return "break"  # Stop event propagation

    def _on_key_right(self, event=None):  # noqa: D401
        if self._focused_in_edit_widget():
            return
        if self.root.winfo_viewable():
            self._next_page()
            return "break"  # Stop event propagation

    def _build_mission_card(self, mission: MissionDef, col: int) -> None:
        card = ttk.Frame(self.cards_frame, style="MS.Card.TFrame")
        card.grid(row=0, column=col, sticky="nsew", padx=0, pady=(0, 6))
        card.grid_rowconfigure(3, weight=1)
        card.grid_columnconfigure(0, weight=1)

        # Bind hover events to card to update helptext
        def on_enter(_e):
            info_text = f"{mission.title}: {len(mission.params)} parameters - Edit values below or grab a template"
            self._update_helptext(info_text)
        def on_leave(_e):
            self._update_helptext("Hover over mission cards to see parameter information")
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

        title_label = tk.Label(card, text=mission.title, bg=self.palette["panel_light"], fg=self.palette["button_orange"], font=self.fonts["title"], anchor="w")
        title_label.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        # Add double-click to open INI editor at this section
        def _on_title_double_click(_e, m=mission):
            alternative_ini_editor_action(jump=f"[{m.section}]")

        title_label.bind("<Double-1>", _on_title_double_click)

        self._build_card_content(card, mission)

    def _build_card_content(self, card: ttk.Frame, mission: MissionDef) -> None:
        """Hook for subclasses to add content like 'Grab Template' or parameters."""
        # In MissionSettings, this will have the Grab Template dropdown.
        # In OptionalSettings, this might be different or empty.
        template_row = tk.Frame(card, bg=self.palette["panel_light"])
        template_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(6, 4))

        tk.Label(template_row, text="Grab Template:", bg=self.palette["panel_light"], fg=self.palette["text_primary"], font=self.fonts["label"]).pack(side=tk.LEFT)

        options = ["Select a template..."] + get_available_templates()
        cb = ttk.Combobox(template_row, state="readonly", values=options, style="MS.TCombobox", width=20)
        # Restore previously chosen template for this mission, if any
        try:
            prev = self._last_template_choice.get(mission.section)
            if prev and prev in options:
                cb.set(prev)
            else:
                cb.current(0)
        except Exception:
            cb.current(0)
        cb.bind("<<ComboboxSelected>>", lambda _e, m=mission, cbox=cb: self._on_grab_template(m, cbox))
        cb.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

        self._build_parameters_list(card, mission)

    def _build_parameters_list(self, card: ttk.Frame, mission: MissionDef) -> None:
        params_outer = tk.Frame(card, bg=self.palette["panel_dark"])
        params_outer.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 8))
        params_outer.grid_rowconfigure(0, weight=1)
        params_outer.grid_columnconfigure(0, weight=1)
        params_outer.grid_columnconfigure(1, weight=0)  # Scrollbar column - no expansion

        canvas = tk.Canvas(params_outer, bg=self.palette["panel_light"], highlightthickness=0, borderwidth=0)
        vsb = tk.Scrollbar(params_outer, orient=tk.VERTICAL, command=canvas.yview)

        inner = tk.Frame(canvas, bg=self.palette["panel_light"])
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # --- Corrected Mouse Wheel Binding ---
        # Bind mouse wheel events to each widget within this card's hierarchy.
        # This ensures that only the card currently under the mouse cursor will scroll.
        def _on_mousewheel(event):
            # Determine scroll direction based on platform
            # Windows: event.delta is +/-120
            # Linux: event.num is 4 (up) or 5 (down)
            direction = 0
            if event.num == 5 or event.delta < 0: # Scroll down
                direction = 1
            elif event.num == 4 or event.delta > 0: # Scroll up
                direction = -1
            
            if direction != 0:
                canvas.yview_scroll(direction, "units")
            # Return "break" to prevent the event from propagating to other handlers
            return "break"

        def _on_inner_config(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(inner_window, width=event.width)

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", _on_inner_config)

        # Bind the scroll event to the card's main frame and all its children.
        # This ensures that hovering over any part of the card makes it scrollable.
        widgets_to_bind = [card, canvas, inner]

        self.card_widgets[mission.section] = {}

        for key, value in mission.params:
            # Handle blank line separators (key="", value="")
            if key == "":
                separator = tk.Frame(inner, bg=self.palette["panel_light"], height=8)
                separator.pack(fill=tk.X, pady=0)
                widgets_to_bind.append(separator)
                continue
            
            param_row_frame, entry_widget = self._build_param_row(inner, mission, key, value)
            widgets_to_bind.append(param_row_frame)
            widgets_to_bind.extend(param_row_frame.winfo_children())
            self.card_widgets[mission.section][key] = entry_widget

        for widget in widgets_to_bind:
            widget.bind("<MouseWheel>", _on_mousewheel, add=True)
            widget.bind("<Button-4>", _on_mousewheel, add=True)
            widget.bind("<Button-5>", _on_mousewheel, add=True)

    def _build_param_row(self, parent: tk.Frame, mission: MissionDef, key: str, value: str) -> Tuple[tk.Frame, tk.Entry]:
        row = tk.Frame(parent, bg=self.palette["panel_light"])
        row.pack(fill=tk.X, pady=2)
        row.grid_columnconfigure(1, weight=1)

        display_text = self._pretty_label_from_key(key)
        label = tk.Label(row, text=display_text, width=24, anchor="w", bg=self.palette["panel_light"], fg=self.palette["text_primary"], font=self.fonts["label"])
        label.grid(row=0, column=0, sticky="w", padx=(0, 8))

        # Bind click on label to show help
        def on_label_click(_e):
            # Use the original key for help lookup
            help_text = self._get_help_for_key(key)
            self._update_helptext(help_text)
        label.bind("<Button-1>", on_label_click)

        # Hover-Event für Marquee
        def on_enter(event=None, lbl=label, txt=display_text):
            try:
                # Start marquee for this specific label if text is too long
                if len(txt) > self._param_marquee_window_chars:
                    self._start_param_marquee(lbl, txt)
            except Exception:
                pass
        label.bind("<Enter>", on_enter)
        label.bind("<Leave>", lambda _e, lbl=label, txt=display_text: self._stop_param_marquee(lbl, txt))

        var = tk.StringVar(value=value)
        entry = tk.Entry(
            row, textvariable=var, bg=self.palette["entry_bg"], fg=self.palette["entry_fg"],
            insertbackground=self.palette["entry_fg"], relief=tk.FLAT, borderwidth=0,
            font=self.fonts["entry"], justify="center",
        )
        entry.string_var = var  # type: ignore

        key_norm = key.lower()
        is_bool = key_norm.endswith("enabled") or key_norm.startswith("use") or key_norm.startswith("enable") or value.lower() in ('true', 'false')
        is_trap = key_norm == 'traptype'

        # Bind focus/click on entry to show help
        def on_entry_focus(_e):
            # Use the original key for help lookup
            help_text = self._get_help_for_key(key)
            self._update_helptext(help_text)
        entry.bind("<FocusIn>", on_entry_focus)
        entry.bind("<Button-1>", on_entry_focus, add="+")

        if is_bool or is_trap:
            entry.config(state="readonly", readonlybackground=self.palette["entry_bg"], fg=self.palette["entry_fg"])
            def _on_special_edit_click(_e, m=mission, k=key):
                if is_trap: self._open_traptype_popup(m, k, entry)
                elif is_bool: self._open_bool_popup(m, k, entry)
            entry.bind("<Button-1>", _on_special_edit_click)
        else:
            entry.bind("<FocusOut>", lambda _e, sec=mission.section, k=key, e=entry: self._set_param_value(sec, k, e.get()))
        
        # Add Up/Down arrow navigation
        def _on_arrow_nav(event, m=mission, k=key):
            param_keys = [p[0] for p in m.params if p[0]] # Get only valid keys, ignore separators
            try:
                idx = param_keys.index(k)
            except ValueError:
                return # Should not happen

            if event.keysym == 'Down':
                next_idx = (idx + 1) % len(param_keys)
            elif event.keysym == 'Up':
                next_idx = (idx - 1 + len(param_keys)) % len(param_keys)
            else:
                return

            next_key = param_keys[next_idx]
            next_entry = self.card_widgets.get(m.section, {}).get(next_key)
            if next_entry:
                next_entry.focus_set()
                next_entry.icursor(tk.END)
                return "break"
        entry.bind("<Up>", _on_arrow_nav)
        entry.bind("<Down>", _on_arrow_nav)

        entry.grid(row=0, column=1, sticky="ew")
        return row, entry

    def _start_param_marquee(self, label_widget: tk.Label, text: str) -> None:
        """Start marquee animation for a specific parameter label."""
        self._stop_param_marquee()  # Stop any existing marquee
        
        self._param_marquee_widget = label_widget
        self._param_marquee_text = text
        self._param_marquee_index = 0
        
        # Animate if text is longer than the widget can display
        if len(text) > self._param_marquee_window_chars:
            self._param_marquee_job = self.root.after(750, self._animate_param_marquee)

    def _stop_param_marquee(self, label_widget: Optional[tk.Label] = None, original_text: Optional[str] = None) -> None:
        """Stop the parameter marquee and restore the original text."""
        if self._param_marquee_job:
            try:
                self.root.after_cancel(self._param_marquee_job)
            except Exception:
                pass
            self._param_marquee_job = None

        # Restore the text of the specific widget that was animated
        if self._param_marquee_widget and self._param_marquee_widget.winfo_exists():
            try:
                self._param_marquee_widget.config(text=self._param_marquee_text)
            except Exception:
                pass
        
        self._param_marquee_widget = None
        self._param_marquee_text = ""

    def _animate_param_marquee(self) -> None:
        """Animation step for the parameter label marquee."""
        if not self._param_marquee_widget or not self._param_marquee_widget.winfo_exists():
            return

        text = self._param_marquee_text
        window = self._param_marquee_window_chars
        
        end_index = max(0, len(text) - window)
        
        if self._param_marquee_index <= end_index:
            display_text = text[self._param_marquee_index : self._param_marquee_index + window]
            self._param_marquee_widget.config(text=display_text)
            if self._param_marquee_index == end_index:
                self._param_marquee_job = self.root.after(self.marquee_pause_ms, self._animate_param_marquee)
            else:
                self._param_marquee_index += 1
                self._param_marquee_job = self.root.after(self.marquee_delay_ms, self._animate_param_marquee)
        else:
            self._param_marquee_index = 0
            self._param_marquee_job = self.root.after(self.marquee_delay_ms, self._animate_param_marquee)

    def _open_bool_popup(self, mission: MissionDef, key: str, entry_widget: tk.Entry) -> None:
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=self.palette["panel_dark"])

        def choose(val: str) -> None:
            entry_widget.string_var.set(val) # type: ignore
            self._set_param_value(mission.section, key, val)
            win.destroy()

        x = entry_widget.winfo_rootx()
        y = entry_widget.winfo_rooty() + entry_widget.winfo_height()
        win.geometry(f"120x80+{x}+{y}")

        frame = tk.Frame(win, bg=self.palette["panel_dark"], padx=6, pady=6)
        frame.pack(fill=tk.BOTH, expand=True)

        current_val = entry_widget.get().lower()
        true_bg = self.palette["button_green"] if current_val == 'true' else self.palette["button_gray"]
        false_bg = self.palette["button_green"] if not current_val == 'true' else self.palette["button_gray"]

        tk.Button(frame, text="true", bg=true_bg, fg=self.palette["button_text"], relief=tk.FLAT, command=lambda: choose('true')).pack(fill=tk.X, pady=(0, 4))
        tk.Button(frame, text="false", bg=false_bg, fg=self.palette["button_text"], relief=tk.FLAT, command=lambda: choose('false')).pack(fill=tk.X)

    def _open_traptype_popup(self, mission: MissionDef, key: str, entry_widget: tk.Entry) -> None:
        options = ["Explosive", "Flashbang", "Alarm"]
        current_values = {v.strip() for v in entry_widget.get().split(',') if v.strip()}

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=self.palette["panel_dark"])

        x = entry_widget.winfo_rootx()
        y = entry_widget.winfo_rooty() + entry_widget.winfo_height()
        win.geometry(f"240x150+{x}+{y}")

        frame = tk.Frame(win, bg=self.palette["panel_dark"], padx=8, pady=8)
        frame.pack(fill=tk.BOTH, expand=True)

        vars_map: dict[str, tk.BooleanVar] = {}
        for i, name in enumerate(options):
            var = tk.BooleanVar(value=(name in current_values))
            vars_map[name] = var
            chk = tk.Checkbutton(
                frame, text=name, variable=var, anchor='w', bg=self.palette["panel_dark"], fg=self.palette["button_text"],
                activebackground=self.palette["panel_dark"], activeforeground=self.palette["button_text"],
                selectcolor=self.palette["panel_light"], relief=tk.FLAT, borderwidth=0
            )
            chk.grid(row=i, column=0, sticky="ew")

        def apply_close() -> None:
            new_values = [k for k, v in vars_map.items() if v.get()]
            val_str = ", ".join(new_values)
            entry_widget.string_var.set(val_str) # type: ignore
            self._set_param_value(mission.section, key, val_str)
            win.destroy()

        btn_frame = tk.Frame(frame, bg=self.palette["panel_dark"])
        btn_frame.grid(row=len(options), column=0, sticky="e", pady=(8, 0))
        tk.Button(btn_frame, text="OK", bg=self.palette["button_green"], fg=self.palette["button_text"], relief=tk.FLAT, command=apply_close).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="Cancel", bg=self.palette["button_gray"], fg=self.palette["button_text"], relief=tk.FLAT, command=win.destroy).pack(side=tk.LEFT, padx=(6, 0))

    def _set_mission_image(self, label: tk.Label, section: str) -> None:
        pic_path = self.pic_map.get(_normalize_section_key(section))
        if not pic_path or not pic_path.exists() or Image is None:
            label.configure(text="(no image)" if not pic_path else pic_path.name, fg=self.palette["text_muted"])
            return
        try:
            img = Image.open(str(pic_path)).convert("RGBA")
            target_w = 320
            ratio = target_w / img.width if img.width > 0 else 1
            target_h = int(img.height * ratio)
            img = img.resize((target_w, max(1, target_h)), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            label.configure(image=tk_img, text="")
            label.image = tk_img
        except Exception:
            label.configure(text=pic_path.name, fg=self.palette["text_muted"])

    def _on_grab_template(self, mission: MissionDef, cbox: ttk.Combobox) -> None:
        choice = cbox.get()
        if choice == "Select a template...":
            cbox.current(0)
            return
        try:
            # Persist the user's choice so it remains visible and can be restored
            try:
                self._last_template_choice[mission.section] = choice
            except Exception:
                pass
            from system.programs.Live_Mod.Global_Mission_Settings.config_gms.gms_actions import _find_template_path
            tpl_path = _find_template_path(choice)
            if not tpl_path or not tpl_path.exists():
                show_error(f"Template '{choice}' not found.", parent=self.root)
                cbox.current(0)
                return

            tpl_text = tpl_path.read_text(encoding="utf-8", errors="ignore")
            if not tpl_text:
                show_error(f"Could not read template '{choice}'.", parent=self.root)
                cbox.current(0)
                return

            match = re.search(f"^\\[{re.escape(mission.section)}\\]", tpl_text, re.MULTILINE | re.IGNORECASE)
            if not match:
                show_error(f"Section '{mission.section}' not found in template.", parent=self.root)
                cbox.current(0)
                return

            end_match = re.search(r"^\s*\[", tpl_text[match.end():], re.MULTILINE)
            end = (match.end() + end_match.start()) if end_match else len(tpl_text)
            template_section_block = tpl_text[match.start():end]

            updates: Dict[str, str] = {}
            for raw in template_section_block.splitlines():
                line = raw.strip()
                if line.startswith('[') and line.endswith(']') and line.lower() != f"[{mission.section.lower()}]":
                    break
                if line and not line.startswith(('#', ';', '[')) and '=' in line:
                    try:
                        k, v = line.split('=', 1)
                        updates[k.strip()] = v.split(';')[0].split('#')[0].strip()
                    except Exception:
                        pass

            if not updates:
                show_error(f"No parameters found in template section.", parent=self.root)
                cbox.current(0)
                return
            
            # Batch write for performance
            try:
                from ..config_ms.actions_ms import write_mission_parameters
                write_mission_parameters(mission.section, updates)
            except Exception:
                # Fallback to per-key writes if batch fails
                for key, value in updates.items():
                    write_mission_parameter(mission.section, key, value)

            # Schedule refresh in main loop to avoid operating on destroyed widgets
            try:
                self.root.after(0, self.refresh_data)
            except Exception:
                self.refresh_data()
        except Exception as e:
            show_error(f"Failed to apply template: {e}", parent=self.root)

    def _pretty_label_from_key(self, key: str) -> str:
        """Convert an INI key into a human-readable label."""
        try:
            s = key.replace("_", " ").replace(".", " ")
            s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s
        except Exception:
            return key

    def _set_param_value(self, section: str, key: str, value: str) -> None:
        write_mission_parameter(section, key, value)
        for m in self.missions:
            if m.section == section:
                m.params = [(k, (value if k == key else v)) for (k, v) in m.params]
