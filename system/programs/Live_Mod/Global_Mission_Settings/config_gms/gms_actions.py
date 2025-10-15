"""Action handlers for the Global Mission Settings GUI.

Currently implements the initial "user" block handling that writes the
fields Modname, Version, Date, Notes, Template into:

- The Ready or Not difficulty work.ini in the user's LOCALAPPDATA folder
- The local mirror file user_mission_info.json (INI-like key=value store)

Other actions remain placeholders until specified.
"""

from __future__ import annotations

from typing import Callable, Iterable
from pathlib import Path
import os
import re
import threading
from collections import deque
from time import monotonic
import sys
import subprocess
import shutil
from typing import Sequence
from typing import Tuple

# Lightweight in-process event bus for notifying other UIs
try:
    from system.gui_utils import event_bus as _event_bus  # type: ignore
except Exception:  # pragma: no cover
    _event_bus = None  # type: ignore

def _publish_work_ini_changed() -> None:
    try:
        if _event_bus is not None:
            _event_bus.publish("work_ini_changed")
    except Exception:
        pass


class ActionNotImplementedError(NotImplementedError):
    """Raised when an action has not been implemented yet."""


def _raise_placeholder(name: str) -> None:
    raise ActionNotImplementedError(
        f"The '{name}' action has not been implemented yet."
    )


def _local_appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    # Fallback to user profile if LOCALAPPDATA missing
    return Path.home() / "AppData" / "Local"


def _work_ini_path() -> Path:
    return _local_appdata() / "ReadyOrNot" / "Saved" / "Config" / "StrategoAI_Live_Mod" / "Work" / "work.ini"


def _user_info_path() -> Path:
    """Return path to the persistent mirror file (user_mission_info.json)."""
    # Verwendet den zentralen, benutzerspezifischen Pfad in AppData.
    from system.config_main.main_actions import get_user_mod_files_path
    path = get_user_mod_files_path() / "user_mission_info.json"
    return path


def mirror_exists() -> bool:
    try:
        return _user_info_path().exists()
    except Exception:
        return False


def _active_difficulties_path() -> Path:
    return _local_appdata() / "ReadyOrNot" / "Saved" / "Config" / "Difficulties"


# Legacy user keys that are NO LONGER USED
# These keys have been replaced by the new mapping system:
# - DifficultyNameKey (replaces Modname)
# - DifficultySubtextKey (includes Notes)
# - DifficultyFlavorKey (includes Date)
# - DifficultyGameplayTag (generated code)
# DO NOT write these keys to work.ini anymore!
_LEGACY_USER_KEYS = ("Modname", "Version", "Date", "Notes", "Template")
_UI_MIRROR_KEYS = ("UI_Modname", "UI_Version", "UI_Date", "UI_Notes", "UI_Template")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically when possible
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Write content as-is (preserve line-endings/layout)
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# Removed legacy functions that wrote Modname/Version/Date/Notes/Template
# These keys are no longer used. The new system uses:
# - DifficultyNameKey (in [Info])
# - DifficultySubtextKey (in [Info]) 
# - DifficultyFlavorKey (in [Info])
# - DifficultyGameplayTag (in [Info])
# - UI_Modname, UI_Version, UI_Date, UI_Notes (in mirror file only)


def _set_or_append_kv_block(existing: str, *, keys: Iterable[str], values: dict[str, str]) -> str:
    """Replace existing key lines preserving exact formatting; never alter layout.

    - Preserves unrelated content, spacing, and line endings.
    - For matches, only the value part after '=' is replaced; prefix/spaces/EOL bleiben erhalten.
    - IMPORTANT: If a key is not found, we DO NOT append it here to avoid layout drift.
      Seeding from Mod_Base.ini must ensure the keys exist.
    - Parameter keys (not user info) preserve their original formatting including whitespace.
    """
    # Detect existing newline style
    newline = "\r\n" if "\r\n" in existing else "\n"
    # Keepends so we preserve per-line line endings
    lines = existing.splitlines(keepends=True)
    seen: set[str] = set()
    key_res: dict[str, re.Pattern[str]] = {}
    for k in keys:
        # Capture: (prefix)(key)(sep)(value)(eol)
        key_res[k] = re.compile(
            rf"^(?P<prefix>\s*)(?P<key>{re.escape(k)})"
            rf"(?P<sep>\s*=\s*)(?P<val>.*?)(?P<eol>(\r\n|\n|\r))$",
            re.IGNORECASE,
        )

    for i, line in enumerate(lines):
        for k, rx in key_res.items():
            m = rx.match(line)
            if m:
                new_val = values.get(k, "")
                # Preserve existing formatting (prefix, separator, EOL)
                prefix = m.group('prefix')
                separator = m.group('sep')
                lines[i] = f"{prefix}{m.group('key')}{separator}{new_val}{m.group('eol')}"
                seen.add(k)
                break

    # Intentionally do not append missing keys here.
    return "".join(lines)


def _write_mirror_exact(values: dict[str, str]) -> None:
    """Deprecated: legacy exact mirror of user keys removed.

    Kept for backward compatibility but now no-ops to avoid writing legacy keys.
    """
    return


def _write_user_info_to_files(values: dict[str, str]) -> None:
    """Deprecated: do not write legacy user keys to files anymore."""
    return


def _template_path() -> Path:
    """Return path to the base template for seeding work.ini."""
    # Uses the application base path to be portable in frozen builds.
    try:
        from system.config_main.main_actions import get_application_base_path
        base = get_application_base_path()
    except Exception:
        # Fallback for development environments where the import might fail
        # or when get_application_base_path is not available.
        base = Path(__file__).resolve().parents[5] # Assumes a fixed structure
    return base / "system" / "templates" / "build" / "Mod_Base.ini"


def _seed_work_ini_from_template_if_missing() -> None:
    work_path = _work_ini_path()
    if work_path.exists():
        return
    tpl = _read_text(_template_path())
    lines: list[str] = []
    for raw in tpl.splitlines():
        if raw.strip().startswith("#;Global /end"):
            break
        if raw.strip() == "#;empty_line":
            lines.append("")
            continue
        if raw.strip().startswith("#;"):
            # programming markers are not emitted into work.ini
            continue
        lines.append(raw)
    content = "\n".join(lines) + "\n"
    _write_text(work_path, content)


