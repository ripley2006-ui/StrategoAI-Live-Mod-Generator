"""Unified dark-themed dialog system for consistent UI across the application.

All message dialogs use the same size and style, adapting only content.
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Literal

# Standard dialog dimensions (optimized smaller size)
DIALOG_WIDTH = 480
DIALOG_HEIGHT = 160
DIALOG_PADDING = 16

# Dark theme colors
COLORS = {
    "bg": "#1d1f23",
    "panel": "#2a2d33",
    "text": "#f8fafc",
    "button_red": "#b91c1c",
    "button_red_pressed": "#7f1d1d",
    "button_orange": "#f97316",
    "button_orange_pressed": "#c2410c",
    "button_gray": "#4b5563",
    "button_gray_pressed": "#374151",
    "button_blue": "#1d4ed8",
    "button_blue_pressed": "#1e3a8a",
}


def _create_dialog_base(parent: tk.Widget | None, title: str) -> tuple[tk.Toplevel, tk.Frame]:
    """Create a standard dark-themed dialog window with fixed size."""
    dialog = tk.Toplevel()
    dialog.title(title)
    if parent:
        dialog.transient(parent)
        # Center on parent
        try:
            dialog.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - DIALOG_WIDTH) // 2
            y = py + (ph - DIALOG_HEIGHT) // 2
            dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}+{x}+{y}")
        except Exception:
            # Center on screen if parent positioning fails
            dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
    else:
        # Center on screen
        try:
            dialog.update_idletasks()
            screen_w = dialog.winfo_screenwidth()
            screen_h = dialog.winfo_screenheight()
            x = (screen_w - DIALOG_WIDTH) // 2
            y = (screen_h - DIALOG_HEIGHT) // 2
            dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}+{x}+{y}")
        except Exception:
            dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
    
    try:
        dialog.iconbitmap(False)
    except Exception:
        pass
    
    try:
        dialog.configure(bg=COLORS["bg"])
    except Exception:
        pass
    
    dialog.resizable(False, False)
    dialog.grab_set()
    
    # Remove black border by setting dialog background to match frame
    try:
        dialog.configure(bg=COLORS["panel"])
    except Exception:
        pass
    
    # Content frame
    frame = tk.Frame(dialog, bg=COLORS["panel"])
    frame.pack(fill=tk.BOTH, expand=True, padx=DIALOG_PADDING, pady=DIALOG_PADDING)
    
    return dialog, frame


def show_info(message: str, title: str = "StrategoAI", parent: tk.Widget | None = None) -> None:
    """Show an information dialog with OK button."""
    dialog, frame = _create_dialog_base(parent, title)
    
    # Message label (centered)
    lbl = tk.Label(
        frame,
        text=message,
        bg=COLORS["panel"],
        fg=COLORS["text"],
        font=("Segoe UI", 11, "bold"),
        justify="center",
        wraplength=DIALOG_WIDTH - 2 * DIALOG_PADDING - 20,
        anchor="center"
    )
    lbl.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
    
    # OK button (centered)
    def on_ok():
        dialog.destroy()
    
    btn_frame = tk.Frame(frame, bg=COLORS["panel"])
    btn_frame.pack(anchor="center")
    
    ok_btn = tk.Button(
        btn_frame,
        text="OK",
        command=on_ok,
        bg=COLORS["button_orange"],
        fg=COLORS["text"],
        activebackground=COLORS["button_orange_pressed"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        borderwidth=0,
        width=14,
        font=("Segoe UI", 11, "bold")
    )
    ok_btn.pack()
    
    dialog.bind("<Return>", lambda e: on_ok())
    dialog.bind("<Escape>", lambda e: on_ok())
    dialog.protocol("WM_DELETE_WINDOW", on_ok)
    
    try:
        ok_btn.focus_set()
    except Exception:
        pass
    
    dialog.wait_window()


def show_error(message: str, title: str = "StrategoAI Error", parent: tk.Widget | None = None) -> None:
    """Show an error dialog with OK button."""
    dialog, frame = _create_dialog_base(parent, title)
    
    # Message label (centered)
    lbl = tk.Label(
        frame,
        text=message,
        bg=COLORS["panel"],
        fg=COLORS["text"],
        font=("Segoe UI", 11, "bold"),
        justify="center",
        wraplength=DIALOG_WIDTH - 2 * DIALOG_PADDING - 20,
        anchor="center"
    )
    lbl.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
    
    # OK button (centered)
    def on_ok():
        dialog.destroy()
    
    btn_frame = tk.Frame(frame, bg=COLORS["panel"])
    btn_frame.pack(anchor="center")
    
    ok_btn = tk.Button(
        btn_frame,
        text="OK",
        command=on_ok,
        bg=COLORS["button_red"],
        fg=COLORS["text"],
        activebackground=COLORS["button_red_pressed"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        borderwidth=0,
        width=14,
        font=("Segoe UI", 11, "bold")
    )
    ok_btn.pack()
    
    dialog.bind("<Return>", lambda e: on_ok())
    dialog.bind("<Escape>", lambda e: on_ok())
    dialog.protocol("WM_DELETE_WINDOW", on_ok)
    
    try:
        ok_btn.focus_set()
    except Exception:
        pass
    
    dialog.wait_window()


def ask_yes_no(
    message: str,
    title: str = "StrategoAI",
    yes_text: str = "Yes",
    no_text: str = "No",
    parent: tk.Widget | None = None
) -> bool:
    """Show a Yes/No confirmation dialog. Returns True if Yes, False if No."""
    dialog, frame = _create_dialog_base(parent, title)
    
    # Message label (centered)
    lbl = tk.Label(
        frame,
        text=message,
        bg=COLORS["panel"],
        fg=COLORS["text"],
        font=("Segoe UI", 11, "bold"),
        justify="center",
        wraplength=DIALOG_WIDTH - 2 * DIALOG_PADDING - 20,
        anchor="center"
    )
    lbl.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
    
    result = {"value": False}
    
    def on_yes():
        result["value"] = True
        dialog.destroy()
    
    def on_no():
        result["value"] = False
        dialog.destroy()
    
    # Button frame (right-aligned)
    btn_frame = tk.Frame(frame, bg=COLORS["panel"])
    btn_frame.pack(anchor="e")
    
    no_btn = tk.Button(
        btn_frame,
        text=no_text,
        command=on_no,
        bg=COLORS["button_gray"],
        fg=COLORS["text"],
        activebackground=COLORS["button_gray_pressed"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        borderwidth=0,
        width=12,
        font=("Segoe UI", 11, "bold")
    )
    no_btn.pack(side=tk.RIGHT)
    
    yes_btn = tk.Button(
        btn_frame,
        text=yes_text,
        command=on_yes,
        bg=COLORS["button_orange"],
        fg=COLORS["text"],
        activebackground=COLORS["button_orange_pressed"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        borderwidth=0,
        width=12,
        font=("Segoe UI", 11, "bold")
    )
    yes_btn.pack(side=tk.RIGHT, padx=(0, 8))
    
    dialog.bind("<Return>", lambda e: on_yes())
    dialog.bind("<Escape>", lambda e: on_no())
    dialog.protocol("WM_DELETE_WINDOW", on_no)
    
    try:
        yes_btn.focus_set()
    except Exception:
        pass
    
    dialog.wait_window()
    return result["value"]


def ask_yes_cancel(
    message: str,
    title: str = "StrategoAI",
    yes_text: str = "Yes",
    cancel_text: str = "Cancel",
    parent: tk.Widget | None = None
) -> bool | None:
    """Show a Yes/Cancel confirmation dialog. Returns True if Yes, None if Cancel."""
    dialog, frame = _create_dialog_base(parent, title)
    
    # Message label (centered)
    lbl = tk.Label(
        frame,
        text=message,
        bg=COLORS["panel"],
        fg=COLORS["text"],
        font=("Segoe UI", 11, "bold"),
        justify="center",
        wraplength=DIALOG_WIDTH - 2 * DIALOG_PADDING - 20,
        anchor="center"
    )
    lbl.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
    
    result: dict[str, bool | None] = {"value": None}
    
    def on_yes():
        result["value"] = True
        dialog.destroy()
    
    def on_cancel():
        result["value"] = None
        dialog.destroy()
    
    # Button frame (right-aligned)
    btn_frame = tk.Frame(frame, bg=COLORS["panel"])
    btn_frame.pack(anchor="e")
    
    cancel_btn = tk.Button(
        btn_frame,
        text=cancel_text,
        command=on_cancel,
        bg=COLORS["button_gray"],
        fg=COLORS["text"],
        activebackground=COLORS["button_gray_pressed"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        borderwidth=0,
        width=12,
        font=("Segoe UI", 11, "bold")
    )
    cancel_btn.pack(side=tk.RIGHT)
    
    yes_btn = tk.Button(
        btn_frame,
        text=yes_text,
        command=on_yes,
        bg=COLORS["button_orange"],
        fg=COLORS["text"],
        activebackground=COLORS["button_orange_pressed"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        borderwidth=0,
        width=12,
        font=("Segoe UI", 11, "bold")
    )
    yes_btn.pack(side=tk.RIGHT, padx=(0, 8))
    
    dialog.bind("<Return>", lambda e: on_yes())
    dialog.bind("<Escape>", lambda e: on_cancel())
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)
    
    try:
        yes_btn.focus_set()
    except Exception:
        pass
    
    dialog.wait_window()
    return result["value"]


def ask_confirm_destructive(
    message: str,
    title: str = "StrategoAI",
    action_text: str = "Delete",
    cancel_text: str = "Cancel",
    parent: tk.Widget | None = None
) -> bool:
    """Show a destructive action confirmation (red button). Returns True if confirmed."""
    dialog, frame = _create_dialog_base(parent, title)
    
    # Message label (centered)
    lbl = tk.Label(
        frame,
        text=message,
        bg=COLORS["panel"],
        fg=COLORS["text"],
        font=("Segoe UI", 11, "bold"),
        justify="center",
        wraplength=DIALOG_WIDTH - 2 * DIALOG_PADDING - 20,
        anchor="center"
    )
    lbl.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
    
    result = {"value": False}
    
    def on_confirm():
        result["value"] = True
        dialog.destroy()
    
    def on_cancel():
        result["value"] = False
        dialog.destroy()
    
    # Button frame (right-aligned)
    btn_frame = tk.Frame(frame, bg=COLORS["panel"])
    btn_frame.pack(anchor="e")
    
    cancel_btn = tk.Button(
        btn_frame,
        text=cancel_text,
        command=on_cancel,
        bg=COLORS["button_gray"],
        fg=COLORS["text"],
        activebackground=COLORS["button_gray_pressed"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        borderwidth=0,
        width=12,
        font=("Segoe UI", 11, "bold")
    )
    cancel_btn.pack(side=tk.RIGHT)
    
    action_btn = tk.Button(
        btn_frame,
        text=action_text,
        command=on_confirm,
        bg=COLORS["button_red"],
        fg=COLORS["text"],
        activebackground=COLORS["button_red_pressed"],
        activeforeground=COLORS["text"],
        relief=tk.FLAT,
        borderwidth=0,
        width=12,
        font=("Segoe UI", 11, "bold")
    )
    action_btn.pack(side=tk.RIGHT, padx=(0, 8))
    
    dialog.bind("<Return>", lambda e: on_confirm())
    dialog.bind("<Escape>", lambda e: on_cancel())
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)
    
    try:
        action_btn.focus_set()
    except Exception:
        pass
    
    dialog.wait_window()
    return result["value"]


__all__ = [
    "show_info",
    "show_error",
    "ask_yes_no",
    "ask_yes_cancel",
    "ask_confirm_destructive",
]
