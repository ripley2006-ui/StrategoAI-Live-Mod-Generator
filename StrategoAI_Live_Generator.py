"""Entrypoint for the StrategoAI Live Generator application."""

from __future__ import annotations

import sys
import os
from system.gui_main.gui_main import StrategoAILiveGeneratorApp


def _acquire_single_instance(lock_name: str) -> bool:
    try:
        import ctypes
        from ctypes import wintypes  # type: ignore
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        CreateMutexW = kernel32.CreateMutexW
        CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        CreateMutexW.restype = wintypes.HANDLE
        handle = CreateMutexW(None, False, lock_name)
        if not handle:
            return True
        # ERROR_ALREADY_EXISTS = 183
        err = ctypes.get_last_error()
        if err == 183:
            return False
        return True
    except Exception:
        return True


def main() -> None:
    # Special mode: allow launching the bundled INI editor in frozen builds
    try:
        mode = os.environ.get("STRATEGOAI_MODE", "").strip().lower()
        if mode == "ini_editor":
            # Rebuild argv for the editor __main__ using optional env hints
            editor_path = os.environ.get("STRATEGOAI_EDITOR_PATH", "")
            editor_jump = os.environ.get("STRATEGOAI_EDITOR_JUMP", "")
            argv = [sys.argv[0]]
            if editor_path:
                argv.append(editor_path)
            if editor_jump:
                argv.extend(["--jump", editor_jump])
            sys.argv = argv
            try:
                from system.programs.ini_Editor.__main__ import main as editor_main
                editor_main()
            except Exception:
                pass
            return
    except Exception:
        pass
    if not _acquire_single_instance("Global\\StrategoAI_Live_Generator"):
        try:
            print("StrategoAI Live Generator ist bereits gestartet.")
        except Exception:
            pass
        return
    app = StrategoAILiveGeneratorApp()
    app.run()


if __name__ == "__main__":
    main()