def _write_user_info_to_work(values: dict[str, str]) -> None:
    """Deprecated: legacy [Global] user keys are no longer written."""
    return


# Legacy function removed - do not read Modname/Version/Date/Notes from work.ini
# These keys no longer exist in work.ini!
# Use get_user_ui_info_from_mirror() instead to read UI_* keys from mirror


def read_ini_values(keys: Sequence[str]) -> dict[str, str]:
    """Read arbitrary key=value pairs from work.ini without changing layout.

    Returns a dict for the requested keys. Missing keys map to "".
    """
    text = _read_text(_work_ini_path())
    result: dict[str, str] = {k: "" for k in keys}
    if not text:
        return result
    lines = text.splitlines()
    patterns: dict[str, re.Pattern[str]] = {
        k: re.compile(rf"^(?i:{re.escape(k)})\s*=\s*(.*)$") for k in keys
    }
    for line in lines:
        for k, pat in patterns.items():
            m = pat.match(line)
            if m:
                result[k] = m.group(1)
    return result


def write_ini_values(values: dict[str, str]) -> None:
    """Write arbitrary key=value pairs into work.ini preserving layout.

    Only replaces the value part after '=' for keys that already exist.
    Does not append missing keys to avoid layout drift.
    """
    if not values:
        return
    work_path = _work_ini_path()
    _seed_work_ini_from_template_if_missing()
    current = _read_text(work_path)
    updated = _set_or_append_kv_block(current, keys=values.keys(), values=values)
    _write_text(work_path, updated)
    _publish_work_ini_changed()


# ---------------------------------------------------------------------------
# Multiplayer settings helpers (comment toggle via leading ';')
# ---------------------------------------------------------------------------

# Match an INI key line with optional leading ';' (comment) and optional EOL
_KEY_LINE_RX = re.compile(
    r"^(?P<prefix>\s*;?\s*)(?P<key>[^#;=\s][^=\s]*?)\s*=\s*(?P<val>.*?)(?P<eol>(\r\n|\n|\r))?$"
)


def read_keys_with_comment_state(keys: Sequence[str]) -> dict[str, Tuple[bool, str]]:
    """Return {key: (enabled, value)} for given keys from work.ini.

    enabled = True if line is not commented (no leading ';' before key), False otherwise.
    """
    text = _read_text(_work_ini_path())
    if not text:
        return {k: (False, "") for k in keys}
    result: dict[str, Tuple[bool, str]] = {k: (False, "") for k in keys}
    for line in text.splitlines(keepends=False):
        m = _KEY_LINE_RX.match(line)
        if not m:
            continue
        k = m.group('key').strip()
        if k in result:
            prefix = m.group('prefix')
            enabled = ';' not in prefix.strip()  # if prefix has ';', treat as disabled
            val = m.group('val').split(';', 1)[0].split('#', 1)[0].strip()
            result[k] = (enabled, val)
    return result


def write_keys_with_comment_state(settings: dict[str, Tuple[bool, str]]) -> None:
    """Write values and comment state for keys in work.ini, preserving layout.

    If enabled is False, ensure a ';' appears before the key (commented line).
    If enabled is True, remove leading ';' before the key.
    """
    path = _work_ini_path()
    _seed_work_ini_from_template_if_missing()
    text = _read_text(path)
    if not text:
        return
    lines = text.splitlines(keepends=True)
    key_set = set(settings.keys())
    for i, line in enumerate(lines):
        m = _KEY_LINE_RX.match(line)
        if not m:
            continue
        key = m.group('key').strip()
        if key not in key_set:
            continue
        enabled, value = settings[key]
        eol = m.group('eol') if m.group('eol') else "\n"
        # Build new line, adjusting comment mark
        # Build explicit prefix: add '; ' when disabled, nothing when enabled
        prefix = '' if enabled else '; '
        lines[i] = f"{prefix}{key}={value}{eol}"
    _write_text(path, "".join(lines))
    _publish_work_ini_changed()


def _read_user_info_from_mirror() -> dict[str, str]:
    """Read user info from the mirror file in repo-local config_gms directory.
    
    Returns empty dict for legacy keys - they should not exist in mirror anymore.
    Use get_user_ui_info_from_mirror() instead to read UI_* keys.
    """
    # This function is deprecated - return empty dict
    return {}

def get_user_ui_info_from_mirror() -> dict[str, str]:
    """Public: Read UI fields for startup from mirror.

    Uses dedicated UI_* keys to persist user inputs across restarts without
    writing legacy keys into INI. Falls back to DifficultyNameKey for Modname
    when UI_Modname missing.
    """
    data = _read_mirror_dict()
    ui = {
        "Modname": data.get("UI_Modname", ""),
        "Version": data.get("UI_Version", ""),
        "Date": data.get("UI_Date", ""),
        "Notes": _decode_multiline(data.get("UI_Notes", "")),
        # Template should not be persisted in mirror per spec
        "Template": "",
    }
    if not ui["Modname"]:
        ui["Modname"] = data.get("DifficultyNameKey", "")
    return ui


def apply_user_info_to_work_from_mirror() -> None:
    """Apply values from mirror file into work.ini (in-place value replace)."""
    vals = _read_user_info_from_mirror()
    _write_user_info_to_work(vals)


def delete_user_info_mirror() -> None:
    """Delete the mirror file to reset preserved user fields on uninstall."""
    try:
        p = _user_info_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass


def _write_bytes_atomic(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dst)


