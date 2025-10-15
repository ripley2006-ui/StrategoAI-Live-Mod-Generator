"""Footer button actions and state transitions.

This module encapsulates footer-specific actions and registers them with
the global action registry in main_actions. It represents explicit program
states, e.g. STATE 1 (not installed) and STATE 2 (installed).
"""

from __future__ import annotations

from pathlib import Path
import shutil
import ctypes
from typing import Optional
import tkinter as tk
import os
import subprocess
import re
from datetime import datetime

from .main_actions import (
    ActionExecutionError,
    ButtonState,
    ActionContext,
    register_action,
)
from . import main_actions as _ma
from system.gui_utils.unified_dialogs import show_info, ask_confirm_destructive
from system.programs.Live_Mod.Global_Mission_Settings.config_gms.gms_actions import (
    apply_user_info_to_work_from_mirror,
    delete_user_info_mirror,
    pause_live_sync,
    resume_live_sync,
    resume_live_sync_after,
)


# ---------------------------- Dark Dialog Helpers ----------------------------



# ---------------------------------------------------------------------------
# State model (lightweight)
# ---------------------------------------------------------------------------
# STATE 1: Live Mod NOT installed
# STATE 2: Live Mod installed
#
# We infer state from filesystem via _ma._is_live_mod_installed(). No separate
# global state storage is required. Other states (3..6) can be added later and
# also derive from context or persisted flags as needed.


def install_live_mod(context: ActionContext) -> Optional[ButtonState]:
    """Footer Button 1 action: transition to STATE 2 (installed).

    Copies all folders and files from the project's template install directory
    into the ReadyOrNot config directory.
    """
    project_root = _ma.get_application_base_path()
    source_dir = (project_root / "system/templates/mod_install").resolve()
    dest_dir = _ma._install_base_path()

    if not source_dir.exists() or not source_dir.is_dir():
        raise ActionExecutionError(f"Source directory not found: {source_dir}")

    # Check if any of the source items already exist at the destination
    source_items = list(source_dir.iterdir())
    if not source_items:
        raise ActionExecutionError(f"Source directory is empty: {source_dir}")

    already_installed = any((dest_dir / item.name).exists() for item in source_items)
    if already_installed:
        return ButtonState(text="Mod installed", style="green", enabled=False, message="Bereits installiert.")

    # Pause live sync during install to avoid race with copy
    try:
        pause_live_sync()
    except Exception:
        pass  # Ignore if it fails

    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in source_items:
        dest_path = dest_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest_path, dirs_exist_ok=True)
        elif item.is_file():
            shutil.copy(item, dest_path)

    # Apply preserved user info from mirror into freshly installed work.ini
    try:
        apply_user_info_to_work_from_mirror()
    except Exception:
        pass
    # Resume after a short delay and trigger a sync once complete
    try:
        resume_live_sync_after(3.0, trigger_sync=True)
    except Exception:
        pass

    # Reflect STATE 2 (installed) and lock the button
    return ButtonState(text="Mod installed", style="green", enabled=False, message="Live Mod installiert.")


# -------- Activation/Deactivation (STATE 3/4) --------

def _paths():
    base = _ma._install_base_path()
    return (base / "Difficulties", base / "Difficulties.disabled")


def _is_active() -> bool:
    active, _disabled = _paths()
    return active.exists()


def _is_deactivated() -> bool:
    _active, disabled = _paths()
    return disabled.exists()


