"""Backend actions for the Mission Settings GUI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
try:
    from system.gui_utils import event_bus as _event_bus  # type: ignore
except Exception:
    _event_bus = None  # type: ignore


@dataclass
class MissionDef:
    """Represents one mission section with its editable parameters."""
    index: int
    section: str
    title: str
    params: List[Tuple[str, str]]  # (key, value) list - empty key "" means blank line separator


def _work_path() -> Path:
    """Get path to work.ini."""
    from system.programs.Live_Mod.Global_Mission_Settings.config_gms.gms_actions import _work_ini_path
    return _work_ini_path()


def _read_text(path: Path) -> str:
    """Read text file safely."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _write_text(path: Path, text: str) -> None:
    """Write text file safely."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except Exception:
        pass

def _get_work_ini_values() -> Dict[str, Dict[str, str]]:
    """Reads all sections and key-value pairs from work.ini."""
    work_text = _read_text(_work_path())
    all_values: Dict[str, Dict[str, str]] = {}
    current_section = ""
    for line in work_text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            all_values[current_section] = {}
        elif current_section and "=" in line and not line.startswith(("#", ";")):
            key, val = line.split("=", 1)
            all_values[current_section][key.strip()] = val.split(";")[0].split("#")[0].strip()
    return all_values

def extract_missions_from_template(path: Path) -> List[MissionDef]:
    """Parse work.ini to discover all missions and their optional parameters.
    
    Only reads from work.ini - no fallback to template.
    """
    missions: List[MissionDef] = []
    
    # Only read from work.ini
    work_path = _work_path()
    if not work_path.exists():
        return missions

    try:
        lines = work_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return missions

    work_values = _get_work_ini_values()

    i = 0
    idx = 0
    end_marker = "# ini file by StrategoAI Mod Generator"

    while i < len(lines):
        line = lines[i].strip()

        if line.startswith(end_marker):
            break

        if line.startswith("[") and line.endswith("]") and "_Core" in line:
            section = line.strip("[]")

            title = section
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if s.startswith(end_marker) or s.startswith("[") or not s:
                    break
                if s.startswith("#") and " - " in s:
                    try:
                        title = s.lstrip("#").strip().split(" - ", 1)[0].strip()
                    except Exception:
                        pass
                    break
                j += 1

            # Find the start of the optional settings block for this mission
            optional_settings_start_line = -1
            l = i + 1
            while l < len(lines):
                line_l = lines[l].strip()
                if line_l.startswith("["):  # Stop at next section
                    break
                if line_l.startswith("#--Optional Settings"):
                    optional_settings_start_line = l
                    break
                l += 1

            params: List[Tuple[str, str]] = []
            if optional_settings_start_line != -1:
                # Start parsing parameters AFTER the marker line
                k = optional_settings_start_line + 1
                while k < len(lines):
                    st = lines[k].strip()
                    if st.startswith("["):  # Stop at the next section
                        break
                    # Include empty lines as separators (key="", value="")
                    if not st:
                        params.append(("", ""))
                    elif not st.startswith(("#", ";")) and "=" in st:
                        try:
                            key, val = st.split("=", 1)
                            current_val = work_values.get(section, {}).get(key.strip(), val.split(";")[0].split("#")[0].strip())
                            params.append((key.strip(), current_val))
                        except Exception:
                            pass
                    k += 1

            # Only add the mission if it has optional parameters
            if not params:
                i += 1
                continue

            missions.append(MissionDef(index=idx, section=section, title=title, params=params))
            idx += 1
            if idx >= 26:
                break
            i = k
            continue
        i += 1
    
    return missions


def _find_section(text: str, header: str) -> Tuple[int, int]:
    """Find section boundaries in INI text."""
    lines = text.splitlines(keepends=True)
    pos = 0
    for i, line in enumerate(lines):
        if line.strip() == f"[{header}]":
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


def write_mission_parameter(section: str, key: str, value: str) -> None:
    """Write a single parameter value for a given mission section to work.ini."""
    work_file = _work_path()
    current_text = _read_text(work_file)
    if not current_text:
        return

    s, e = _find_section(current_text, section)
    if s < 0:
        return

    block = current_text[s:e]
    lines = block.splitlines(keepends=True)
    updated = False
    for i, ln in enumerate(lines):
        raw = ln.strip()
        if raw and not raw.startswith(('#', ';', '[')) and '=' in raw:
            k = raw.split('=', 1)[0].strip()
            if k == key:
                eol = "\n" if ln.endswith("\n") else ("\r\n" if ln.endswith("\r\n") else "\n")
                lines[i] = f"{k}={value}{eol}"
                updated = True
                break
    
    if not updated:
        last_line_idx = len(lines) - 1
        if last_line_idx != -1:
            if not lines[last_line_idx].endswith(("\n", "\r")):
                lines[last_line_idx] += "\n"
            lines.append(f"{key}={value}\n")
            updated = True

    if updated:
        new_text = current_text[:s] + "".join(lines) + current_text[e:]
        _write_text(work_file, new_text)
        try:
            if _event_bus is not None:
                _event_bus.publish("work_ini_changed")
        except Exception:
            pass


def write_mission_parameters(section: str, updates: Dict[str, str]) -> None:
    """Write multiple parameters for a mission section in a single pass.

    Significantly faster than writing keys one-by-one.
    - Updates existing keys in-place (preserving EOL style and layout)
    - Appends missing keys at the end of the section block
    """
    if not updates:
        return
    work_file = _work_path()
    current_text = _read_text(work_file)
    if not current_text:
        return

    s, e = _find_section(current_text, section)
    if s < 0:
        return

    block = current_text[s:e]
    lines = block.splitlines(keepends=True)
    pending = {k.strip(): v for k, v in updates.items()}
    eol_default = "\n"
    updated_any = False

    for i, ln in enumerate(lines):
        raw = ln.strip()
        if raw and not raw.startswith(('#', ';', '[')) and '=' in raw:
            k = raw.split('=', 1)[0].strip()
            if k in pending:
                eol = "\n" if ln.endswith("\n") else ("\r\n" if ln.endswith("\r\n") else eol_default)
                lines[i] = f"{k}={pending.pop(k)}{eol}"
                updated_any = True

    # Append remaining keys at the end of the section block (before next section)
    if pending:
        # Ensure the block ends with a newline
        if not (lines and (lines[-1].endswith("\n") or lines[-1].endswith("\r"))):
            lines.append(eol_default)
        for k, v in pending.items():
            lines.append(f"{k}={v}{eol_default}")
        updated_any = True

    if updated_any:
        new_text = current_text[:s] + "".join(lines) + current_text[e:]
        _write_text(work_file, new_text)
        try:
            if _event_bus is not None:
                _event_bus.publish("work_ini_changed")
        except Exception:
            pass