def start_fresh_action(label: str | None = None) -> None:
    """Overwrite the user's work.ini with a small Start-Fresh template.

    - `label` selects the template: one of 'Casual', 'Standard', 'Hard'.
      When omitted or invalid, defaults to 'Standard'.
    - Copies from repository path: system/templates/start_fresh/<Label>/work.ini
    - Destination is the Ready or Not work.ini under LOCALAPPDATA.
    - Always overwrites the destination file.
    """
    # Normalize label
    normalized = (label or "Standard").strip().title()
    if normalized not in {"Casual", "Standard", "Hard"}:
        normalized = "Standard"

    # Robuste Pfad-Ermittlung, die sowohl in Entwicklung als auch in kompilierten Builds funktioniert.
    def get_application_base_path() -> Path:
        """
        Ermittelt das Basisverzeichnis der Anwendung, egal ob als Skript oder als kompilierte EXE ausgeführt.
        """
        if getattr(sys, 'frozen', False):
            # In a frozen build, the base path is the directory of the executable.
            return Path(sys.executable).resolve().parent
        else:
            # In a development environment, walk up from this file until we find the 'system' folder.
            # This is more robust than checking for 'StrategoAI_Live_Generator.py'.
            p = Path(__file__).resolve().parent
            for parent in p.parents:
                if (parent / 'system').is_dir():
                    return parent
            raise FileNotFoundError("Could not locate application base path.")

    root = get_application_base_path()
    src = root / "system" / "templates" / "start_fresh" / normalized / "work.ini"
    if not src.exists():
        raise FileNotFoundError(f"Start fresh template not found: {src}")

    dst = _work_ini_path()
    data = src.read_bytes()
    _write_bytes_atomic(dst, data)
    # After replacing, restore Modname and Version from mirror if available
    try:
        mirror_vals = _read_user_info_from_mirror()
        restore: dict[str, str] = {}
        mod = (mirror_vals.get("Modname") or "").strip()
        ver = (mirror_vals.get("Version") or "").strip()
        if mod:
            restore["Modname"] = mod
        if ver:
            restore["Version"] = ver
        if restore:
            write_ini_values(restore)
    except Exception:
        # Non-fatal: if mirror missing or parse failed, continue
        pass
    # Touch to ensure any external watcher reacts
    try:
        os.utime(dst, None)
    except Exception:
        pass
    # Publish reset event to trigger full UI rebuild
    try:
        if _event_bus is not None:
            _event_bus.publish("work_ini_reset")
    except Exception:
        pass
    _publish_work_ini_changed()
    # After start fresh, force a new code/tag based on current UI values
    try:
        _purge_mapping_keys_from_mirror()
        ui = get_user_ui_info_from_mirror()
        mod = ui.get("Modname", "")
        ver = ui.get("Version", "")
        dt = ui.get("Date", "")
        nt = ui.get("Notes", "")
        if mod:
            apply_modname_mappings(mod, ver, dt, nt)
    except Exception:
        pass


def multiplayer_settings_action() -> None:
    _raise_placeholder("Multiplayer settings")


def alternative_ini_editor_action(jump: str | None = None) -> None:
    """Open INI editor as integrated window or fallback to system default.
    
    In frozen builds, opens the editor directly as Tkinter window (no separate EXE needed).
    In development, same behavior for consistency.
    """
    work_path = _work_ini_path()
    
    if not work_path.exists():
        try:
            _seed_work_ini_from_template_if_missing()
        except Exception:
            pass
    
    # Try to open integrated Tkinter editor
    try:
        from system.programs.ini_Editor.ini_editor import open_ini_editor
        open_ini_editor(str(work_path) if work_path.exists() else None, jump=jump)        
    except Exception:
        # If editor fails, fall back to system default
        try:
            if work_path.exists():
                os.startfile(str(work_path))  # type: ignore[attr-defined]
        except Exception:
            pass


def clean_all_action() -> None:
    """Reset work.ini to a clean template and remove mirrored user info.

    Steps:
    - Delete repo-local user_mission_info.json (mirror)
    - Copy system/templates/clean_all_ini/work.ini over the active Work/work.ini
    - Ensure destination directories exist
    - Touch the destination to update mtime so any watchers refresh
    """
    # Remove mirror file
    try:
        p = _user_info_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass

    # Resolve source clean template
    try:
        from system.config_main.main_actions import get_application_base_path
        base = get_application_base_path()
    except Exception:
        # Fallback for development environments
        base = Path(__file__).resolve().parents[5]

    src = base / "system" / "templates" / "clean_all_ini" / "work.ini"
    if not src.exists():
        raise FileNotFoundError(f"Clean template not found: {src}")

    # Destination work.ini
    dst = _work_ini_path()
    data = src.read_bytes()
    _write_bytes_atomic(dst, data)
    
    # Touch to ensure any external watcher reacts
    try:
        os.utime(dst, None)
    except Exception:
        pass
    
    # Publish reset event to trigger full UI rebuild
    try:
        if _event_bus is not None:
            _event_bus.publish("work_ini_reset")
    except Exception:
        pass
    _publish_work_ini_changed()


def register_actions() -> dict[str, Callable[[], None]]:
    """Return a mapping of action names for potential future integration."""

    return {
        "start_fresh": start_fresh_action,
        "multiplayer_settings": multiplayer_settings_action,
        "alternative_ini_editor": alternative_ini_editor_action,
        "clean_all": clean_all_action,
    }


__all__ = [
    "ActionNotImplementedError",
    "start_fresh_action",
    "multiplayer_settings_action",
    "alternative_ini_editor_action",
    "clean_all_action",
    "register_actions",
    "update_user_info",
    "update_user_info_work_only",
    "get_user_info",
    "enqueue_user_info",
    "apply_user_info_to_work_from_mirror",
    "delete_user_info_mirror",
    "get_current_difficulty_from_work",
    "apply_difficulty_to_work",
    "get_available_templates",
    "validate_template_format",
    "load_template",
    "get_user_ui_info_from_mirror",
]

# ---------------------- Difficulty helpers (minimal, safe) -------------------
def _find_section_exact(text: str, header: str) -> tuple[int, int]:
    """Return (start,end) byte positions of a section by exact header line.

    End is right before the next line that begins with '[' or EOF. (-1,-1) if missing.
    """
    lines = text.splitlines(keepends=True)
    pos = 0
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = pos
            j = i + 1
            end = pos + len(line)
            while j < len(lines):
                if lines[j].lstrip().startswith("["):
                    break
                end += len(lines[j])
                j += 1
            return start, end
        pos += len(line)
    return -1, -1


def get_current_difficulty_from_work() -> str:
    """Map DifficultyGameplayTag under [Info] to Casual/Standard/Hard.

    Rules:
    - If tag equals 'Difficulty.Standard' (ignoring spaces), return Standard.
    - If tag contains '.Casual' anywhere, return Casual.
    - If tag contains '.Hard' anywhere, return Hard.
    - Otherwise default to Standard.
    """
    text = _read_text(_work_ini_path())
    if not text:
        return "Standard"
    s, e = _find_section_exact(text, "[Info]")
    block = text[s:e] if s >= 0 else text
    for raw in block.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        if line.lower().startswith("difficultygameplaytag"):
            tag = line.split("=", 1)[1].strip().replace(" ", "")
            if tag.lower() == "difficulty.standard":
                return "Standard"
            if ".casual" in tag.lower():
                return "Casual"
            if ".hard" in tag.lower():
                return "Hard"
            return "Standard"
    return "Standard"


