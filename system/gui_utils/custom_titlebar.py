"""Custom titlebar for the main window with minimize and close buttons."""

import tkinter as tk
from typing import Callable, Optional


class CustomTitleBar:
    """A custom titlebar with dragging, minimize, and close functionality."""
    
    def __init__(
        self,
        parent: tk.Widget,
        title: str = "",
        bg_color: str = "#2b2b2b",
        text_color: str = "#f5f5f5",
        close_callback: Optional[Callable[[], None]] = None
    ):
        self.parent = parent
        self.root = parent.winfo_toplevel()
        self.close_callback = close_callback
        
        # Create titlebar frame
        self.frame = tk.Frame(parent, bg=bg_color, height=32)
        self.frame.pack(side=tk.TOP, fill=tk.X)
        self.frame.pack_propagate(False)
        
        # Minimize button (left side)
        self.minimize_btn = tk.Button(
            self.frame,
            text="−",
            font=("Segoe UI", 14, "bold"),
            bg=bg_color,
            fg=text_color,
            activebackground="#404040",
            activeforeground=text_color,
            relief=tk.FLAT,
            bd=0,
            width=3,
            command=self._minimize_window
        )
        self.minimize_btn.pack(side=tk.LEFT, padx=(4, 0))
        
        # Title label (center)
        self.title_label = tk.Label(
            self.frame,
            text=title,
            bg=bg_color,
            fg=text_color,
            font=("Segoe UI", 10, "bold")
        )
        self.title_label.pack(side=tk.LEFT, padx=10, expand=True)
        
        # Close button (right side, red)
        self.close_btn = tk.Button(
            self.frame,
            text="✕",
            font=("Segoe UI", 12, "bold"),
            bg="#b91c1c",  # Red background
            fg="#ffffff",
            activebackground="#7f1d1d",  # Darker red when clicked
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            width=3,
            command=self._close_window
        )
        self.close_btn.pack(side=tk.RIGHT, padx=(0, 4))
        
        # Enable dragging
        self._drag_start_x = 0
        self._drag_start_y = 0
        self.frame.bind("<Button-1>", self._start_drag)
        self.frame.bind("<B1-Motion>", self._on_drag)
        self.title_label.bind("<Button-1>", self._start_drag)
        self.title_label.bind("<B1-Motion>", self._on_drag)
    
    def _minimize_window(self) -> None:
        """Minimize the window to taskbar."""
        try:
            self.root.iconify()
        except Exception:
            pass
    
    def _close_window(self) -> None:
        """Close the window."""
        if self.close_callback:
            self.close_callback()
        else:
            try:
                self.root.destroy()
            except Exception:
                pass
    
    def _start_drag(self, event: tk.Event) -> None:
        """Start dragging the window."""
        self._drag_start_x = event.x
        self._drag_start_y = event.y
    
    def _on_drag(self, event: tk.Event) -> None:
        """Handle window dragging."""
        try:
            x = self.root.winfo_x() + event.x - self._drag_start_x
            y = self.root.winfo_y() + event.y - self._drag_start_y
            self.root.geometry(f"+{x}+{y}")
        except Exception:
            pass


__all__ = ["CustomTitleBar"]
