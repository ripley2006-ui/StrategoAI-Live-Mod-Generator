"""Live synchronization of work.ini to game difficulty files.

Polls the work.ini file when the Live Mod is installed and copies its
contents to CasualDifficulty.ini, HardDifficulty.ini, and StandardDifficulty.ini
in the Difficulties folder. Files are created if missing.

Excluded parameters (preserved per difficulty):
- [Info] section: DifficultyGameplayTag, DifficultyNameKey, DifficultySubtextKey,
  DifficultyDescriptionKey, DifficultyFlavorKey, DifficultyBackground, StackupLevel
- [/Script/GameplayTags.GameplayTagsList] section: GameplayTagList

Game Detection:
- Synchronization ONLY runs while Ready Or Not is running
- If game is already running when program starts: sync immediately
- If game starts after program: waits 10 seconds before syncing begins
- Stops immediately when game is closed
- Monitors for process: ReadyOrNotSteam-Win64-Shipping.exe
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Callable
import time
import re

from . import main_actions as _ma

# Global toggle to enable/disable live synchronization.
# Set to False to disable polling completely.
ENABLED: bool = True

# Pre-game synchronization (runs even if the game is not running)
PRE_GAME_SYNC_ENABLED: bool = True
PRE_GAME_INTERVAL_SECONDS: int = 10

# Parameters that should NOT be synchronized (preserved per difficulty)
EXCLUDED_PARAMS = {
    'DifficultyGameplayTag',
    'DifficultyNameKey',
    'DifficultySubtextKey',
    'DifficultyDescriptionKey',
    'DifficultyFlavorKey',
    'DifficultyBackground',
    'StackupLevel',
    'GameplayTagList'
}

# Game detection settings
GAME_PROCESS_NAME = "ReadyOrNotSteam-Win64-Shipping.exe"
GAME_START_DELAY_SECONDS = 10


class LiveSyncManager:
    def __init__(self) -> None:
        self._root = None  # tk.Tk
        self._timer_id: Optional[str] = None
        self._interval_ms = 1000  # while actively syncing (game running)
        self._inactive_interval_ms = 3000  # idle UI housekeeping
        self._pre_game_interval_ms = PRE_GAME_INTERVAL_SECONDS * 1000
        self._last_mtime: Optional[float] = None
        self._inactive: bool = True
        
        # Game detection state
        self._game_running: bool = False
        self._game_start_time: Optional[float] = None
        self._sync_enabled_after_delay: bool = False
        self._initial_check_done: bool = False  # Track if we've done the initial game check

    def start(self, root) -> None:
        """Attach to Tk root and begin polling."""
        if not ENABLED:
            return
        self._root = root
        self._schedule_next()

    def stop(self) -> None:
        if self._root and self._timer_id:
            try:
                self._root.after_cancel(self._timer_id)
            except Exception:
                pass
        self._timer_id = None

    def refresh_now(self) -> None:
        """Force an immediate sync check (e.g., after actions)."""
        if not self._root or not ENABLED:
            return
        # Run one iteration quickly; next cycles will follow normal cadence
        try:
            self._poll()
        finally:
            self._schedule_next()

    def force_sync_now(self) -> None:
        """Force a sync of work.ini to the three difficulty files immediately.

        Ignores game state and intervals; still respects missing paths.
        """
        try:
            active, work = self._active_paths()
            if not work.exists():
                return
            # Create target directory if missing
            try:
                active.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            # Always preserve difficulty-specific headers before [Global]
            self._sync_files(active, work, preserve_excluded=True)
        except Exception:
            pass

    # Internal
    def _schedule_next(self) -> None:
        if not self._root or not ENABLED:
            return
        try:
            # Choose cadence based on game state
            if PRE_GAME_SYNC_ENABLED and not self._game_running:
                interval = self._pre_game_interval_ms
            else:
                interval = self._inactive_interval_ms if self._inactive else self._interval_ms
            self._timer_id = self._root.after(interval, self._on_timer)
        except Exception:
            self._timer_id = None

    def _on_timer(self) -> None:
        if not ENABLED:
            return
        try:
            self._poll()
        finally:
            self._schedule_next()

    def _active_paths(self) -> tuple[Path, Path]:
        base = _ma._install_base_path()
        difficulties_dir = base / "Difficulties"
        work_dir = base / "StrategoAI_Live_Mod" / "Work" / "work.ini"
        return difficulties_dir, work_dir

    def _is_game_running(self) -> bool:
        """Check if Ready Or Not is currently running."""
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'] == GAME_PROCESS_NAME:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            return False
        except ImportError:
            # psutil not available - fallback: always allow sync (like before)
            return True
        except Exception:
            # Any other error - fallback: always allow sync
            return True

    def _check_game_state(self) -> bool:
        """Check game state and return True if sync should proceed.
        
        Returns:
            True if sync should proceed, False if should wait or game not running
        """
        game_running = self._is_game_running()
        
        # Initial check on first poll - if game already running, enable sync immediately
        if not self._initial_check_done:
            self._initial_check_done = True
            if game_running:
                self._game_running = True
                self._sync_enabled_after_delay = True  # Enable immediately, no delay
                # print(f"[LiveSync] Game already running at startup, sync enabled immediately")
                return True
        
        # Game just started (wasn't running before, now is)
        if game_running and not self._game_running:
            self._game_running = True
            self._game_start_time = time.time()
            self._sync_enabled_after_delay = False
            # print(f"[LiveSync] Game started, waiting {GAME_START_DELAY_SECONDS}s before sync...")
            return False
        
        # Game stopped
        if not game_running and self._game_running:
            self._game_running = False
            self._game_start_time = None
            self._sync_enabled_after_delay = False
            # print(f"[LiveSync] Game stopped, sync disabled")
            return False
        
        # Game NOT running - NO SYNC
        if not game_running:
            return False
        
        # Game IS running - check if delay has passed (only if it was started after program)
        if game_running:
            if not self._sync_enabled_after_delay:
                if self._game_start_time:
                    elapsed = time.time() - self._game_start_time
                    if elapsed >= GAME_START_DELAY_SECONDS:
                        self._sync_enabled_after_delay = True
                        # print(f"[LiveSync] Delay passed, sync enabled while game running")
                        return True
                    else:
                        # Still waiting for delay
                        return False
            else:
                # Delay already passed (or game was running at startup), sync is enabled
                return True
        
        # Default: no sync
        return False

    def _poll(self) -> None:
        active, work = self._active_paths()
        if not work.exists():
            self._inactive = True
            self._last_mtime = None
            return
        
        # Check game state
        game_sync_allowed = self._check_game_state()
        pre_game_sync = PRE_GAME_SYNC_ENABLED and not game_sync_allowed
        if not game_sync_allowed and not pre_game_sync:
            # Neither in-game sync nor pre-game sync allowed
            self._inactive = True
            return
        
        # Pause mechanism: if a pause flag exists, skip syncing
        pause_flag = active / "LiveSync.PAUSE"
        if pause_flag.exists():
            try:
                # Track current mtime to avoid bulk sync when unpaused
                self._last_mtime = work.stat().st_mtime
            except Exception:
                self._last_mtime = None
            self._inactive = False  # Still consider environment active, just paused
            return
        try:
            stat = work.stat()
            mtime = stat.st_mtime
        except FileNotFoundError:
            self._inactive = True
            self._last_mtime = None
            return

        if self._last_mtime is None or mtime > self._last_mtime:
            self._last_mtime = mtime
            # Pre-game: overwrite excluded too; In-game: preserve excluded
            self._sync_files(active, work, preserve_excluded=game_sync_allowed)
        # Mark active when we performed or considered a sync without pause
        self._inactive = False

    def _parse_ini_line(self, line: str) -> tuple[Optional[str], str]:
        """Parse an INI line and extract the parameter name.
        
        Returns (param_name, original_line) or (None, original_line) if not a parameter.
        Handles lines with or without '=' and trailing spaces.
        """
        stripped = line.strip()
        
        # Skip empty lines, comments, and section headers
        if not stripped or stripped.startswith('#') or stripped.startswith(';') or stripped.startswith('['):
            return (None, line)
        
        # Try to extract parameter name (before '=' or end of line)
        if '=' in stripped:
            param_name = stripped.split('=')[0].strip()
        else:
            # Line without '=' - treat entire line as parameter name
            param_name = stripped
        
        return (param_name, line)

    def _merge_ini_content(self, source_content: str, target_path: Path, *, preserve_excluded: bool) -> str:
        """Merge `work.ini` into a difficulty file, syncing ONLY from [Global] onward.

        - Everything before the first [Global] in the TARGET stays untouched.
        - The body from [Global] in the SOURCE replaces the body in the TARGET.
        - If the target has no [Global], we append the source's [Global] body to the
          end of the target content (without touching what is already there).
        - If the source has no [Global], we do not modify the target.

        Note: `preserve_excluded` is kept for signature stability but the merge
        policy is always header-preserving to meet installation requirements.
        """
        # Locate [Global] in the source
        src_match = re.search(r"^\s*\[Global\]", source_content, re.MULTILINE | re.IGNORECASE)
        if not src_match:
            # Source has no [Global] -> do nothing
            try:
                return target_path.read_text(encoding='utf-8') if target_path.exists() else ""
            except Exception:
                return ""

        source_body = source_content[src_match.start():]

        # If target doesn't exist, create it as [Global] body only
        if not target_path.exists():
            return source_body.lstrip()

        # Read target and split at its [Global]
        try:
            target_content = target_path.read_text(encoding='utf-8')
        except Exception:
            # On read error, fallback to source body only
            return source_body.lstrip()

        tgt_match = re.search(r"^\s*\[Global\]", target_content, re.MULTILINE | re.IGNORECASE)
        if tgt_match:
            target_header = target_content[:tgt_match.start()]
            # Combine header + new body
            return target_header.rstrip() + "\n" + source_body.lstrip()
        else:
            # No [Global] in target: append source body
            sep = "\n" if not target_content.endswith("\n") else ""
            return target_content + sep + source_body.lstrip()

    def _rebuild_ini_from_sections(self, sections: dict[str, dict[str, str]]) -> str:
        """Rebuild INI content from sections dictionary."""
        lines = []
        
        for section_name, params in sections.items():
            # Add section header (if not HEADER)
            if section_name != "HEADER" and '__SECTION_HEADER__' in params:
                lines.append(params['__SECTION_HEADER__'])
            
            # Add all parameter lines in order
            for key, line in params.items():
                if not key.startswith('__') or key.startswith('__LINE_'):
                    lines.append(line)
        
        return ''.join(lines)

    def _sync_files(self, active: Path, work: Path, *, preserve_excluded: bool = True) -> None:
        """Sync work.ini to difficulty files, preserving excluded parameters."""
        try:
            source_content = work.read_text(encoding='utf-8')
        except Exception:
            return
        
        targets = [
            active / "CasualDifficulty.ini",
            active / "HardDifficulty.ini",
            active / "StandardDifficulty.ini",
        ]
        
        for target in targets:
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                
                # Merge or overwrite depending on mode
                merged_content = self._merge_ini_content(source_content, target, preserve_excluded=preserve_excluded)
                
                # Write merged content
                target.write_text(merged_content, encoding='utf-8')
            except Exception as e:
                # Skip failures; continue with other targets
                # print(f"[LiveSync] Failed to sync {target.name}: {e}")
                pass


__all__ = ["LiveSyncManager"]