def apply_difficulty_to_work(label: str) -> None:
    """Replace only [Info] and GameplayTags blocks from small templates.

    Uses system/templates/build/<Label>_Info.ini. Replaces [Info] when present;
    if missing, inserts [Info] once at the top. GameplayTags block is replaced when
    present or appended once if missing. No other content is changed.
    """
    name = {"Casual": "Casual_Info.ini", "Standard": "Standard_Info.ini", "Hard": "Hard_Info.ini"}.get(label)
    if not name:
        return
    try:
        from system.config_main.main_actions import get_application_base_path
        root = get_application_base_path()
    except Exception:
        return
    tpl_path = root / "system" / "templates" / "build" / name
    if not tpl_path.exists():
        return
    tpl = _read_text(tpl_path)
    i_s, i_e = _find_section_exact(tpl, "[Info]")
    t_s, t_e = _find_section_exact(tpl, "[/Script/GameplayTags.GameplayTagsList]")
    info_block = tpl[i_s:i_e] if i_s >= 0 else ""
    tags_block = tpl[t_s:t_e] if t_s >= 0 else ""
    if not info_block and not tags_block:
        return
    work_path = _work_ini_path()
    text = _read_text(work_path)
    changed = False
    # Replace [Info] or insert once at top
    if info_block:
        s2, e2 = _find_section_exact(text, "[Info]")
        if s2 >= 0:
            text = text[:s2] + info_block + text[e2:]
            changed = True
        else:
            # insert once at top
            joiner = "\n" if (text and not text.startswith("[")) else ""
            text = info_block + (joiner + text if text else "")
            changed = True
    # GameplayTags replace or append once
    if tags_block:
        s3, e3 = _find_section_exact(text, "[/Script/GameplayTags.GameplayTagsList]")
        if s3 >= 0:
            text = text[:s3] + tags_block + text[e3:]
            changed = True
        else:
            joiner2 = "\n" if (text and not text.endswith(("\n", "\r"))) else ""
            text = text + joiner2 + tags_block
            changed = True
    if changed:
        _write_text(work_path, text)
        # Publish reset event when difficulty changes (full UI rebuild needed)
        try:
            if _event_bus is not None:
                _event_bus.publish("work_ini_reset")
        except Exception:
            pass
        _publish_work_ini_changed()
        # Auto-regenerate code/tag to match new difficulty using current UI values
        try:
            _purge_mapping_keys_from_mirror()
            ui = get_user_ui_info_from_mirror()
            mod = ui.get("Modname", "")
            ver = ui.get("Version", "")
            dt = ui.get("Date", "")
            nt = ui.get("Notes", "")
            if mod:
                apply_modname_mappings(mod, ver, dt, nt)
        except Exception:
            pass


# ----------------------- Modname mapping helpers ----------------------------

def _letters_only(s: str) -> str:
    try:
        return "".join(ch for ch in s if ch.isalpha())
    except Exception:
        return s


def _read_mirror_dict() -> dict[str, str]:
    text = _read_text(_user_info_path())
    data: dict[str, str] = {}
    if not text:
        return data
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v
    return data

def _encode_multiline(val: str) -> str:
    """Encode multiline text for single-line key=value storage.

    Converts CRLF/CR to LF, then replaces LF with literal \n.
    """
    try:
        s = str(val or "").replace("\r\n", "\n").replace("\r", "\n")
        return s.replace("\n", r"\n")
    except Exception:
        return str(val) if val is not None else ""

def _decode_multiline(val: str) -> str:
    """Decode literal \n sequences back to real newlines for UI display."""
    try:
        s = str(val or "")
        return s.replace(r"\n", "\n")
    except Exception:
        return str(val) if val is not None else ""


def _write_mirror_merge(values: dict[str, str]) -> None:
    """Merge provided key/values into mirror file without removing others."""
    path = _user_info_path()
    current = _read_mirror_dict()
    current.update({k: str(v) for k, v in (values or {}).items()})
    # Order: UI keys first, then mappings, then alpha of the rest
    ui_keys = ["UI_Modname", "UI_Version", "UI_Date", "UI_Notes"]
    mapping_keys = ["CodePrefix", "CodeNumber", "DifficultyNameKey", "DifficultySubtextKey", "DifficultyGameplayTag", "GameplayTag", "DifficultyFlavorKey"]
    keys = ui_keys + mapping_keys + sorted([k for k in current.keys() if k not in ui_keys and k not in mapping_keys])
    seen = set()
    lines: list[str] = []
    for k in keys:
        if k in current and k not in seen:
            lines.append(f"{k}={current[k]}")
            seen.add(k)
    content = "\n".join(lines) + "\n"
    _write_text(path, content)


def _purge_legacy_keys_from_mirror() -> None:
    """Remove legacy user keys from mirror (Modname, Version, Date, Notes, Template).
    
    These keys should never exist in the mirror file. Only UI_* keys are allowed.
    """
    path = _user_info_path()
    data = _read_mirror_dict()
    changed = False
    for k in _LEGACY_USER_KEYS:
        if k in data:
            del data[k]
            changed = True
    if not changed:
        return
    # Re-write without the legacy keys
    ui_keys = ["UI_Modname", "UI_Version", "UI_Date", "UI_Notes"]
    mapping_keys = ["CodePrefix", "CodeNumber", "DifficultyNameKey", "DifficultySubtextKey", "DifficultyGameplayTag", "GameplayTag", "DifficultyFlavorKey"]
    keys = ui_keys + mapping_keys + sorted([k for k in data.keys() if k not in ui_keys and k not in mapping_keys])
    seen = set()
    lines: list[str] = []
    for k in keys:
        if k in data and k not in seen:
            lines.append(f"{k}={data[k]}")
            seen.add(k)
    content = "\n".join(lines) + "\n" if lines else ""
    _write_text(path, content)


