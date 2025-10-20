"""Tkinter-based INI Editor for StrategoAI Live Mod Generator."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path
import re

# Import event bus for notifying other UIs when work.ini is saved
try:
    from system.gui_utils import event_bus as _event_bus  # type: ignore
except Exception:
    _event_bus = None  # type: ignore


def default_work_ini_path() -> str:
    """Return the default work.ini path in user's AppData."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return os.path.join(base, "ReadyOrNot", "Saved", "Config", "StrategoAI_Live_Mod", "Work", "work.ini")


class IniEditorWindow:
    def __init__(self, parent: tk.Widget | None = None, path: str | None = None, jump: str | None = None):
        if parent:
            self.root = tk.Toplevel(parent)
            self.root.transient(parent)
            self.root.grab_set()
        else:
            self.root = tk.Tk()
        self.root.title("StrategoAI - INI Editor")
        self.root.geometry("1100x850+200+50")
        self.root.configure(bg="#1d1f23")
        
        self.filepath = path or ""
        self.dirty = False
        self.baseline_text = ""
        self.jump_token = jump or ""
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        self.suggestion_listbox: tk.Listbox | None = None
        self.suggestions: list[str] = []
        
        # Create main layout
        self._build_ui()
        
        # Auto-load file if provided
        if not self.filepath or not os.path.isfile(self.filepath):
            try:
                self.filepath = default_work_ini_path()
            except Exception:
                pass
        
        if self.filepath and os.path.isfile(self.filepath):
            self._load_file(self.filepath)
        
        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def wait_window(self):
        """Wait for the window to be destroyed (used when modal)."""
        self.root.wait_window(self.root)
    
    def _build_ui(self):
        """Build the UI components."""
        # Main container with splitter-like layout
        main_frame = tk.Frame(self.root, bg="#1d1f23")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side: Text editor
        editor_frame = tk.Frame(main_frame, bg="#1d1f23")
        editor_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Text editor with scrollbar
        self.text_editor = scrolledtext.ScrolledText(
            editor_frame,
            wrap=tk.NONE,
            font=("Consolas", 14, "bold"),  # Größere, fette Schrift
            bg="#111111",
            fg="#F5F5F5",
            insertbackground="#F5F5F5",
            selectbackground="#4a4a4a",
            selectforeground="#F5F5F5",
            borderwidth=0,
            highlightthickness=0,
            undo=True
        )
        self.text_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self._create_context_menu()
        self.text_editor.bind("<<Modified>>", self._on_text_changed)
        
        # Bind Tab and Shift-Tab for value navigation
        self.text_editor.bind("<Tab>", self._on_tab_forward)
        self.text_editor.bind("<Shift-Tab>", self._on_tab_backward)
        
        # Right side: Section list
        sections_frame = tk.Frame(main_frame, bg="#6a6a6a", width=260)
        sections_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=5, pady=5)
        sections_frame.pack_propagate(False)
        
        tk.Label(
            sections_frame,
            text="Sections",
            bg="#6a6a6a",
            fg="#0a0a0a",
            font=("Arial", 12, "bold")
        ).pack(pady=5)
        
        self.sections_list = tk.Listbox(
            sections_frame,
            bg="#6a6a6a",
            fg="#0a0a0a",
            font=("Arial", 11, "bold"),
            selectbackground="#5a5a5a",
            selectforeground="#FFFFFF",
            borderwidth=0,
            highlightthickness=0
        )
        self.sections_list.pack(fill=tk.BOTH, expand=True)
        self.sections_list.bind("<<ListboxSelect>>", self._on_section_click)
        
        # Bottom: Buttons
        button_frame = tk.Frame(self.root, bg="#2a2d33")
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        button_style = {
            "bg": "#3a3a3a",
            "fg": "#f5f5f5",
            "activebackground": "#4a4a4a",
            "activeforeground": "#f5f5f5",
            "borderwidth": 0,
            "highlightthickness": 0,
            "font": ("Segoe UI", 10),
            "padx": 12,
            "pady": 6
        }
        
        tk.Button(button_frame, text="Open...", command=self._on_open, **button_style).pack(side=tk.LEFT, padx=2)
        tk.Button(button_frame, text="Save", command=self._on_save, **button_style).pack(side=tk.LEFT, padx=2)
        tk.Button(button_frame, text="Save As...", command=self._on_save_as, **button_style).pack(side=tk.LEFT, padx=(2, 20))
        
        # Search field
        tk.Label(button_frame, text="Search:", bg="#2a2d33", fg="#f5f5f5", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 5))
        search_entry = tk.Entry(
            button_frame,
            textvariable=self.search_var,
            bg="#111111",
            fg="#F5F5F5",
            insertbackground="#F5F5F5",
            font=("Segoe UI", 11),
            width=48 # 20% schmaler
        )
        search_entry.pack(side=tk.LEFT, pady=8, padx=(0, 5))
        search_entry.bind("<Return>", self._find_next)
        search_entry.bind("<F3>", self._find_next)
        search_entry.bind("<FocusOut>", self._hide_suggestions)
        search_entry.bind("<Escape>", self._hide_suggestions)
        search_entry.bind("<Down>", self._focus_suggestions)

        def _clear_search():
            self.search_var.set("")
            search_entry.focus_set()

        clear_button = tk.Button(
            button_frame,
            text="Clear",
            command=_clear_search,
            **button_style
        )
        clear_button.pack(side=tk.LEFT)

        # Suggestion box (Listbox)
        self.suggestion_listbox = tk.Listbox(
            self.root,
            bg="#2a2d33",
            fg="#f5f5f5",
            selectbackground="#4a4a4a",
            selectforeground="#f5f5f5",
            highlightthickness=0,
            borderwidth=1,
            relief="solid",
            font=("Segoe UI", 10)
        )
        self.suggestion_listbox.bind("<ButtonRelease-1>", self._on_suggestion_select)
        self.suggestion_listbox.bind("<Return>", self._on_suggestion_select)
        self.suggestion_listbox.bind("<Escape>", lambda e: (self._hide_suggestions(), search_entry.focus_set()))

        tk.Button(button_frame, text="Close", command=self._on_close, **button_style).pack(side=tk.RIGHT, padx=2)
    
    def _load_file(self, path: str):
        """Load a file into the editor."""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Suppress dirty flag during load
            self.text_editor.delete("1.0", tk.END)
            self.text_editor.insert("1.0", content)
            self.text_editor.edit_reset()  # Clear undo history
            
            self.filepath = path
            self.baseline_text = content
            self.dirty = False
            
            # Update window title
            try:
                size = os.path.getsize(path)
                size_str = f"{size} bytes"
            except Exception:
                size_str = ""
            self.root.title(f"Alternative INI Editor - {path} {('(' + size_str + ')' if size_str else '')}")
            
            # Rebuild sections
            self._rebuild_sections()
            
            # Defer jump until window is fully drawn and focused
            def deferred_jump():
                if self.jump_token:
                    self._jump_to_token(self.jump_token)
                else:
                    self._jump_to_first_value()
            
            # Apply syntax highlighting AFTER jumping
            self._apply_syntax_highlighting()
            
            # Force a scroll update to fix display glitches
            self.text_editor.see("1.0")
            self.root.update_idletasks()

            # Execute the jump now that everything is ready
            self.root.after(50, deferred_jump)
            
        except Exception as e:
            messagebox.showerror("Open Failed", f"Cannot open file:\n{path}\n\n{e}")
    
    def _rebuild_sections(self):
        """Parse INI sections and populate the sections list."""
        self.sections_list.delete(0, tk.END)
        content = self.text_editor.get("1.0", tk.END)
        
        # Find all section headers [Section]
        for match in re.finditer(r'^\s*\[([^\]]+)\]', content, re.MULTILINE):
            section_name = match.group(1)
            line_num = content.count('\n', 0, match.start()) + 1
            self.sections_list.insert(tk.END, f"[{section_name}]")
            # Store line number as data (we'll use it for jumping)
            # Tkinter doesn't have item.data like Qt, so we'll store in a dict
            if not hasattr(self, '_section_lines'):
                self._section_lines = {}
            self._section_lines[self.sections_list.size() - 1] = line_num
    
    def _on_section_click(self, event):
        """Jump to selected section."""
        selection = self.sections_list.curselection()
        if not selection:
            return

        idx = selection[0]
        if hasattr(self, '_section_lines') and idx in self._section_lines:
            line_num = self._section_lines[idx]
            self.text_editor.mark_set(tk.INSERT, f"{line_num}.0")
            # Position section header at top of view instead of center
            try:
                total_lines = int(self.text_editor.index(tk.END).split('.')[0]) - 1
                if total_lines > 0:
                    # Scroll so the section line is at the top of the view
                    fraction = (line_num - 1) / float(total_lines)
                    self.text_editor.yview_moveto(fraction)
                else:
                    self.text_editor.see(f"{line_num}.0")
            except Exception:
                self.text_editor.see(f"{line_num}.0")
            self.text_editor.focus_set()
    
    def _apply_syntax_highlighting(self):
        """Apply syntax highlighting to the text editor content."""
        # Clear existing tags to prevent stacking
        self.text_editor.tag_remove("section", "1.0", tk.END)
        self.text_editor.tag_remove("comment", "1.0", tk.END)
        self.text_editor.tag_remove("param_comment", "1.0", tk.END)
        self.text_editor.tag_remove("comment_header", "1.0", tk.END)
        self.text_editor.tag_remove("key", "1.0", tk.END)
        self.text_editor.tag_remove("equals", "1.0", tk.END)

        # Configure tags
        self.text_editor.tag_configure("section", foreground="#954527", font=("Consolas", 14, "bold"))
        self.text_editor.tag_configure("param_comment", foreground="#9ca3af", font=("Consolas", 14, "italic")) # Light gray, italic
        self.text_editor.tag_configure("comment", foreground="#78771b")
        self.text_editor.tag_configure("comment_header", foreground="#38bdf8") # Light blue for header comments
        self.text_editor.tag_configure("key", foreground="#14b8a6") # Turquoise for parameter names
        self.text_editor.tag_configure("equals", foreground="#14b8a6") # Turquoise for equals sign

        content = self.text_editor.get("1.0", tk.END)
        
        # Highlight sections: [Section]
        for match in re.finditer(r'^\s*(\[.*?\])', content, re.MULTILINE):
            start, end = match.span(1)
            self.text_editor.tag_add("section", f"1.0 + {start} chars", f"1.0 + {end} chars")

        # Iterate through all lines to apply highlighting with correct priority
        for i, line in enumerate(content.splitlines()):
            line_num = i + 1
            stripped_line = line.strip()

            if stripped_line.startswith(';'):
                # Commented-out parameter: entire line is light gray
                self.text_editor.tag_add("param_comment", f"{line_num}.0", f"{line_num}.end")
            elif stripped_line.startswith('#'):
                # Normal or header comment
                if re.match(r'^\s*#\s*-+.*?-+\s*$', stripped_line):
                    self.text_editor.tag_add("comment_header", f"{line_num}.0", f"{line_num}.end")
                else:
                    self.text_editor.tag_add("comment", f"{line_num}.0", f"{line_num}.end")
            elif '=' in stripped_line and not stripped_line.startswith('['):
                # Active parameter: color the key and equals sign
                key_match = re.match(r'^\s*([^=]+)(\s*=)', line)
                if key_match:
                    key_start_col = key_match.start(1)
                    key_end_col = key_match.end(1)
                    eq_end_col = key_match.end(2)
                    self.text_editor.tag_add("key", f"{line_num}.{key_start_col}", f"{line_num}.{eq_end_col}")


    def _create_context_menu(self):
        """Create a right-click context menu for the text editor."""
        self.context_menu = tk.Menu(self.text_editor, tearoff=0, bg="#2a2d33", fg="#f5f5f5",
                                    activebackground="#4a4a4a", activeforeground="#f5f5f5",
                                    font=("Segoe UI", 10))
        
        self.context_menu.add_command(label="Undo", command=lambda: self.text_editor.edit_undo())
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Cut", command=lambda: self.text_editor.event_generate("<<Cut>>"))
        self.context_menu.add_command(label="Copy", command=lambda: self.text_editor.event_generate("<<Copy>>"))
        self.context_menu.add_command(label="Paste", command=lambda: self.text_editor.event_generate("<<Paste>>"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select All", command=lambda: self.text_editor.event_generate("<<SelectAll>>"))

        def show_menu(event):
            # Update undo/redo state before showing
            try:
                self.text_editor.edit_undo()
                self.text_editor.edit_redo()
            except tk.TclError:
                pass # No more undos
            self.context_menu.tk_popup(event.x_root, event.y_root)
        self.text_editor.bind("<Button-3>", show_menu)

    def _jump_to_first_value(self):
        """Jump to the first parameter value (after '=')."""
        content = self.text_editor.get("1.0", tk.END)
        # Find first key=value line
        match = re.search(r'^[ \t]*[^#;\[\]\s][^=\n]*=[ \t]*', content, re.MULTILINE)
        if match:
            pos = match.end()
            line = content.count('\n', 0, pos) + 1
            col = pos - content.rfind('\n', 0, pos) - 1
            self.text_editor.mark_set(tk.INSERT, f"{line}.{col}")
            self.text_editor.see(tk.INSERT)
    
    def _on_search(self, *args):
        """Handle search as user types."""
        query = self.search_var.get()
        if not query or len(query) < 2: # Start suggesting after 2 chars
            self._hide_suggestions()
            self.text_editor.tag_remove(tk.SEL, "1.0", tk.END)
            return
        
        # Find suggestions
        content = self.text_editor.get("1.0", tk.END)
        q_lower = query.lower()
        
        # Find all parameter keys that match the query
        matches = re.findall(r'^\s*([^#;=\s][^=]*?)\s*=', content, re.MULTILINE | re.IGNORECASE)
        
        self.suggestions = sorted(list(set([key.strip() for key in matches if q_lower in key.lower()])))
        
        if self.suggestions:
            self._show_suggestions()
        else:
            self._hide_suggestions()

    def _show_suggestions(self):
        if not self.suggestion_listbox: return
        
        self.suggestion_listbox.delete(0, tk.END)
        for item in self.suggestions:
            self.suggestion_listbox.insert(tk.END, item)
        
        # Position the listbox above the search entry
        search_entry = self.root.focus_get()
        if not isinstance(search_entry, tk.Entry): return
        
        x = search_entry.winfo_rootx() - self.root.winfo_rootx()
        y = search_entry.winfo_rooty() - self.root.winfo_rooty()
        
        list_height = min(10, len(self.suggestions)) * 22 # Approx height
        
        self.suggestion_listbox.place(
            x=x,
            y=y - list_height,
            width=search_entry.winfo_width(),
            height=list_height
        )

    def _hide_suggestions(self, event=None):
        if self.suggestion_listbox:
            self.suggestion_listbox.place_forget()

    def _on_suggestion_select(self, event=None):
        if not self.suggestion_listbox or not self.suggestion_listbox.curselection(): return
        
        selected_index = self.suggestion_listbox.curselection()[0]
        selected_value = self.suggestion_listbox.get(selected_index)
        self.search_var.set(selected_value)
        self._hide_suggestions()
        self._jump_to_token(selected_value)

    def _focus_suggestions(self, event=None):
        if self.suggestion_listbox and self.suggestion_listbox.winfo_viewable():
            self.suggestion_listbox.focus_set()
            self.suggestion_listbox.selection_set(0)

    def _find_next(self, event=None):
        """Find the next occurrence of the search query."""
        query = self.search_var.get()
        if not query:
            return
        
        # Start search from after the current cursor position
        start_pos = self.text_editor.index(f"{tk.INSERT}+1c")
        pos = self.text_editor.search(query, start_pos, nocase=True, stopindex=tk.END)
        if pos:
            self.text_editor.tag_remove(tk.SEL, "1.0", tk.END)
            self.text_editor.tag_add(tk.SEL, pos, f"{pos}+{len(query)}c")
            self.text_editor.mark_set(tk.INSERT, pos)
            self.text_editor.see(pos)

    def _jump_to_token(self, token: str):
        """Jump to a specific token in the file."""
        content = self.text_editor.get("1.0", tk.END)
        # Case-insensitive search
        idx = content.lower().find(token.lower())
        if idx >= 0:
            line = content.count('\n', 0, idx) + 1
            col = idx - content.rfind('\n', 0, idx) - 1
            try:
                total_lines = int(self.text_editor.index(tk.END).split('.')[0]) - 1
                if total_lines > 0:
                    # Scroll so the line is at the top of the view
                    fraction = (line - 1) / float(total_lines)
                    self.text_editor.yview_moveto(fraction)
                else:
                    self.text_editor.see(f"{line}.0") # Fallback for single-line files
            except Exception:
                self.text_editor.see(f"{line}.0") # Fallback
            
            self.text_editor.mark_set(tk.INSERT, f"{line}.{col}")
            # Select the found token for better visibility
            self.text_editor.tag_add(tk.SEL, f"{line}.{col}", f"{line}.{col + len(token)}")
    
    def _on_text_changed(self, event=None):
        """Handle text changes."""
        if self.text_editor.edit_modified():
            current_text = self.text_editor.get("1.0", tk.END)
            self.dirty = (current_text != self.baseline_text + '\n')  # Tkinter adds newline
            self._rebuild_sections()
            self.text_editor.edit_modified(False)
    
    def _on_open(self):
        """Open file dialog."""
        initial_dir = os.path.dirname(self.filepath) if self.filepath else ""
        path = filedialog.askopenfilename(
            title="Open INI",
            initialdir=initial_dir,
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")]
        )
        if path:
            self._load_file(path)
    
    def _on_save(self) -> bool:
        """Save the current file."""
        if not self.filepath:
            return self._on_save_as()

        try:
            content = self.text_editor.get("1.0", tk.END)
            # Remove the extra newline that Tkinter adds
            if content.endswith('\n'):
                content = content[:-1]

            with open(self.filepath, "w", encoding="utf-8") as f:
                f.write(content)

            self.baseline_text = content
            self.dirty = False
            self.text_editor.edit_modified(False)

            # Publish events to notify other UIs that work.ini has changed
            try:
                if _event_bus is not None:
                    _event_bus.publish("work_ini_changed")
                    # Also publish reset event to force full rebuild in all tabs
                    _event_bus.publish("work_ini_reset")
            except Exception:
                pass

            return True
        except Exception as e:
            messagebox.showerror("Save Failed", f"Cannot write file:\n{self.filepath}\n\n{e}")
            return False
    
    def _on_save_as(self) -> bool:
        """Save as dialog."""
        path = filedialog.asksaveasfilename(
            title="Save INI As",
            initialfile=os.path.basename(self.filepath) if self.filepath else "work.ini",
            defaultextension=".ini",
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")]
        )
        if path:
            self.filepath = path
            return self._on_save()
        return False
    
    def _on_close(self):
        """Handle window close."""
        if self.dirty:
            response = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                icon=messagebox.WARNING
            )
            if response is None:  # Cancel
                return
            elif response:  # Yes - Save
                if not self._on_save():
                    return
        
        self.root.destroy()

    def _find_next_value_line(self, start_line: int, direction: int) -> int | None:
        """Find the next valid parameter line, skipping blanks and comments."""
        total_lines = int(self.text_editor.index(f"end-1c").split('.')[0])
        current_line = start_line
        
        for _ in range(total_lines + 1):
            current_line += direction
            if direction == 1 and current_line > total_lines:
                current_line = 1  # Wrap to top
            elif direction == -1 and current_line < 1:
                current_line = total_lines  # Wrap to bottom

            line_content = self.text_editor.get(f"{current_line}.0", f"{current_line}.end").strip()
            
            if not line_content or line_content.startswith(('#', ';', '[')):
                continue
            
            if '=' in line_content:
                return current_line
        
        return None

    def _navigate_value(self, direction: int) -> None:
        """Core logic for Tab and Shift+Tab navigation."""
        try:
            start_line = int(self.text_editor.index(tk.INSERT).split('.')[0])
        except (ValueError, IndexError):
            start_line = 1

        next_line_num = self._find_next_value_line(start_line, direction)

        if next_line_num is not None:
            line_content = self.text_editor.get(f"{next_line_num}.0", f"{next_line_num}.end")
            try:
                eq_pos = line_content.index('=')
                value_start_col = eq_pos + 1
                
                value_start_idx = f"{next_line_num}.{value_start_col}"
                value_end_idx = f"{next_line_num}.end"

                self.text_editor.mark_set(tk.INSERT, value_end_idx)
                self.text_editor.see(tk.INSERT)
            except ValueError:
                pass # Should not happen due to check in _find_next_value_line

    def _on_tab_forward(self, event=None) -> str:
        self._navigate_value(1)
        return "break"

    def _on_tab_backward(self, event=None) -> str:
        self._navigate_value(-1)
        return "break"


def open_ini_editor(path: str | None = None, jump: str | None = None):
    """Open the INI editor window, trying to find a parent Tk instance."""
    parent = None
    # Try to find an existing Tk root to use as parent
    if tk._default_root:
        parent = tk._default_root
    
    app = IniEditorWindow(parent, path, jump)
    app.wait_window()


def main():
    """Main entry point for standalone execution."""
    # Parse args: optional --jump TOKEN then optional path
    args = sys.argv[1:]
    jump = None
    path = None
    
    if "--jump" in args:
        try:
            idx = args.index("--jump")
            jump = args[idx + 1] if idx + 1 < len(args) else None
            del args[idx:idx + 2]
        except Exception:
            pass
    
    if args:
        path = args[0]
    
    # Fallback to default work.ini if no valid path
    if not path or not os.path.isfile(path):
        try:
            path = default_work_ini_path()
        except Exception:
            pass
    
    open_ini_editor(path, jump)


if __name__ == "__main__":
    main()
