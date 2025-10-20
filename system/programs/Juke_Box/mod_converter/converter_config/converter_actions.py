"""Action handlers for the Mod Converter UI.

This module provides the business logic for converting foreign mod formats:
- Extracting INI files from .pak archives
- Converting foreign INI format to Live Mod format
- Managing conversion jobs and output
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
import os
import shutil


class ActionNotImplementedError(NotImplementedError):
    """Raised when an action has not been implemented yet."""


def _raise_placeholder(name: str) -> None:
    raise ActionNotImplementedError(
        f"The '{name}' action has not been implemented yet."
    )


def _local_appdata() -> Path:
    """Return the local AppData directory."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    # Fallback to user profile if LOCALAPPDATA missing
    return Path.home() / "AppData" / "Local"


def _templates_path() -> Path:
    """Return path to the templates output directory."""
    try:
        from system.config_main.main_actions import get_user_mod_files_path
        return get_user_mod_files_path() / "MyTemplates"
    except Exception:
        # Fallback for development environments
        return _local_appdata() / "StrategoAI_Live_Mod" / "MyTemplates"


def _temp_extraction_path() -> Path:
    """Return path for temporary pak extraction."""
    try:
        from system.config_main.main_actions import get_user_mod_files_path
        return get_user_mod_files_path() / "TempConversion"
    except Exception:
        return _local_appdata() / "StrategoAI_Live_Mod" / "TempConversion"


def _ensure_directories() -> None:
    """Create necessary directories if they don't exist."""
    _templates_path().mkdir(parents=True, exist_ok=True)
    _temp_extraction_path().mkdir(parents=True, exist_ok=True)


def _read_text(path: Path) -> str:
    """Read text file with error handling."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_text(path: Path, content: str) -> None:
    """Write text file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# =============================================================================
# PAK File Extraction
# =============================================================================

def extract_pak_action(pak_path: Path) -> Optional[Path]:
    """Extract INI file from a .pak archive.

    Args:
        pak_path: Path to the .pak file

    Returns:
        Path to the extracted INI file, or None if extraction failed
    """
    _raise_placeholder("Extract PAK")


def cleanup_temp_files() -> None:
    """Clean up temporary extraction directory."""
    try:
        temp_dir = _temp_extraction_path()
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


# =============================================================================
# INI Conversion
# =============================================================================

def detect_mod_name(ini_path: Path) -> str:
    """Detect mod name from INI file.

    Args:
        ini_path: Path to the INI file

    Returns:
        Detected mod name or empty string
    """
    # TODO: Implement mod name detection from INI content
    # Look for DifficultyNameKey or similar identifiers
    return ini_path.stem


def validate_foreign_ini(ini_path: Path) -> tuple[bool, str]:
    """Validate if an INI file can be converted.

    Args:
        ini_path: Path to the INI file

    Returns:
        Tuple of (valid: bool, message: str)
    """
    try:
        content = _read_text(ini_path)

        if not content:
            return (False, "File is empty")

        # Basic validation - check for some expected sections
        # This is a placeholder - actual validation will depend on foreign mod format
        if "[Global]" in content or "[/Script/" in content:
            return (True, "Valid INI format detected")
        else:
            return (False, "Unknown INI format")

    except Exception as e:
        return (False, f"Error reading file: {e}")


def convert_ini_to_live_mod(source_path: Path, output_name: Optional[str] = None) -> tuple[bool, str, Path]:
    """Convert a foreign mod INI to Live Mod format.

    Args:
        source_path: Path to the source INI file
        output_name: Optional custom name for the output file

    Returns:
        Tuple of (success: bool, message: str, output_path: Path)
    """
    _raise_placeholder("Convert INI to Live Mod")


# =============================================================================
# Conversion Workflow
# =============================================================================

def process_conversion_job(source_path: str, source_type: str) -> tuple[bool, str, str]:
    """Process a conversion job from start to finish.

    Args:
        source_path: Path to the source file
        source_type: Type of source ("ini" or "pak")

    Returns:
        Tuple of (success: bool, message: str, output_path: str)
    """
    try:
        _ensure_directories()
        source = Path(source_path)

        if not source.exists():
            return (False, "Source file not found", "")

        # Handle PAK files
        if source_type == "pak":
            extracted_ini = extract_pak_action(source)
            if not extracted_ini:
                return (False, "Failed to extract INI from PAK", "")
            source = extracted_ini

        # Validate INI
        valid, msg = validate_foreign_ini(source)
        if not valid:
            return (False, f"Validation failed: {msg}", "")

        # Convert to Live Mod format
        success, msg, output_path = convert_ini_to_live_mod(source)

        # Cleanup temp files if this was a PAK extraction
        if source_type == "pak":
            cleanup_temp_files()

        return (success, msg, str(output_path))

    except Exception as e:
        return (False, f"Conversion failed: {e}", "")


# =============================================================================
# Output Management
# =============================================================================

def open_output_folder() -> None:
    """Open the templates output folder in file explorer."""
    try:
        output_path = _templates_path()
        output_path.mkdir(parents=True, exist_ok=True)

        if os.name == 'nt':  # Windows
            os.startfile(str(output_path))  # type: ignore
        elif os.name == 'posix':  # macOS/Linux
            import subprocess
            subprocess.run(['xdg-open', str(output_path)])
    except Exception:
        pass


def get_output_path_for_mod(mod_name: str) -> Path:
    """Get the output path for a converted mod.

    Args:
        mod_name: Name of the mod

    Returns:
        Path where the converted mod will be saved
    """
    _ensure_directories()
    output_dir = _templates_path()

    # Sanitize mod name for filename
    safe_name = "".join(c for c in mod_name if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_name:
        safe_name = "Converted_Mod"

    # Add timestamp to avoid conflicts
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}.ini"

    return output_dir / filename


def register_actions() -> dict[str, Callable[[], None]]:
    """Return a mapping of action names for potential future integration."""
    return {
        "extract_pak": lambda: extract_pak_action(Path()),
        "convert_ini": lambda: convert_ini_to_live_mod(Path()),
        "open_output": open_output_folder,
        "cleanup_temp": cleanup_temp_files,
    }


__all__ = [
    "ActionNotImplementedError",
    "extract_pak_action",
    "detect_mod_name",
    "validate_foreign_ini",
    "convert_ini_to_live_mod",
    "process_conversion_job",
    "open_output_folder",
    "get_output_path_for_mod",
    "cleanup_temp_files",
    "register_actions",
]