def _purge_mapping_keys_from_mirror() -> None:
    """Remove mapping keys so a new code/tag is generated on next apply.

    Keys: CodePrefix, CodeNumber, DifficultyGameplayTag, GameplayTag
    """
    path = _user_info_path()
    data = _read_mirror_dict()
    changed = False
    for k in ("CodePrefix", "CodeNumber", "DifficultyGameplayTag", "GameplayTag"):
        if k in data:
            del data[k]
            changed = True
    if not changed:
        return
    # Re-write remaining keys with the same ordering rules as _write_mirror_merge
    ui_keys = ["UI_Modname", "UI_Version", "UI_Date", "UI_Notes"]
    mapping_keys = ["CodePrefix", "CodeNumber", "DifficultyNameKey", "DifficultySubtextKey", "DifficultyGameplayTag", "GameplayTag", "DifficultyFlavorKey"]
    keys = ui_keys + mapping_keys + sorted([k for k in data.keys() if k not in ui_keys and k not in mapping_keys])
    seen = set()
    lines: list[str] = []
    for k in keys:
        if k in data and k not in seen:
            lines.append(f"{k}={data[k]}")
            seen.add(k)
    content = "\n".join(lines) + "\n" if lines else ""
    _write_text(path, content)

def _generate_code_for_modname(modname: str) -> tuple[str, int]:
    """Return (prefix, number) where prefix is 3 letters from modname and
    number is 1..999 not equal to the last used for this prefix.
    The last used number is read from mirror via CodePrefix/CodeNumber if the
    prefix matches.
    """
    import random
    letters = _letters_only(modname).strip()
    if not letters:
        letters = "MOD"
    prefix_source = letters.replace(" ", "")
    p = prefix_source[:3]
    if not p:
        p = "MOD"
    # Capitalize like example: Rea from RealLife
    prefix = p[0:1].upper() + p[1:].lower()
    mirror = _read_mirror_dict()
    last_prefix = mirror.get("CodePrefix", "")
    last_number = 0
    try:
        if last_prefix == prefix:
            last_number = int(mirror.get("CodeNumber", "0") or 0)
    except Exception:
        last_number = 0
    # pick random 1..999 not equal to last_number
    n = random.randint(1, 999)
    if last_number and n == last_number:
        # minimal retry once
        n = 1 if n != 1 else 2
    return prefix, n


def _difficulty_tag_root(label: str) -> str:
    L = (label or "Standard").strip().title()
    if L == "Casual":
        return "Difficulty.Standard.Casual."
    if L == "Hard":
        return "Difficulty.Hard."
    return "Difficulty.Standard."


def _build_subtext_value(display_name: str, notes_text: str | None = None) -> str:
    """Build DifficultySubtextKey string with display name and 4 bullet lines from Notes.

    Format:
    "display_name\r\n\r\n<grey.semibold>• line1</>\r\n<grey.semibold>• line2</>\r\n<grey.semibold>• line3</>\r\n<grey.semibold>• line4</>"
    """
    safe_name = str(display_name or "").strip()
    bullets: list[str]
    if notes_text is None:
        bullets = ["", "", "", ""]
    else:
        norm = str(notes_text).replace("\r\n", "\n").replace("\r", "\n")
        lines = norm.split("\n")
        # ensure exactly 4 entries
        bullets = [lines[i] if i < len(lines) else "" for i in range(4)]
    # Build with literal CRLF sequences inside the quoted string
    sub = (
        '"'
        + safe_name
        + "\\r\\n\\r\\n"
        + "\\r\\n".join([f"<grey.semibold>• {bullets[i]}</>" for i in range(4)])
        + '"'
    )
    return sub


def _format_flavor_value(date_str: str) -> str:
    """Build DifficultyFlavorKey value using italic with typographic quotes.

    Example: "<italic>“12.10.2025”</>"
    """
    safe = str(date_str or "").strip()
    # Use curly quotes U+201C and U+201D around the date
    return '"' + f"<italic>“{safe}”</>" + '"'


def _update_info_block_with_modname(text: str, display_name: str, tag_value: str, flavor_value: str | None = None, notes_text: str | None = None) -> str:
    """Replace DifficultyNameKey, DifficultySubtextKey and DifficultyGameplayTag in [Info].
    If keys are missing, append them at the end of the section.
    """
    s, e = _find_section_exact(text, "[Info]")
    if s < 0:
        # Insert a minimal [Info] at top
        eol = "\n" if ("\r\n" not in text) else "\r\n"
        block = f"[Info]{eol}DifficultyNameKey={display_name}{eol}DifficultySubtextKey={_build_subtext_value(display_name, notes_text)}{eol}DifficultyGameplayTag={tag_value}{eol}"
        if flavor_value is not None:
            block += f"DifficultyFlavorKey={flavor_value}{eol}"
        return block + ("\n" + text if text else "")
    block = text[s:e]
    lines = block.splitlines(keepends=True)
    keys = {"DifficultyNameKey": False, "DifficultySubtextKey": False, "DifficultyGameplayTag": False}
    for i, ln in enumerate(lines):
        raw = ln.strip()
        if not raw or raw.startswith(('#', ';', '[')) or '=' not in raw:
            continue
        k = raw.split('=', 1)[0].strip()
        eol = "\n" if ln.endswith("\n") else ("\r\n" if ln.endswith("\r\n") else "\n")
        if k == "DifficultyNameKey":
            lines[i] = f"DifficultyNameKey={display_name}{eol}"
            keys["DifficultyNameKey"] = True
        elif k == "DifficultySubtextKey":
            lines[i] = f"DifficultySubtextKey={_build_subtext_value(display_name, notes_text)}{eol}"
            keys["DifficultySubtextKey"] = True
        elif k == "DifficultyGameplayTag":
            lines[i] = f"DifficultyGameplayTag={tag_value}{eol}"
            keys["DifficultyGameplayTag"] = True
        elif k == "DifficultyFlavorKey" and flavor_value is not None:
            lines[i] = f"DifficultyFlavorKey={flavor_value}{eol}"
            # keep keys map as-is; not tracked for all()
    # append missing at end of section block (before closing)
    if not all(keys.values()):
        insert_at = len(lines)
        add_eol = "\n"
        if lines:
            add_eol = "\n" if lines[-1].endswith("\n") else ("\r\n" if lines[-1].endswith("\r\n") else "\n")
        extra: list[str] = []
        if not keys["DifficultyNameKey"]:
            extra.append(f"DifficultyNameKey={display_name}{add_eol}")
        if not keys["DifficultySubtextKey"]:
            extra.append(f"DifficultySubtextKey={_build_subtext_value(display_name, notes_text)}{add_eol}")
        if not keys["DifficultyGameplayTag"]:
            extra.append(f"DifficultyGameplayTag={tag_value}{add_eol}")
        if flavor_value is not None:
            extra.append(f"DifficultyFlavorKey={flavor_value}{add_eol}")
        lines[insert_at:insert_at] = extra
    return text[:s] + "".join(lines) + text[e:]


