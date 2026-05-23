"""Browserbase context management for persistent Facebook sessions.

Uses Browserbase's Context API to persist cookies/storage across browser
sessions.  The user logs in manually once via a live Browserbase session;
cookies are saved in the context and reused for all subsequent automation.
"""

import json
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

logger = logging.getLogger("fb_agent.session")

STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)
CONTEXT_FILE = STORAGE_DIR / "bb_context.json"

BB_API_BASE = "https://www.browserbase.com/v1"


def _bb_headers() -> dict:
    api_key = os.getenv("BROWSERBASE_API_KEY", "")
    return {"x-bb-api-key": api_key, "Content-Type": "application/json"}


def _project_id() -> str:
    return os.getenv("BROWSERBASE_PROJECT_ID", "")


def load_context_id() -> str | None:
    """Load saved Browserbase context ID from disk."""
    if not CONTEXT_FILE.exists():
        return None
    try:
        data = json.loads(CONTEXT_FILE.read_text())
        return data.get("context_id") or None
    except Exception:
        return None


def save_context_id(context_id: str) -> None:
    """Persist Browserbase context ID to disk."""
    CONTEXT_FILE.write_text(json.dumps({"context_id": context_id}))


def clear_context_file() -> None:
    """Delete local context file."""
    if CONTEXT_FILE.exists():
        CONTEXT_FILE.unlink()


async def create_context() -> str:
    """Create a new Browserbase context via REST API. Returns context_id."""
    project_id = _project_id()
    if not project_id:
        raise ValueError(
            "BROWSERBASE_PROJECT_ID is not set. "
            "Add it to backend/.env (find it in your Browserbase dashboard)."
        )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BB_API_BASE}/contexts",
            headers=_bb_headers(),
            json={"projectId": project_id},
        )
        resp.raise_for_status()
        data = resp.json()
        context_id = data["id"]
        save_context_id(context_id)
        logger.info("Created Browserbase context: %s", context_id)
        return context_id


async def delete_context() -> None:
    """Delete Browserbase context via API and clear local file."""
    context_id = load_context_id()
    if not context_id:
        clear_context_file()
        return

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                f"{BB_API_BASE}/contexts/{context_id}",
                headers=_bb_headers(),
            )
            if resp.status_code == 404:
                logger.info("Context %s already deleted remotely", context_id)
            else:
                resp.raise_for_status()
                logger.info("Deleted Browserbase context: %s", context_id)
    except Exception:
        logger.warning("Failed to delete context %s via API", context_id, exc_info=True)
    finally:
        clear_context_file()


async def get_session_debug_urls(session_id: str) -> dict:
    """Return debug URLs for a Browserbase session.

    Response includes:
      - debuggerFullscreenUrl: bare embeddable live view (no Browserbase chrome) — for iframe
      - debuggerUrl: live view with Browserbase chrome — for opening in a new tab
    Older SDK versions may return `liveViewUrl` instead.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{BB_API_BASE}/sessions/{session_id}/debug",
            headers=_bb_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def get_or_create_context_id() -> str:
    """Return existing context ID or create a new one."""
    ctx = load_context_id()
    if ctx:
        return ctx
    return await create_context()


# ── Public helpers used by main.py ────────────────────────────────

def session_exists() -> bool:
    """True if a Browserbase context is saved (user has logged in before)."""
    return load_context_id() is not None


def clear_session() -> None:
    """Synchronous clear of local context file (does NOT delete remote)."""
    clear_context_file()


def clear_browser_profile() -> None:
    """No-op — no local browser profile with Browserbase."""
    pass