def toggle_live_mod_activation(_context: ActionContext) -> Optional[ButtonState]:
    """Footer Button 2 action: STATE 3/4 toggle.

    - If active → deactivate (STATE 3): rename to Difficulties.disabled
    - If deactivated → activate (STATE 4): rename back to Difficulties
    - If not installed → no-op with disabled state
    """
    base = _ma._install_base_path() / "Difficulties"  # Source for active files
    off_dir = _ma._install_base_path() / "StrategoAI_Live_Mod" / "Mods_Off"  # New destination for deactivated files
    act_files = [base / "CasualDifficulty.ini", base / "HardDifficulty.ini", base / "StandardDifficulty.ini"]
    off_files = [off_dir / "CasualDifficulty.ini", off_dir / "HardDifficulty.ini", off_dir / "StandardDifficulty.ini"]
    # Always pause LiveSync around activation state changes to avoid races
    try:
        pause_live_sync()
    except Exception:
        pass
    # Decide current state by presence of files
    act_present = sum(1 for p in act_files if p.exists())
    off_present = sum(1 for p in off_files if p.exists())
    # Deactivate: move files to Mods_Off and keep paused
    if act_present >= 1:
        try:
            off_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        for src, dst in zip(act_files, off_files):
            if src.exists():
                try:
                    shutil.move(str(src), str(dst))
                except Exception:
                    pass
        return ButtonState(text="Activate Live Mod", style="orange", enabled=True, message="Live Mod deaktiviert.")
    # Activate: move back and resume after delay
    if off_present >= 1:
        for src, dst in zip(off_files, act_files):
            if src.exists():
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                except Exception:
                    pass
        try:
            resume_live_sync_after(3.0, trigger_sync=True)
        except Exception:
            pass
        return ButtonState(text="Deactivate Live Mod", style="orange", enabled=True, message="Live Mod aktiviert.")
    return ButtonState(text="Deactivate Live Mod", style="gray", enabled=False)


def _live_mod_activation_status(_context: ActionContext) -> Optional[ButtonState]:
    # STATE presentation for Button 2 based on file locations
    base = _ma._install_base_path() / "Difficulties"  # Source for active files
    off = _ma._install_base_path() / "StrategoAI_Live_Mod" / "Mods_Off"  # New destination for deactivated files
    act_files = [base / "CasualDifficulty.ini", base / "HardDifficulty.ini", base / "StandardDifficulty.ini"]
    off_files = [off / "CasualDifficulty.ini", off / "HardDifficulty.ini", off / "StandardDifficulty.ini"]
    try:
        act_present = any(p.exists() for p in act_files)
        off_present = any(p.exists() for p in off_files)
        if act_present:
            return ButtonState(text="Deactivate Live Mod", style="orange", enabled=True)
        if off_present:
            return ButtonState(text="Activate Live Mod", style="orange", enabled=True)
    except Exception:
        pass
    return ButtonState(text="Deactivate Live Mod", style="gray", enabled=False)


# -------- Uninstall (STATE 5 back to 1) --------

def uninstall_live_mod(_context: ActionContext) -> Optional[ButtonState]:
    """Footer Button 3 action: transition to STATE 1 by removing both variants.

    Shows a confirmation dialog (Yes / Cancel) before uninstalling.
    """
    # Dark themed confirmation prompt
    confirmed = ask_confirm_destructive(
        "Do you really want to uninstall the Live Mod?",
        title="Uninstall Live Mod",
        action_text="Uninstall",
        cancel_text="Cancel"
    )
    if not confirmed:
        # No changes; reflect current uninstall button state
        return _live_mod_uninstall_status(_context)
    
    project_root = _ma.get_application_base_path()
    source_dir = (project_root / "system/templates/mod_install").resolve()
    dest_dir = _ma._install_base_path()

    # Pause live sync before removing folders to avoid races
    try:
        pause_live_sync()
    except Exception:
        pass

    # Dynamically determine items to uninstall based on the install template
    if source_dir.exists():
        source_items = list(source_dir.iterdir())
        for item in source_items:
            dest_path = dest_dir / item.name
            if dest_path.exists():
                try:
                    if dest_path.is_dir():
                        shutil.rmtree(dest_path)
                    else:
                        dest_path.unlink()
                except Exception:
                    # If direct deletion fails, try to send to recycle bin as a fallback
                    try:
                        _send_to_recycle_bin(dest_path)
                    except Exception:
                        pass  # Ignore if both fail

    # Also clean up the legacy .disabled folder if it exists
    disabled_path = _ma._install_base_path() / "Difficulties.disabled"
    if disabled_path.exists():
        try:
            shutil.rmtree(disabled_path)
        except Exception:
            try:
                _send_to_recycle_bin(disabled_path)
            except Exception:
                pass

    # Remove mirror so UI starts clean next time
    try:
        delete_user_info_mirror()
    except Exception:
        pass

    # Resume without forcing a sync (no work.ini guaranteed)
    try:
        resume_live_sync(trigger_sync=False)
    except Exception:
        pass

    return ButtonState(text="Uninstall Live Mod", style="gray", enabled=False, message="Live Mod entfernt.")