def _update_gameplay_tag_list(text: str, tag_value: str) -> str:
    """Replace the first GameplayTagList Tag that starts with "Difficulty." with tag_value.
    If none exists, append one at the end of the block or create the block if missing.
    """
    header = "[/Script/GameplayTags.GameplayTagsList]"
    s, e = _find_section_exact(text, header)
    eol = "\n" if ("\r\n" not in text) else "\r\n"
    line_tpl = f"GameplayTagList=(Tag=\"{tag_value}\",DevComment=\"\"){eol}"
    if s < 0:
        block = header + eol + line_tpl
        joiner = eol if text and not text.endswith(("\n", "\r")) else ""
        return text + joiner + block
    block = text[s:e]
    lines = block.splitlines(keepends=True)
    replaced = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith('GameplayTagList=') and 'Tag="Difficulty.' in ln:
            # preserve EOL of this line
            eol_i = "\n" if ln.endswith("\n") else ("\r\n" if ln.endswith("\r\n") else eol)
            lines[i] = f"GameplayTagList=(Tag=\"{tag_value}\",DevComment=\"\"){eol_i}"
            replaced = True
            break
    if not replaced:
        # append one line
        lines.append(line_tpl)
    return text[:s] + "".join(lines) + text[e:]


def apply_modname_mappings(modname: str, version: str | None = None, date_str: str | None = None, notes_text: str | None = None) -> None:
    """Apply Modname-derived mappings to [Info] and GameplayTags and mirror.

    Policy change:
    - Keep DifficultyGameplayTag/GameplayTagList stable across Modname edits.
    - Only generate a new code (prefix+number) when no mapping exists yet,
      i.e., after "Clean all" or "Uninstall" which remove the mirror file.

    Always update readable fields (DifficultyNameKey, DifficultySubtextKey,
    DifficultyFlavorKey) from the current inputs.
    """
    # Try to reuse existing mapping from mirror (stable across Modname changes)
    mirror = _read_mirror_dict()
    existing_tag = mirror.get("GameplayTag") or mirror.get("DifficultyGameplayTag")
    if existing_tag:
        tag_value = existing_tag
        # Derive prefix/number for mirror consistency if present
        prefix = mirror.get("CodePrefix", "")
        try:
            number = int(mirror.get("CodeNumber", "0") or 0)
        except Exception:
            number = 0
    else:
        # First run (or after Clean/Uninstall): generate new code
        prefix, number = _generate_code_for_modname(modname)
        difficulty = get_current_difficulty_from_work()
        root = _difficulty_tag_root(difficulty)
        tag_value = f"{root}{prefix}{number}"
    # Build display name and textual fields
    # Build display name with optional version suffix
    ver = (version or "").strip()
    display_name = modname.strip() if not ver else f"{modname.strip()} {ver}"

    path = _work_ini_path()
    text = _read_text(path)
    flavor_value = _format_flavor_value(date_str) if (date_str is not None and str(date_str).strip()) else None
    updated = _update_info_block_with_modname(text, display_name, tag_value, flavor_value, notes_text)
    updated = _update_gameplay_tag_list(updated, tag_value)
    if updated != text:
        _write_text(path, updated)
        _publish_work_ini_changed()
        try:
            if _event_bus is not None:
                _event_bus.publish("work_ini_reset")
        except Exception:
            pass
    # Mirror: purge legacy keys and persist only new mapping fields
    try:
        _purge_legacy_keys_from_mirror()
    except Exception:
        pass
    mm: dict[str, str] = {
        # Persist mapping (prefix/number) when known
        "DifficultyNameKey": display_name,
        "DifficultySubtextKey": _build_subtext_value(display_name, notes_text),
        "DifficultyGameplayTag": tag_value,
        "GameplayTag": tag_value,
    }
    if prefix:
        mm["CodePrefix"] = prefix
    if number:
        mm["CodeNumber"] = str(number)
    if flavor_value is not None:
        mm["DifficultyFlavorKey"] = flavor_value
    _write_mirror_merge(mm)

# Public helper for GUI live-updates
# Public helpers for GUI - these now work ONLY with the new mapping system
# Legacy Modname/Version/Date/Notes/Template keys are NEVER written to work.ini

def update_user_info(values: dict[str, str]) -> None:
    """Public helper to persist user info fields immediately.

    Expected keys: Modname, Version, Date, Notes (for UI compatibility)
    BUT: these are converted to the new mapping system and NEVER written as-is to work.ini!
    """
    # Apply Modname-dependent mappings only; legacy user keys are not persisted
    mod = values.get("Modname", "")
    ver = values.get("Version", "")
    dt = values.get("Date", "")
    nt = values.get("Notes", "")
    if mod:
        try:
            apply_modname_mappings(mod, ver, dt, nt)
        except Exception:
            pass


def update_user_info_work_only(values: dict[str, str]) -> None:
    """Persist only to work.ini (callers may mirror separately to avoid UI lag)."""
    # Only apply Modname mappings; do not write legacy keys
    mod = values.get("Modname", "")
    ver = values.get("Version", "")
    dt = values.get("Date", "")
    nt = values.get("Notes", "")
    if mod:
        try:
            apply_modname_mappings(mod, ver, dt, nt)
        except Exception:
            pass


def get_user_info() -> dict[str, str]:
    """Public helper to read user info from mirror for initial UI population.
    
    Returns UI_* values from mirror, NOT from work.ini!
    Legacy Modname/Version/Date/Notes keys do NOT exist in work.ini anymore.
    """
    return get_user_ui_info_from_mirror()


# ---------------------------------------------------------------------------
# Single background writer to avoid UI stalls
# ---------------------------------------------------------------------------

