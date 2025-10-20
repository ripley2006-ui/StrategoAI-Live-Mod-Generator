"""Action handlers for the Mod Juggler UI.

This module provides the business logic for managing mod sets:
- Creating and editing mod sets from templates
- Activating and deactivating mod sets
- Importing and exporting mod set configurations
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
import os
import json


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


def _mod_sets_path() -> Path:
    """Return path to the mod sets storage directory."""
    try:
        from system.config_main.main_actions import get_user_mod_files_path
        return get_user_mod_files_path() / "ModSets"
    except Exception:
        # Fallback for development environments
        return _local_appdata() / "StrategoAI_Live_Mod" / "ModSets"


def _ensure_mod_sets_directory() -> None:
    """Create the mod sets directory if it doesn't exist."""
    path = _mod_sets_path()
    path.mkdir(parents=True, exist_ok=True)


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
# Mod Set Management Actions
# =============================================================================

def create_set_action(set_name: str, templates: list[str]) -> None:
    """Create a new mod set with the given templates.

    Args:
        set_name: Name of the new mod set
        templates: List of template filenames to include
    """
    _raise_placeholder("Create Set")


def edit_set_action(set_name: str, templates: list[str]) -> None:
    """Edit an existing mod set's template list.

    Args:
        set_name: Name of the existing mod set
        templates: Updated list of template filenames
    """
    _raise_placeholder("Edit Set")


def delete_set_action(set_name: str) -> None:
    """Delete a mod set.

    Args:
        set_name: Name of the mod set to delete
    """
    _raise_placeholder("Delete Set")


def activate_set_action(set_name: str) -> None:
    """Activate a mod set (apply all templates to work.ini).

    Args:
        set_name: Name of the mod set to activate
    """
    _raise_placeholder("Activate Set")


def deactivate_set_action(set_name: str) -> None:
    """Deactivate a mod set.

    Args:
        set_name: Name of the mod set to deactivate
    """
    _raise_placeholder("Deactivate Set")


def duplicate_set_action(set_name: str, new_name: str) -> None:
    """Duplicate an existing mod set.

    Args:
        set_name: Name of the existing mod set
        new_name: Name for the duplicated mod set
    """
    _raise_placeholder("Duplicate Set")


def export_set_action(set_name: str, export_path: Path) -> None:
    """Export a mod set to a file.

    Args:
        set_name: Name of the mod set to export
        export_path: Path where to save the exported set
    """
    _raise_placeholder("Export Set")


def import_set_action(import_path: Path) -> None:
    """Import a mod set from a file.

    Args:
        import_path: Path to the mod set file to import
    """
    _raise_placeholder("Import Set")


# =============================================================================
# Mod Set Data Access
# =============================================================================

def get_mod_sets() -> list[dict[str, any]]:
    """Return list of all mod sets.

    Returns:
        List of dictionaries with keys: name, templates, active, created
    """
    _ensure_mod_sets_directory()
    sets_dir = _mod_sets_path()
    mod_sets = []

    try:
        for file in sets_dir.glob("*.json"):
            try:
                data = json.loads(_read_text(file))
                mod_sets.append({
                    "name": data.get("name", file.stem),
                    "templates": data.get("templates", []),
                    "active": data.get("active", False),
                    "created": data.get("created", ""),
                })
            except Exception:
                # Skip malformed files
                continue
    except Exception:
        pass

    return mod_sets


def get_available_templates() -> list[str]:
    """Return list of available mod templates.

    Returns:
        List of template filenames
    """
    # TODO: Implement template discovery
    # This should scan the templates directory and return available .ini files
    return []


def register_actions() -> dict[str, Callable[[], None]]:
    """Return a mapping of action names for potential future integration."""
    return {
        "create_set": lambda: create_set_action("", []),
        "edit_set": lambda: edit_set_action("", []),
        "delete_set": lambda: delete_set_action(""),
        "activate_set": lambda: activate_set_action(""),
        "deactivate_set": lambda: deactivate_set_action(""),
        "duplicate_set": lambda: duplicate_set_action("", ""),
        "export_set": lambda: export_set_action("", Path()),
        "import_set": lambda: import_set_action(Path()),
    }


__all__ = [
    "ActionNotImplementedError",
    "create_set_action",
    "edit_set_action",
    "delete_set_action",
    "activate_set_action",
    "deactivate_set_action",
    "duplicate_set_action",
    "export_set_action",
    "import_set_action",
    "get_mod_sets",
    "get_available_templates",
    "register_actions",
]