def _send_to_recycle_bin(path: Path) -> None:
    """Send a file or directory to the Recycle Bin on Windows.

    Uses SHFileOperationW with FOF_ALLOWUNDO. Silently no-ops on non-Windows.
    """
    if os.name != 'nt':
        # Non-Windows: skip (caller will fallback delete)
        raise RuntimeError("Recycle Bin not supported on this OS")

    # Prepare double-null-terminated string as required by SHFileOperation
    p = str(path.resolve()) + '\0'
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ('hwnd', wintypes.HWND),
            ('wFunc', ctypes.c_uint),
            ('pFrom', wintypes.LPCWSTR),
            ('pTo', wintypes.LPCWSTR),
            ('fFlags', ctypes.c_uint16),
            ('fAnyOperationsAborted', wintypes.BOOL),
            ('hNameMappings', ctypes.c_void_p),
            ('lpszProgressTitle', wintypes.LPCWSTR),
        ]

    SHFileOperationW = ctypes.windll.shell32.SHFileOperationW
    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004

    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = p + '\0'  # double-null terminated
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    op.fAnyOperationsAborted = False
    op.hNameMappings = None
    op.lpszProgressTitle = None
    res = SHFileOperationW(ctypes.byref(op))
    if res != 0:
        raise OSError(f"SHFileOperation failed with code {res}")


def _live_mod_uninstall_status(_context: ActionContext) -> Optional[ButtonState]:
    base = _ma._install_base_path() / "Difficulties"
    off = base / "Mods_Off" / "Live Mod"
    act_files = [base / "CasualDifficulty.ini", base / "HardDifficulty.ini", base / "StandardDifficulty.ini"]
    off_files = [off / "CasualDifficulty.ini", off / "HardDifficulty.ini", off / "StandardDifficulty.ini"]
    try:
        if base.exists() and (any(p.exists() for p in act_files) or any(p.exists() for p in off_files)):
            return ButtonState(text="Uninstall Live Mod", style="red", enabled=True)
    except Exception:
        pass
    return ButtonState(text="Uninstall Live Mod", style="gray", enabled=False)


# Register footer actions
register_action(
    "install_live_mod",
    run=install_live_mod,
    state=_ma._live_mod_status,  # STATE 1 vs STATE 2 resolved by filesystem
    description="Installiert den Live Mod (STATE 2).",
)

register_action(
    "toggle_live_mod_activation",
    run=toggle_live_mod_activation,
    state=_live_mod_activation_status,
    description="Aktiviert/Deaktiviert den Live Mod (STATE 3/4).",
)

register_action(
    "uninstall_live_mod",
    run=uninstall_live_mod,
    state=_live_mod_uninstall_status,
    description="Deinstalliert den Live Mod (zurück zu STATE 1).",
)


__all__ = [
    "install_live_mod",
    "toggle_live_mod_activation",
    "uninstall_live_mod",
    "open_live_mod_folder",
    "add_mod_to_templates",
]


# -------- Open my Live Mods Folder (Footer 6) --------

def _open_live_mod_folder_status(_context: ActionContext) -> Optional[ButtonState]:
    # Dieser Button ist immer aktiv. Die Ordnererstellung erfolgt nur bei Klick.
    return ButtonState(text="Open my Live Mods Folder", style="blue", enabled=True)


def open_live_mod_folder(context: ActionContext) -> Optional[ButtonState]:
    """Öffnet den benutzerspezifischen Ordner my_AImod_files."""
    folder = _ma.get_user_mod_files_path()
    
    # Ordner erstellen, falls er nicht existiert
    folder.mkdir(parents=True, exist_ok=True)
    
    try:
        path_str = str(folder)
        if hasattr(os, "startfile"):
            os.startfile(path_str)
        else:
            subprocess.Popen(["explorer", path_str])
    except Exception:
        return ButtonState(text="Open my Live Mods Folder", style="blue", enabled=True, tooltip="Could not open Explorer.")
    
    return ButtonState(text="Open my Live Mods Folder", style="blue", enabled=True)


register_action(
    "open_live_mod_folder",
    run=open_live_mod_folder,
    state=_open_live_mod_folder_status,
    description="Öffnet den my_AImod_files Ordner im Programmverzeichnis.",
)


# -------- Snapshot (Footer 4) --------

SNAPSHOT_DIRNAME = "MySnapshots"