class _WriteWorker:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._shutdown = False
        self._wake = threading.Event()
        # queue items: (values, write_work, write_mirror)
        self._queue: deque[tuple[dict[str, str], bool, bool]] = deque()
        self._lock = threading.Lock()
        self._last_written: dict[str, str] = {}  # No longer tracks legacy keys
        self._debounce_ms = 0.3  # seconds

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._shutdown = False
        self._thread = threading.Thread(target=self._run, name="GMS-Writer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._shutdown = True
        self._wake.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=0.5)

    def enqueue_user_info(self, values: dict[str, str], *, write_work: bool, write_mirror: bool) -> None:
        # Apply Modname mappings for work.ini when requested
        try:
            if write_work:
                mod = ""
                ver = ""
                dt = ""
                nt = ""
                for k, v in (values or {}).items():
                    if str(k).lower() == "modname":
                        mod = str(v)
                        # do not break; also probe for version
                        continue
                    
                for k, v in (values or {}).items():
                    if str(k).lower() == "version":
                        ver = str(v)
                        break
                for k, v in (values or {}).items():
                    if str(k).lower() == "date":
                        dt = str(v)
                        break
                for k, v in (values or {}).items():
                    if str(k).lower() == "notes":
                        nt = str(v)
                        break
                if mod:
                    apply_modname_mappings(mod, ver, dt, nt)
        except Exception:
            pass
        # Persist UI fields into mirror under UI_* keys (no legacy writes to INI)
        try:
            if write_mirror:
                ui_vals: dict[str, str] = {}
                # Normalize expected inputs and map to UI_* keys
                for k, v in (values or {}).items():
                    kl = str(k).lower()
                    if kl == "modname":
                        ui_vals["UI_Modname"] = str(v)
                    elif kl == "version":
                        ui_vals["UI_Version"] = str(v)
                    elif kl == "date":
                        ui_vals["UI_Date"] = str(v)
                    elif kl == "notes":
                        ui_vals["UI_Notes"] = _encode_multiline(str(v))
                    # Do not persist template in mirror
                if ui_vals:
                    _write_mirror_merge(ui_vals)
        except Exception:
            pass

    def _coalesce_latest(self) -> tuple[dict[str, str], bool, bool] | None:
        with self._lock:
            if not self._queue:
                return None
            # keep only the last state; mirror true if any enqueued request wanted it
            latest_vals: dict[str, str] | None = None
            write_work = False
            write_mirror = False
            while self._queue:
                vals, ww, mm = self._queue.popleft()
                latest_vals = vals
                write_work = write_work or ww
                write_mirror = write_mirror or mm
            return (latest_vals or {}, write_work, write_mirror)

    def _run(self) -> None:
        pending: tuple[dict[str, str], bool, bool] | None = None
        next_flush = 0.0
        while not self._shutdown:
            # Wait for new work or flush timeout
            now = monotonic()
            timeout = max(0.0, next_flush - now) if pending else None
            self._wake.wait(timeout)
            self._wake.clear()

            # Grab newest work
            latest = self._coalesce_latest()
            if latest:
                pending = latest
                next_flush = monotonic() + self._debounce_ms

            # Flush if due
            if pending and monotonic() >= next_flush:
                vals, write_work, write_mirror = pending
                try:
                    # Write work.ini by applying mappings (no legacy keys written!)
                    if write_work:
                        mod = vals.get("Modname", "")
                        ver = vals.get("Version", "")
                        dt = vals.get("Date", "")
                        nt = vals.get("Notes", "")
                        if mod:
                            apply_modname_mappings(mod, ver, dt, nt)
                    # Always write mirror when requested (debounced by caller)
                    if write_mirror:
                        ui_vals: dict[str, str] = {}
                        for k, v in vals.items():
                            kl = str(k).lower()
                            if kl == "modname":
                                ui_vals["UI_Modname"] = str(v)
                            elif kl == "version":
                                ui_vals["UI_Version"] = str(v)
                            elif kl == "date":
                                ui_vals["UI_Date"] = str(v)
                            elif kl == "notes":
                                ui_vals["UI_Notes"] = _encode_multiline(str(v))
                        if ui_vals:
                            _write_mirror_merge(ui_vals)
                except Exception:
                    # swallow to keep worker alive
                    pass
                finally:
                    pending = None


_WRITER = _WriteWorker()


def enqueue_user_info(values: dict[str, str], *, write_work: bool = True, write_mirror: bool = True) -> None:
    """Queue a user-info write; processed by a single background worker.

    - Coalesces rapid changes, writes at most ~3/sec.
    - Avoids UI stalls and thread explosions.
    """
    _WRITER.start()
    _WRITER.enqueue_user_info(values, write_work=write_work, write_mirror=write_mirror)


# ---------------------------------------------------------------------------
# LiveSync pause/resume helpers (cooperate with system/config_main/live_sync.py)
# ---------------------------------------------------------------------------

def pause_live_sync() -> None:
    """Create a pause flag to stop main LiveSync while editing.

    IMPORTANT: Only if an active Difficulties folder exists. Do not create
    the Difficulties folder implicitly when the mod is deactivated or
    uninstalled, otherwise we reintroduce an 'active' folder inadvertently.
    """
    active = _active_difficulties_path()
    if not active.exists():
        return
    flag = active / "LiveSync.PAUSE"
    try:
        flag.write_text("paused", encoding="utf-8")
    except Exception:
        pass


def resume_live_sync(trigger_sync: bool = True) -> None:
    """Remove pause flag and optionally trigger a single sync by touching work.ini.

    No-ops entirely if the active Difficulties or work.ini do not exist.
    """
    active = _active_difficulties_path()
    if not active.exists():
        return
    flag = active / "LiveSync.PAUSE"
    try:
        if flag.exists():
            flag.unlink()
    except Exception:
        pass
    if trigger_sync:
        try:
            wp = _work_ini_path()
            if wp.exists():
                os.utime(wp, None)  # update mtime to trigger live sync poll
        except Exception:
            pass


def resume_live_sync_after(delay_seconds: float = 3.0, *, trigger_sync: bool = True) -> None:
    """Resume LiveSync after a delay without blocking the UI.

    Keeps the pause flag for the delay duration to suppress syncing, then
    removes it and optionally touches work.ini to trigger a single sync.
    """
    try:
        delay = float(delay_seconds)
    except Exception:
        delay = 3.0

    def _delayed():
        try:
            import time
            time.sleep(max(0.0, delay))
        except Exception:
            pass
        # After delay, resume as usual
        try:
            resume_live_sync(trigger_sync=trigger_sync)
        except Exception:
            pass

    try:
        t = threading.Thread(target=_delayed, daemon=True)
        t.start()
    except Exception:
        # Fallback to immediate resume if threading fails
        resume_live_sync(trigger_sync=trigger_sync)

