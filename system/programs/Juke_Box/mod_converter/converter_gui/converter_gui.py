"""Tkinter based UI for the Mod Converter - Foreign Mod to Live Mod Format."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageTk  # type: ignore
except Exception:
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

from ..converter_config.converter_config import (
    ACTION_BUTTONS,
    DEFAULT_HELP_TEXT,
    WINDOW_HEIGHT,
    WINDOW_MIN_SIZE,
    WINDOW_MAX_SIZE,
    WINDOW_TITLE,
    WINDOW_WIDTH,
    LEFT_PANEL_RATIO,
    ConversionJob,
    STATUS_PENDING,
    STATUS_EXTRACTING,
    STATUS_CONVERTING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    current_date_string,
)

from system.gui_utils.unified_dialogs import show_info, show_error, ask_yes_cancel

from ..converter_config.converter_actions import (
    ActionNotImplementedError,
    extract_pak_action,
    detect_mod_name,
    validate_foreign_ini,
    convert_ini_to_live_mod,
    process_conversion_job,
    open_output_folder,
    cleanup_temp_files,
)


class ModConverterApp:
    """Mod Converter application for converting foreign mods to Live Mod format.

    This UI allows users to:
    - Add INI files or PAK files for conversion
    - Extract INI from PAK archives
    - Convert foreign mod format to Live Mod format
    - Manage conversion queue
    """

    def __init__(self, parent: tk.Widget | None = None, main_app=None) -> None:
        """Initialize the Mod Converter application.

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
                "success": base_palette.get("success", base_palette.get("status_green_bg", "#22c55e")),
                "warning": base_palette.get("warning", "#f59e0b"),
                "error": base_palette.get("error", base_palette.get("status_red_bg", "#ef4444")),
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
                "success": "#22c55e",
                "warning": "#f59e0b",
                "error": "#ef4444",
            }

        # State
        self.conversion_jobs: list[ConversionJob] = []
        self.selected_job: Optional[ConversionJob] = None

        # UI Components
        self.main_frame: Optional[tk.Frame] = None
        self.left_panel: Optional[tk.Frame] = None
        self.right_panel: Optional[tk.Frame] = None
        self.jobs_listbox: Optional[tk.Listbox] = None
        self.log_text: Optional[tk.Text] = None

        # Initialize UI
        self._setup_window()
        self._build_layout()
        self._show_welcome_message()

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

        # Left panel (conversion queue + actions)
        self._build_left_panel()

        # Right panel (conversion log)
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        """Build the left panel with conversion queue and action buttons."""
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
            text="Conversion Queue",
            font=("Segoe UI", 12, "bold"),
            bg=self.palette["content_bg"],
            fg=self.palette["text_primary"],
        )
        title_label.pack(pady=(10, 5))

        # Jobs listbox
        listbox_frame = tk.Frame(self.left_panel, bg=self.palette["content_bg"])
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(listbox_frame)
        scrollbar.pack(side="right", fill="y")

        self.jobs_listbox = tk.Listbox(
            listbox_frame,
            bg=self.palette["background"],
            fg=self.palette["text_primary"],
            selectbackground=self.palette["accent"],
            selectforeground=self.palette["text_primary"],
            font=("Segoe UI", 9),
            yscrollcommand=scrollbar.set,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )
        self.jobs_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.jobs_listbox.yview)

        self.jobs_listbox.bind("<<ListboxSelect>>", self._on_job_selected)

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
        """Build the right panel with conversion log."""
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
            text="Conversion Log",
            font=("Segoe UI", 12, "bold"),
            bg=self.palette["content_bg"],
            fg=self.palette["text_primary"],
        )
        title_label.pack(pady=(10, 5))

        # Log text widget
        text_frame = tk.Frame(self.right_panel, bg=self.palette["content_bg"])
        text_frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        self.log_text = tk.Text(
            text_frame,
            bg=self.palette["background"],
            fg=self.palette["text_primary"],
            font=("Consolas", 9),
            wrap="word",
            yscrollcommand=scrollbar.set,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.palette["border"],
            state="disabled",
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_text.yview)

        # Configure text tags for colored output
        self.log_text.tag_config("info", foreground=self.palette["text_secondary"])
        self.log_text.tag_config("success", foreground=self.palette["success"])
        self.log_text.tag_config("warning", foreground=self.palette["warning"])
        self.log_text.tag_config("error", foreground=self.palette["error"])

    def _show_welcome_message(self) -> None:
        """Display welcome message in the log."""
        self._log_message(DEFAULT_HELP_TEXT, "info")

    def _log_message(self, message: str, tag: str = "info") -> None:
        """Add a message to the conversion log.

        Args:
            message: Message text
            tag: Text tag for coloring (info, success, warning, error)
        """
        if not self.log_text:
            return

        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"{message}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def _update_jobs_list(self) -> None:
        """Update the jobs listbox with current conversion jobs."""
        if not self.jobs_listbox:
            return

        self.jobs_listbox.delete(0, tk.END)
        for job in self.conversion_jobs:
            source_name = Path(job.source_path).name
            display = f"[{job.status}] {source_name}"
            self.jobs_listbox.insert(tk.END, display)

    def _on_job_selected(self, event) -> None:
        """Handle job selection."""
        if not self.jobs_listbox:
            return

        selection = self.jobs_listbox.curselection()
        if not selection:
            self.selected_job = None
            return

        idx = selection[0]
        if 0 <= idx < len(self.conversion_jobs):
            self.selected_job = self.conversion_jobs[idx]
            self._log_message(f"\nSelected: {Path(self.selected_job.source_path).name}", "info")

    def _execute_action(self, action_id: str) -> None:
        """Execute an action by its ID."""
        try:
            if action_id == "add_ini":
                self._handle_add_ini()
            elif action_id == "add_pak":
                self._handle_add_pak()
            elif action_id == "start_conversion":
                self._handle_start_conversion()
            elif action_id == "clear_completed":
                self._handle_clear_completed()
            elif action_id == "open_output":
                self._handle_open_output()
            else:
                show_info(self.root, "Info", f"Action '{action_id}' not implemented yet.")

        except ActionNotImplementedError as e:
            show_info(self.root, "Not Implemented", str(e))
        except Exception as e:
            show_error(self.root, "Error", f"Action failed: {e}")

    # Action handlers

    def _handle_add_ini(self) -> None:
        """Handle add INI file action."""
        file_path = filedialog.askopenfilename(
            parent=self.root,
            title="Select Foreign Mod INI File",
            filetypes=[("INI Files", "*.ini"), ("All Files", "*.*")],
        )

        if not file_path:
            return

        # Detect mod name
        mod_name = detect_mod_name(Path(file_path))

        # Add to conversion queue
        job = ConversionJob(
            source_path=file_path,
            source_type="ini",
            mod_name=mod_name,
            status=STATUS_PENDING,
        )

        self.conversion_jobs.append(job)
        self._update_jobs_list()
        self._log_message(f"Added INI file: {Path(file_path).name}", "success")

    def _handle_add_pak(self) -> None:
        """Handle add PAK file action."""
        file_path = filedialog.askopenfilename(
            parent=self.root,
            title="Select Packed Mod (.pak) File",
            filetypes=[("PAK Files", "*.pak"), ("All Files", "*.*")],
        )

        if not file_path:
            return

        # Detect mod name from filename
        mod_name = Path(file_path).stem

        # Add to conversion queue
        job = ConversionJob(
            source_path=file_path,
            source_type="pak",
            mod_name=mod_name,
            status=STATUS_PENDING,
        )

        self.conversion_jobs.append(job)
        self._update_jobs_list()
        self._log_message(f"Added PAK file: {Path(file_path).name}", "success")

    def _handle_start_conversion(self) -> None:
        """Handle start conversion action."""
        pending_jobs = [j for j in self.conversion_jobs if j.status == STATUS_PENDING]

        if not pending_jobs:
            show_info(self.root, "No Jobs", "No pending conversion jobs in queue.")
            return

        self._log_message(f"\n=== Starting conversion of {len(pending_jobs)} job(s) ===", "info")

        for job in pending_jobs:
            self._convert_job(job)

        self._log_message("\n=== Conversion batch completed ===", "success")

    def _convert_job(self, job: ConversionJob) -> None:
        """Convert a single job.

        Args:
            job: ConversionJob to process
        """
        try:
            self._log_message(f"\nProcessing: {Path(job.source_path).name}", "info")

            # Update status
            job.status = STATUS_EXTRACTING if job.source_type == "pak" else STATUS_CONVERTING
            self._update_jobs_list()

            # Process the conversion
            success, message, output_path = process_conversion_job(job.source_path, job.source_type)

            if success:
                job.status = STATUS_COMPLETED
                job.output_path = output_path
                self._log_message(f" {message}", "success")
                self._log_message(f"  Output: {output_path}", "info")
            else:
                job.status = STATUS_FAILED
                self._log_message(f" {message}", "error")

        except Exception as e:
            job.status = STATUS_FAILED
            self._log_message(f" Error: {e}", "error")

        finally:
            self._update_jobs_list()

    def _handle_clear_completed(self) -> None:
        """Handle clear completed jobs action."""
        initial_count = len(self.conversion_jobs)
        self.conversion_jobs = [j for j in self.conversion_jobs if j.status != STATUS_COMPLETED]
        removed_count = initial_count - len(self.conversion_jobs)

        if removed_count > 0:
            self._update_jobs_list()
            self._log_message(f"\nCleared {removed_count} completed job(s)", "info")
        else:
            show_info(self.root, "Nothing to Clear", "No completed jobs in queue.")

    def _handle_open_output(self) -> None:
        """Handle open output folder action."""
        try:
            open_output_folder()
            self._log_message("\nOpened output folder in file explorer", "success")
        except Exception as e:
            show_error(self.root, "Error", f"Failed to open output folder: {e}")

    def run(self) -> None:
        """Start the application main loop (standalone mode only)."""
        if not self._embedded_mode:
            self.root.mainloop()


def create_app(parent: tk.Widget, main_app=None) -> ModConverterApp:
    """Factory function to create a Mod Converter app instance.

    Args:
        parent: Parent widget for embedded mode
        main_app: Reference to main application

    Returns:
        ModConverterApp instance
    """
    return ModConverterApp(parent, main_app=main_app)


__all__ = ["ModConverterApp", "create_app"]
