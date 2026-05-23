import json
import shutil
from pathlib import Path

from config import BROWSER_USER_DATA_DIR

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


def load_context_id() -> str | None:
    """Compatibility shim for the current API layer."""
    return "local-browser-profile" if session_exists() else None


def save_context_id(context_id: str) -> None:
    """Compatibility shim; local sessions are saved via save_session()."""
    return None


async def get_or_create_context_id() -> str:
    """Compatibility shim for login start."""
    return "local-browser-profile"


async def delete_context_by_id(context_id: str) -> None:
    """Clear a pending local login profile if no saved session exists."""
    if not session_exists():
        clear_browser_profile()


async def delete_context() -> None:
    clear_session()
    clear_browser_profile()


def clear_session() -> None:
    """Nuke session — forces re-login on next run."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def clear_browser_profile() -> None:
    """
    Remove persistent Playwright profile used by browser-use.
    This ensures account switch is clean even when keep-alive profile exists.
    """
    profile_dir = Path(BROWSER_USER_DATA_DIR)

    if profile_dir.exists() and profile_dir.is_dir():
        shutil.rmtree(profile_dir, ignore_errors=True)