# ---------------------------------------------------------------------------
# Template loading system
# ---------------------------------------------------------------------------

def _template_directories() -> list[Path]:
    """Return paths to template directories (user templates first, then standard templates)."""
    from system.config_main.main_actions import get_user_mod_files_path, get_application_base_path
    
    # 1. Benutzervorlagen im AppData-Verzeichnis
    user_templates = get_user_mod_files_path() / "MyTemplates"
    
    # 2. Standardvorlagen im Programmverzeichnis
    app_root = get_application_base_path()
    standard_templates = app_root / "system" / "templates" / "standard_templates"
    return [
        user_templates,
        standard_templates,
    ]


def get_available_templates() -> list[str]:
    """Scan template directories and return list of .ini filenames.
    
    Returns actual filenames (e.g., "Strat_RealLife_357.ini") sorted alphabetically.
    
    Always performs a fresh scan - no caching.
    """
    templates: set[str] = set()
    for directory in _template_directories():
        if not directory.exists():
            continue
        try:
            # Force fresh scan by using glob
            for file in directory.glob("*.ini"):
                # Only include files, not directories
                if file.is_file():
                    templates.add(file.name)
        except Exception:
            continue
    
    return sorted(templates)


# Removed get_template_filename_from_display() - no longer needed
# GUI now uses tuples (display_name, filename) directly


def _extract_modname_from_template(template_path: Path) -> str:
    """Extract display name from a template file.
    
    Returns the value of DifficultyNameKey= from [Info] section if found,
    otherwise empty string.
    """
    try:
        content = template_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        
        # Look for DifficultyNameKey in [Info] section
        in_info_section = False
        for line in lines:
            stripped = line.strip()
            
            # Check for [Info] section start
            if stripped == "[Info]":
                in_info_section = True
                continue
            
            # Exit [Info] section if we hit another section
            if in_info_section and stripped.startswith("[") and stripped.endswith("]"):
                in_info_section = False
            
            # Look for DifficultyNameKey in [Info] section
            if in_info_section and stripped.lower().startswith("difficultynamekey="):
                value = stripped.split("=", 1)[1].strip()
                # Remove quotes if present
                value = value.strip('"').strip()
                if value:
                    return value
        
        return ""
    except Exception:
        return ""


def _find_template_path(filename: str) -> Path | None:
    """Find full path to template file by searching template directories.
    
    User templates (MyTemplates) have priority over standard templates.
    """
    for directory in _template_directories():
        try:
            if not directory.is_dir():
                continue
            candidate = directory / filename
            if candidate.is_file():
                return candidate
        except OSError:  # Catches permission errors on non-existent paths
            continue
    return None


def validate_template_format(template_path: Path) -> bool:
    """Validate if template file matches Live Mod format (tolerant).

    Rules (kept minimal to avoid false negatives):
    - File must contain a "[Global]" section somewhere.
    - File must contain basic parameter keys in [Global] section.
    """
    try:
        content = template_path.read_text(encoding="utf-8")
        # Required section
        if "[Global]" not in content:
            return False

        # Just check that [Global] section has some content
        # (we don't check for specific legacy user keys anymore)
        return True
    except Exception:
        return False


def load_template(template_name: str) -> tuple[bool, str]:
    """Load a template and replace current work.ini content.
    
    This function:
    1. Pauses Live Sync
    2. Backs up user's Modname and Version from GUI (if available)
    3. Validates template format
    4. Replaces work.ini with template content
    5. Restores user's Modname and Version
    6. Resumes Live Sync
    
    Args:
        template_name: Filename of the template (e.g., "a1_Strat_RealLife.ini")
    
    Returns:
        Tuple of (success: bool, message: str)
        - (True, "Template loaded successfully") on success
        - (False, "error message") on failure
    """
    try:
        # Pause Live Sync immediately
        pause_live_sync()
        
        # Find template file
        template_path = _find_template_path(template_name)
        if not template_path:
            resume_live_sync(trigger_sync=False)
            return (False, f"Template '{template_name}' not found.")
        
        # Validate format
        if not validate_template_format(template_path):
            resume_live_sync(trigger_sync=False)
            return (False, "Template is not in Live Mod format and must be converted first.")
        
        # Backup user's Modname and Version from mirror file (if they exist)
        mirror_vals = _read_user_info_from_mirror()
        saved_modname = (mirror_vals.get("Modname") or "").strip()
        saved_version = (mirror_vals.get("Version") or "").strip()
        
        # Load template content
        template_content = template_path.read_text(encoding="utf-8")
        
        # Write template to work.ini
        work_path = _work_ini_path()
        work_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(work_path, template_content)
        # Publish reset event to trigger full UI rebuild (missions list reload)
        try:
            if _event_bus is not None:
                _event_bus.publish("work_ini_reset")
        except Exception:
            pass
        _publish_work_ini_changed()
        
        # Restore user's Modname and Version if they were saved
        restore_values: dict[str, str] = {}
        if saved_modname:
            restore_values["Modname"] = saved_modname
        if saved_version:
            restore_values["Version"] = saved_version
        
        if restore_values:
            # Use write_ini_values which now has fixed whitespace handling
            write_ini_values(restore_values)
        # After loading a template, force a new code/tag automatically
        try:
            _purge_mapping_keys_from_mirror()
            ui = get_user_ui_info_from_mirror()
            mod = ui.get("Modname", "") or restore_values.get("Modname", "")
            ver = ui.get("Version", "") or restore_values.get("Version", "")
            dt = ui.get("Date", "")
            nt = ui.get("Notes", "")
            if mod:
                apply_modname_mappings(mod, ver, dt, nt)
        except Exception:
            pass
        
        # Resume Live Sync and trigger immediate sync
        resume_live_sync(trigger_sync=True)
        
        return (True, "Template loaded successfully")
        
    except Exception as e:
        # Ensure Live Sync is resumed even on error
        try:
            resume_live_sync(trigger_sync=False)
        except Exception:
            pass
        return (False, f"Failed to load template: {str(e)}")
