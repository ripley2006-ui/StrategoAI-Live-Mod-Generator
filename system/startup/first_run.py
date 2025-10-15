"""First-run initialization for StrategoAI Live Mod Generator.

This module creates the user folder structure on first run.
"""

from pathlib import Path
import sys


def get_app_root() -> Path:
    """Get the application root directory.
    
    Returns the directory where the EXE is located (frozen) or 
    the project root (development).
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled EXE
        return Path(sys.executable).parent
    else:
        # Running in development
        return Path(__file__).parent.parent.parent


def initialize_user_folders() -> bool:
    """Create user folder structure if it doesn't exist.
    
    Returns:
        True if folders were created (first run), False if already existed.
    """
    app_root = get_app_root()
    user_folder = app_root / "my_AImod_files"
    
    # Check if user folder already exists
    if user_folder.exists():
        return False  # Not first run
    
    # Create main user folder
    user_folder.mkdir(parents=True, exist_ok=True)
    
    # Create subfolders
    snapshots_folder = user_folder / "MySnapshots"
    templates_folder = user_folder / "MyTemplates"
    
    snapshots_folder.mkdir(exist_ok=True)
    templates_folder.mkdir(exist_ok=True)
    
    print(f"✅ Created user folders at: {user_folder}")
    print(f"   - {snapshots_folder.name}/")
    print(f"   - {templates_folder.name}/")
    
    return True  # First run


def ensure_user_folders_exist():
    """Ensure user folders exist. Create them if needed.
    
    This is called at application startup.
    """
    try:
        was_first_run = initialize_user_folders()
        if was_first_run:
            print("\n🎉 Welcome to StrategoAI Live Mod Generator!")
            print("User folders have been created successfully.\n")
    except Exception as e:
        print(f"⚠️ Warning: Could not create user folders: {e}")
        # Don't crash the app, just warn
