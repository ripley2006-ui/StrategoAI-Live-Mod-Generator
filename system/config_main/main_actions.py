"""Action registry for StrategoAI generator buttons."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys
import shutil
from typing import Any, Callable, Dict, Optional

ActionContext = Dict[str, Any]


@dataclass
class ButtonState:
    """Describes visual/state updates for a button after an action."""

    text: Optional[str] = None
    style: Optional[str] = None
    tooltip: Optional[str] = None
    message: Optional[str] = None
    enabled: Optional[bool] = None


class ActionNotFound(KeyError):
    """Raised when an unknown action identifier is requested."""


class ActionExecutionError(RuntimeError):
    """Raised when an action callable fails during execution."""


ActionHandler = Callable[[ActionContext], Optional[ButtonState]]
StateResolver = Callable[[ActionContext], Optional[ButtonState]]


@dataclass
class ActionDefinition:
    """Container for action execution and optional status resolution."""

    run: Optional[ActionHandler] = None
    state: Optional[StateResolver] = None
    description: str = ""


ACTIONS: Dict[str, ActionDefinition] = {}


def register_action(
    action_id: str,
    *,
    run: Optional[ActionHandler] = None,
    state: Optional[StateResolver] = None,
    description: str = "",
) -> None:
    """Register or replace an action definition."""

    ACTIONS[action_id] = ActionDefinition(run=run, state=state, description=description)


def resolve_action_state(action_id: str, context: Optional[ActionContext] = None) -> Optional[ButtonState]:
    """Return the current button state without executing the action."""

    action = ACTIONS.get(action_id)
    if action is None:
        raise ActionNotFound(action_id)
    if action.state is None:
        return None
    return action.state(context or {})


def run_action(action_id: str, context: Optional[ActionContext] = None) -> Optional[ButtonState]:
    """Execute the action and optionally return a new button state."""

    action = ACTIONS.get(action_id)
    if action is None:
        raise ActionNotFound(action_id)
    if action.run is None:
        return None
    ctx = context or {}
    try:
        return action.run(ctx)
    except ActionExecutionError:
        raise
    except Exception as exc:  # pragma: no cover - surface to GUI layer
        raise ActionExecutionError(f"Aktion '{action_id}' fehlgeschlagen: {exc}") from exc


def list_actions() -> Dict[str, str]:
    """Return all registered actions with their description."""

    return {action_id: definition.description for action_id, definition in ACTIONS.items()}


# ---------------------------------------------------------------------------
# Example registration (remove or adjust for real actions)
# ---------------------------------------------------------------------------


def get_application_base_path() -> Path:
    """Return the base path for the application.

    - In a frozen build (Nuitka/PyInstaller), this is the directory containing the EXE.
    - In a development environment, this is the project root containing 'main.py' or 'StrategoAI_Live_Generator.py'.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as a bundled EXE (Nuitka or PyInstaller)
        return Path(sys.executable).parent
    # In development or when not bundled in a standard way, find the project root
    # by walking up from this file until we find the main script or the 'system' folder.
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "StrategoAI_Live_Generator.py").exists() or (parent / "system").is_dir():
            return parent
    return Path.cwd()  # Fallback if structure is unexpected

def get_user_mod_files_path() -> Path:
    """Gibt den Basispfad für benutzerspezifische Mod-Dateien zurück.

    Dieser Pfad ist für Daten gedacht, die vom Benutzer erstellt werden (Snapshots, Templates etc.)
    und befindet sich immer im AppData-Verzeichnis des Benutzers, um Schreibrechte zu garantieren.
    Pfad: C:\\Users\\<user>\\AppData\\Local\\ReadyOrNot\\Saved\\Config\\my_AImod_files
    """
    base = os.environ.get("LOCALAPPDATA")
    # Fallback, falls LOCALAPPDATA nicht gesetzt ist
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "ReadyOrNot" / "Saved" / "Config" / "my_AImod_files"

def _install_base_path() -> Path:
    """Return the ReadyOrNot Saved Config base for the current user.

    Uses LOCALAPPDATA to be user-agnostic and work on any machine.
    Fallback builds the standard path under the user profile.
    """
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / "AppData" / "Local"
    return root / "ReadyOrNot" / "Saved" / "Config"


def _is_live_mod_installed() -> bool:
    return (_install_base_path() / "Difficulties").exists()


def _is_live_mod_deactivated() -> bool:
    return (_install_base_path() / "Difficulties.disabled").exists()


def _live_mod_status(_context: ActionContext) -> Optional[ButtonState]:
    """Report install button state based on presence of Difficulties folder in install base."""

    if _is_live_mod_installed():
        # Installed → show green and lock button to prevent re-install
        return ButtonState(text="Mod installed", style="green", enabled=False)
    # If deactivated, the mod is present but renamed; do not offer install
    if _is_live_mod_deactivated():
        return ButtonState(text="Mod deactivated", style="gray", enabled=False, tooltip="Use 'Activate Live Mod' to re-enable.")
    return ButtonState(text="Install Live Mod", style="orange", enabled=True)


def _install_live_mod(context: ActionContext) -> Optional[ButtonState]:
    """DEPRECATED: Moved to footer_actions.install_live_mod.

    Kept for backward compatibility if referenced directly.
    """
    from .footer_actions import install_live_mod  # lazy import to avoid cycle
    return install_live_mod(context)


def _require_live_mod_installed(_context: ActionContext) -> Optional[ButtonState]:
    """Disable buttons until Live Mod is installed; enable afterwards without changing text/style."""
    if not _is_live_mod_installed():
        return ButtonState(enabled=False, style="gray")
    return ButtonState(enabled=True)


# Registration for 'install_live_mod' is moved to footer_actions to represent
# the transition into STATE 2 (installed). We still expose the state resolver
# here via footer_actions registration.

register_action(
    "require_live_mod_installed",
    state=_require_live_mod_installed,
    description="Aktiviert/Deaktiviert Buttons basierend auf installiertem Live Mod.",
)


__all__ = [
    "ButtonState",
    "ActionDefinition",
    "ActionExecutionError",
    "ActionNotFound",
    "register_action",
    "resolve_action_state",
    "run_action",
    "list_actions",
]
__all__.append("get_user_mod_files_path")

# Ensure footer-specific actions are imported and registered.
# This allows GUI to continue importing only main_actions while actions are
# modularized per-area (e.g., footer_actions).
from . import footer_actions as _footer_actions  # noqa: F401