def _read_modname_from_work(work_ini: Path) -> str:
    """Read modname from work.ini using DifficultyNameKey (new format).
    
    The new format stores the modname in DifficultyNameKey in the [Info] section.
    If not found, fallback to legacy Modname= for backward compatibility.
    """
    try:
        text = work_ini.read_text(encoding="utf-8", errors="ignore")
        # Try new format first: DifficultyNameKey in [Info] section
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("DifficultyNameKey="):
                value = stripped.split("=", 1)[1].strip()
                # Remove version suffix if present (format: "Modname Version")
                # Split by space and take first part
                parts = value.split()
                if parts:
                    return parts[0] or "Live Mod"
        # Fallback: try legacy Modname= format
        for line in text.splitlines():
            if line.strip().startswith("Modname="):
                return line.split("=", 1)[1].strip() or "Live Mod"
    except Exception:
        pass
    return "Live Mod"


def _snapshot_dir(context: ActionContext) -> Path:
    """Gibt das Snapshot-Verzeichnis im benutzerspezifischen Ordner zurück."""
    return _ma.get_user_mod_files_path() / SNAPSHOT_DIRNAME


def _snapshot_status(context: ActionContext) -> Optional[ButtonState]:
    # Enabled only when active INIs and work.ini present
    base, _ = _paths()
    # Use the centralized helper to get the correct work.ini path
    work = _ma._install_base_path() / "StrategoAI_Live_Mod" / "Work" / "work.ini"
    act_files = [base / "CasualDifficulty.ini", base / "HardDifficulty.ini", base / "StandardDifficulty.ini"]
    ctrl = bool((context or {}).get("ctrl", False))
    hover = bool((context or {}).get("hover", False))
    if all(p.exists() for p in act_files) and work.exists():
        if ctrl and hover:
            return ButtonState(text="Load Snapshot", style="green", enabled=True)
        return ButtonState(text="Snapshot", style="purple", enabled=True)
    return ButtonState(text="Snapshot", style="gray", enabled=False)


_SNAPSHOT_RE = re.compile(r"^(?P<base>.+?)\s*-\s*(?P<idx>\d{3})\s*-\s*(?P<ts>\d{8}_\d{6})\.ini$", re.I)


def _parse_snapshot(name: str) -> tuple[str, int, datetime] | None:
    m = _SNAPSHOT_RE.match(name)
    if not m:
        return None
    base = m.group("base").strip()
    try:
        idx = int(m.group("idx"))
        ts = datetime.strptime(m.group("ts"), "%Y%m%d_%H%M%S")
    except Exception:
        return None
    return (base, idx, ts)


def _list_snapshots_sorted(folder: Path) -> list[Path]:
    # Sort by timestamp in filename (not mtime), newest first
    items = []
    for p in folder.glob("*.ini"):
        meta = _parse_snapshot(p.name)
        if meta is None:
            continue
        items.append((p, meta[2]))
    items.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in items]


def _next_snapshot_name(base_name: str, folder: Path) -> str:
    # Determine next index based on existing files with same base (by filename), using parsed metadata
    max_idx = 0
    if folder.exists():
        for f in folder.glob("*.ini"):
            meta = _parse_snapshot(f.name)
            if meta and meta[0].lower() == base_name.lower():
                if meta[1] > max_idx:
                    max_idx = meta[1]
    next_idx = max_idx + 1
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name} - {next_idx:03d} - {ts}.ini"


