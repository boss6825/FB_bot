import json
import os
import shutil
from pathlib import Path

STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)
SESSION_FILE = STORAGE_DIR / "fb_session.json"


def save_session(storage_state: dict) -> None:
    """Save Playwright storage state (cookies + localStorage) to disk."""
    SESSION_FILE.write_text(json.dumps(storage_state))


def load_session() -> dict | None:
    """Return saved session state, or None if no session exists."""
    if not SESSION_FILE.exists():
        return None
    try:
        return json.loads(SESSION_FILE.read_text())
    except Exception:
        return None


def session_exists() -> bool:
    return SESSION_FILE.exists()


def clear_session() -> None:
    """Nuke session — forces re-login on next run."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def clear_browser_profile() -> None:
    """
    Remove persistent Playwright profile used by browser-use.
    This ensures account switch is clean even when keep-alive profile exists.
    """
    default_profile_dir = Path(__file__).parent / "storage" / "persistent-profile"
    configured_dir = os.getenv("BROWSER_USER_DATA_DIR", str(default_profile_dir))
    profile_dir = Path(configured_dir)

    if profile_dir.exists() and profile_dir.is_dir():
        shutil.rmtree(profile_dir, ignore_errors=True)