def _select_snapshot_dialog(folder: Path, context: ActionContext) -> Optional[Path]:
    snapshots = _list_snapshots_sorted(folder)
    if not snapshots:
        show_info("No snapshots found.", title="Load Snapshot")
        return None
    # Simple picker dialog
    win = tk.Toplevel()
    win.title("Load Snapshot")
    width, height = 420, 280
    # Position directly above the footer button if coordinates are provided
    bx = int(context.get("button_abs_x", 100))
    by = int(context.get("button_abs_y", 100))
    y_above = max(0, by - height - 8)
    win.geometry(f"{width}x{height}+{bx}+{y_above}")
    win.transient()
    win.grab_set()
    try:
        win.configure(bg="#1d1f23")
    except Exception:
        pass
    tk.Label(win, text="Select a snapshot to load:", bg="#1d1f23", fg="#f8fafc", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=8, pady=(8, 4))
    lb = tk.Listbox(win, selectmode=tk.SINGLE,
                    bg="#2b2f37", fg="#f8fafc",
                    selectbackground="#1d4ed8", selectforeground="#f8fafc",
                    highlightthickness=0, borderwidth=0,
                    font=("Segoe UI", 10))
    for f in snapshots:
        lb.insert(tk.END, f.name)
    lb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    selected: dict = {"path": None}

    def _on_load():
        sel = lb.curselection()
        if not sel:
            return
        selected["path"] = snapshots[sel[0]]
        win.destroy()

    def _on_cancel():
        selected["path"] = None
        win.destroy()

    def _refresh_list() -> None:
        nonlocal snapshots
        snapshots = _list_snapshots_sorted(folder)
        lb.delete(0, tk.END)
        for f in snapshots:
            lb.insert(tk.END, f.name)

    def _on_delete_keep3():
        nonlocal snapshots
        current = _list_snapshots_sorted(folder)
        if len(current) <= 3:
            show_info("Nothing to delete. Fewer than 4 snapshots exist.", title="Delete Snapshots")
            return
        # Keep newest three, delete the rest
        keep = current[:3]
        deleted = 0
        for f in current[3:]:
            try:
                f.unlink(missing_ok=True)
                deleted += 1
            except Exception:
                pass
        # Renumber the remaining three as 001, 002, 003 (oldest=001, newest=003)
        for i, f in enumerate(reversed(keep), start=1):
            meta = _parse_snapshot(f.name)
            if not meta:
                continue
            base, _old_idx, ts = meta
            new_name = f"{base} - {i:03d} - {ts.strftime('%Y%m%d_%H%M%S')}.ini"
            if f.name != new_name:
                try:
                    f.rename(f.with_name(new_name))
                except Exception:
                    pass
        _refresh_list()
        show_info(f"Deleted {deleted} snapshot(s). Kept last 3.", title="Delete Snapshots")

    btn_frame = tk.Frame(win, bg="#1d1f23")
    btn_frame.pack(fill=tk.X, padx=8, pady=(4, 8))
    # Place delete button on the left, cancel/load on the right
    tk.Button(btn_frame, text="Delete snapshots - keep last 3", command=_on_delete_keep3,
              bg="#4b5563", fg="#f8fafc", activebackground="#374151", activeforeground="#f8fafc", relief=tk.FLAT, borderwidth=0).pack(side=tk.LEFT)
    tk.Button(btn_frame, text="Load", command=_on_load,
              bg="#1d4ed8", fg="#f8fafc", activebackground="#1e3a8a", activeforeground="#f8fafc", relief=tk.FLAT, borderwidth=0).pack(side=tk.RIGHT, padx=4)
    tk.Button(btn_frame, text="Cancel", command=_on_cancel,
              bg="#4b5563", fg="#f8fafc", activebackground="#374151", activeforeground="#f8fafc", relief=tk.FLAT, borderwidth=0).pack(side=tk.RIGHT)

    win.wait_window()
    return selected["path"]


def snapshot_live_mod(context: ActionContext) -> Optional[ButtonState]:
    # ctrl-triggered load?
    ctrl = bool(context.get("ctrl", False))
    active, _ = _paths() # This is the Difficulties folder
    work = _ma._install_base_path() / "StrategoAI_Live_Mod" / "Work" / "work.ini"
    if not (active.exists() and work.exists()):
        return _snapshot_status(context)

    folder = _snapshot_dir(context)
    folder.mkdir(parents=True, exist_ok=True)

    if ctrl:
        chosen = _select_snapshot_dialog(folder, context)
        if not chosen:
            return _snapshot_status(context)
        # Confirm overwrite after selection
        if not ask_confirm_destructive(
            "Do you really want to overwrite the current Mod parameters?",
            title="Load Snapshot",
            action_text="Overwrite",
            cancel_text="Cancel"
        ):
            return _snapshot_status(context)
        shutil.copy2(chosen, work)
        return ButtonState(text="Snapshot loaded", style="purple", enabled=True, message=f"Loaded: {chosen.name}")

    # Create snapshot
    base_name = _read_modname_from_work(work)
    filename = _next_snapshot_name(base_name, folder)
    shutil.copy2(work, folder / filename)
    return ButtonState(text="Snapshot saved", style="purple", enabled=True, message=f"Saved: {filename}")


register_action(
    "snapshot_live_mod",
    run=snapshot_live_mod,
    state=_snapshot_status,
    description="Speichert (oder lädt mit Ctrl) einen Snapshot der work.ini.",
)


# -------- Add Mod to Templates (Footer 5) --------

def _add_to_templates_status(context: ActionContext) -> Optional[ButtonState]:
    active, _ = _paths()
    # Use the centralized helper to get the correct work.ini path
    work = _ma._install_base_path() / "StrategoAI_Live_Mod" / "Work" / "work.ini"
    act_files = [active / "CasualDifficulty.ini", active / "HardDifficulty.ini", active / "StandardDifficulty.ini"]
    ctrl = bool((context or {}).get("ctrl", False))
    hover = bool((context or {}).get("hover", False))
    if ctrl and hover:
        # Allow opening the template folder regardless of install state
        return ButtonState(text="Open Template Folder", style="blue", enabled=True)
    if all(p.exists() for p in act_files) and work.exists():
        return ButtonState(text="Add Mod to Templates", style="purple", enabled=True)
    return ButtonState(text="Add Mod to Templates", style="gray", enabled=False)


def add_mod_to_templates(context: ActionContext) -> Optional[ButtonState]:
    dest_dir = (_ma.get_user_mod_files_path() / "MyTemplates").resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Ctrl-click path: open folder
    if bool(context.get("ctrl", False)):
        try:
            path_str = str(dest_dir)
            if hasattr(os, "startfile"):
                os.startfile(path_str)
            else:
                subprocess.Popen(["explorer", path_str])
        except Exception:
            return ButtonState(text="Open Template Folder", style="blue", enabled=True, tooltip="Could not open Explorer.")
        return ButtonState(text="Open Template Folder", style="blue", enabled=True)

    # Default path: export the FULL active difficulty file as template.
    # Reason: work.ini often contains only [Global] + GameplayTags values.
    # The active files under Difficulties have the merged, complete content.
    active, _ = _paths()
    work = _ma._install_base_path() / "StrategoAI_Live_Mod" / "Work" / "work.ini"
    act_files = [active / "CasualDifficulty.ini", active / "HardDifficulty.ini", active / "StandardDifficulty.ini"]
    if not (all(p.exists() for p in act_files) and work.exists()):
        return _add_to_templates_status(context)

    # Resolve current difficulty to pick correct source file
    try:
        from system.programs.Live_Mod.Global_Mission_Settings.config_gms.gms_actions import get_current_difficulty_from_work
        current_diff = get_current_difficulty_from_work() or "Standard"
    except Exception:
        current_diff = "Standard"
    src_map = {
        "Casual": active / "CasualDifficulty.ini",
        "Hard": active / "HardDifficulty.ini",
        "Standard": active / "StandardDifficulty.ini",
    }
    src_file = src_map.get(current_diff.strip().title(), active / "StandardDifficulty.ini")

    modname = _read_modname_from_work(work)
    dest_path = dest_dir / f"{modname}.ini"
    if dest_path.exists():
        if not ask_confirm_destructive(
            f"Template '{dest_path.name}' already exists. Overwrite?",
            title="Overwrite Template",
            action_text="Overwrite",
            cancel_text="Cancel"
        ):
            return _add_to_templates_status(context)

    # Copy work.ini exactly as template (per request)
    shutil.copy2(work, dest_path)

    _show_toast_above_button(context, f"Saved template: {dest_path.name}")
    return ButtonState(text="Added to Templates", style="purple", enabled=True, message=f"Saved: {dest_path.name}")


def _show_toast_above_button(context: ActionContext, text: str) -> None:
    try:
        bx = int(context.get("button_abs_x", 100))
        by = int(context.get("button_abs_y", 100))
        width, height = 260, 36
        y_above = max(0, by - height - 8)
        win = tk.Toplevel()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{width}x{height}+{bx}+{y_above}")
        frame = tk.Frame(win, bg="#222", bd=1, relief="solid")
        frame.pack(fill=tk.BOTH, expand=True)
        lbl = tk.Label(frame, text=text, bg="#222", fg="#fff")
        lbl.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        win.after(1600, win.destroy)
    except Exception:
        # Fallback silently if toast fails
        pass


register_action(
    "add_mod_to_templates",
    run=add_mod_to_templates,
    state=_add_to_templates_status,
    description="Kopiert work.ini in my_AImod_files/MyTemplates (Name aus Modname).",
)
