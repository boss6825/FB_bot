import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, BackgroundTasks

logger = logging.getLogger("fb_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from session import (
    session_exists,
    load_context_id,
    clear_session,
    clear_browser_profile,
    get_or_create_context_id,
    delete_context,
    delete_context_by_id,
)
from llm import parse_intent, generate_post_text, generate_comment_text, build_agent_task
from store import TaskStore
import config as _config  # noqa: F401  — ensures MODEL_API_KEY env var is set early

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

app = FastAPI(title="Geodo FB Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLite-backed task store for status polling.
tasks = TaskStore()

# In-memory registry for CAPTCHA events (task_id → asyncio.Event)
_captcha_events: dict[str, asyncio.Event] = {}

# In-memory registry for active login sessions
_login_sessions: dict[str, dict] = {}


# ── Request models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    task_id: str


class DraftRequest(BaseModel):
    task_id: str
    message: str | None = None
    action: str | None = None
    target_url: str | None = None
    content_brief: str | None = None


class PublishDraftRequest(BaseModel):
    text: str


# ── Routes ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status/setup")
def setup_status():
    """Tell the frontend whether the user is logged in."""
    logged_in = session_exists()
    return {
        "credentials_saved": logged_in,
        "credentials_valid": logged_in,
        "session_active": logged_in,
        "logged_in": logged_in,
    }


# ── Login flow (user logs in manually via Browserbase) ────────────

@app.post("/auth/login/start")
async def start_login():
    """Start a Browserbase session for manual Facebook login.

    Returns { session_id, session_url } — the user opens session_url
    in their browser and logs into Facebook manually.
    """
    from agent import start_login_session

    context_id = await get_or_create_context_id()

    try:
        info = await start_login_session(context_id)
    except Exception as e:
        logger.exception("Failed to start login session")
        raise HTTPException(status_code=500, detail=_user_facing_error(e))

    _login_sessions[info["session_id"]] = {
        "context_id": context_id,
    }

    return {
        "session_id": info["session_id"],
        "session_url": info["session_url"],
        "live_view_url": info.get("live_view_url"),
    }


@app.post("/auth/login/verify/{session_id}")
async def verify_login(session_id: str):
    """User confirms login. Persist context + release session."""
    if session_id not in _login_sessions:
        raise HTTPException(status_code=404, detail="Login session not found or already ended.")

    from agent import verify_login_session, end_session
    from session import save_context_id

    info = _login_sessions[session_id]
    result = await verify_login_session(session_id)

    if result["logged_in"]:
        save_context_id(info["context_id"])
        await end_session(session_id)
        del _login_sessions[session_id]
        return {"status": "logged_in"}

    return {
        "status": "not_logged_in",
        "state": result.get("state", "other"),
        "details": result.get("details", ""),
    }


@app.post("/auth/login/cancel/{session_id}")
async def cancel_login(session_id: str):
    """Cancel an active login session."""
    if session_id not in _login_sessions:
        raise HTTPException(status_code=404, detail="Login session not found.")

    from agent import end_session

    info = _login_sessions.pop(session_id)
    await end_session(session_id)
    if load_context_id() != info.get("context_id"):
        await delete_context_by_id(info.get("context_id"))
    return {"message": "Login session cancelled."}


@app.post("/auth/logout")
async def logout():
    """Disconnect account: delete Browserbase context + clear local data."""
    from agent import end_session as _end
    pending_contexts = []
    for sid, info in list(_login_sessions.items()):
        pending_contexts.append(info.get("context_id"))
        try:
            await _end(sid)
        except Exception:
            pass
    _login_sessions.clear()

    saved_context_id = load_context_id()
    await delete_context()
    for context_id in pending_contexts:
        if context_id and context_id != saved_context_id:
            await delete_context_by_id(context_id)
    return {"message": "Logged out successfully."}


# ── Chat (legacy direct-execute endpoint) ─────────────────────────

@app.post("/chat")
async def chat(body: ChatRequest, background_tasks: BackgroundTasks):
    if not session_exists():
        raise HTTPException(
            status_code=400,
            detail="Not logged in. Please log in to Facebook first via Settings.",
        )

    tasks[body.task_id] = {"status": "processing", "result": None, "error": None}
    background_tasks.add_task(run_task, body.task_id, body.message)

    return {"task_id": body.task_id, "status": "processing"}


@app.get("/task/{task_id}")
def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found.")
    return tasks[task_id]


@app.post("/task/{task_id}/captcha-solved")
def captcha_solved(task_id: str):
    """User has solved the CAPTCHA in the Browserbase session — unblock the agent."""
    event = _captcha_events.get(task_id)
    if not event:
        raise HTTPException(status_code=404, detail="No pending CAPTCHA for this task.")
    event.set()
    if task_id in tasks:
        prev_status = tasks[task_id].get("_pre_captcha_status", "processing")
        tasks[task_id].update({"status": prev_status})
    return {"message": "Resuming automation."}


# ── Draft endpoints ───────────────────────────────────────────────

@app.post("/draft")
async def create_draft_endpoint(body: DraftRequest, background_tasks: BackgroundTasks):
    if not session_exists():
        raise HTTPException(
            status_code=400,
            detail="Not logged in. Please log in to Facebook first via Settings.",
        )

    tasks[body.task_id] = {
        "status": "processing",
        "result": None,
        "error": None,
        "generated_content": None,
        "action": None,
        "intent": None,
    }
    background_tasks.add_task(create_draft, body.task_id, body)
    return {"task_id": body.task_id, "status": "processing"}


@app.post("/draft/{draft_id}/publish")
async def publish_draft(draft_id: str, body: PublishDraftRequest, background_tasks: BackgroundTasks):
    if draft_id not in tasks:
        raise HTTPException(status_code=404, detail="Draft not found.")
    task = tasks[draft_id]
    if task.get("status") != "draft":
        raise HTTPException(status_code=400, detail=f"Task is not in draft state (current status: {task.get('status')}).")

    intent = task.get("intent") or {}
    action = task.get("action", "post")
    target_url = intent.get("target_url")

    tasks[draft_id]["status"] = "publishing"
    tasks[draft_id]["edited_text"] = body.text

    background_tasks.add_task(publish_task, draft_id, body.text, action, target_url)
    return {"task_id": draft_id, "status": "publishing"}


# ── CAPTCHA callback factory ──────────────────────────────────────

def _make_captcha_callback(task_id: str):
    """Return an async callback for agent.py to call when a CAPTCHA is detected."""

    async def on_captcha(session_id: str, state: str, details: str):
        event = asyncio.Event()
        _captcha_events[task_id] = event
        pre = tasks[task_id].get("status", "processing") if task_id in tasks else "processing"
        tasks[task_id].update({
            "status": "captcha_required",
            "_pre_captcha_status": pre,
            "captcha_type": state,
            "captcha_details": details,
            "session_url": f"https://www.browserbase.com/sessions/{session_id}",
        })
        return event

    return on_captcha


# ── Background task runners ──────────────────────────────────────

async def run_task(task_id: str, message: str):
    """Parse intent, generate content, run Browserbase agent."""
    try:
        context_id = load_context_id()
        if not context_id:
            tasks[task_id] = {
                "status": "error",
                "result": None,
                "error": "Not logged in. Please log in to Facebook first.",
            }
            return

        intent = parse_intent(message)
        action = intent.get("action", "unknown")
        brief = intent.get("content_brief", message)
        target_url = intent.get("target_url")

        if action == "comment":
            normalized_url = _normalize_facebook_url(target_url)
            if not normalized_url:
                tasks[task_id] = {
                    "status": "error",
                    "result": None,
                    "error": "Comment requests must include a valid Facebook post URL.",
                }
                return
            target_url = normalized_url

        if action == "unknown":
            tasks[task_id] = {
                "status": "done",
                "result": "I couldn't understand what you want to do on Facebook. Try something like 'post about X' or 'comment on <url> saying Y'.",
                "error": None,
            }
            return

        if action == "post":
            content = generate_post_text(brief)
        elif action == "comment":
            content = generate_comment_text(brief)
        else:
            content = brief

        agent_task = build_agent_task(action, content, target_url)

        from agent import run_fb_task
        result = await run_fb_task(
            agent_task,
            context_id,
            on_captcha=_make_captcha_callback(task_id),
        )

        failure_prefixes = ("Login failed", "Login expired", "Agent failed", "Agent stopped", "CAPTCHA was not")
        is_failure = any(result.startswith(prefix) for prefix in failure_prefixes)

        if is_failure:
            tasks[task_id] = {
                "status": "error",
                "result": None,
                "generated_content": content,
                "action": action,
                "error": result,
            }
            return

        tasks[task_id] = {
            "status": "done",
            "result": result,
            "generated_content": content,
            "action": action,
            "target_url": target_url,
            "error": None,
        }

    except Exception as e:
        logger.exception("Task %s failed", task_id)
        tasks[task_id] = {
            "status": "error",
            "result": None,
            "error": _user_facing_error(e),
        }
    finally:
        _captcha_events.pop(task_id, None)


async def create_draft(task_id: str, body: DraftRequest):
    """Parse intent and generate text; stop before browser automation."""
    try:
        structured_action = (body.action or "").strip().lower()
        uses_structured_path = bool(structured_action)

        if uses_structured_path:
            if structured_action not in {"post", "comment"}:
                tasks[task_id].update({
                    "status": "error",
                    "error": "Unsupported action. Use 'post' or 'comment'.",
                })
                return

            brief = (body.content_brief or body.message or "").strip()
            if not brief:
                tasks[task_id].update({
                    "status": "error",
                    "error": "Please provide content for the draft.",
                })
                return

            target_url = _normalize_facebook_url(body.target_url)
            if structured_action == "comment" and not target_url:
                tasks[task_id].update({
                    "status": "error",
                    "error": "Comment requests must include a valid Facebook post URL.",
                })
                return

            intent = {
                "action": structured_action,
                "target_url": target_url,
                "content_brief": brief,
            }
            action = structured_action
        else:
            message = (body.message or "").strip()
            if not message:
                tasks[task_id].update({
                    "status": "error",
                    "error": "Message is required.",
                })
                return

            intent = parse_intent(message)
            action = intent.get("action", "unknown")
            brief = intent.get("content_brief", message)

            if action == "comment":
                normalized_url = _normalize_facebook_url(intent.get("target_url"))
                if not normalized_url:
                    tasks[task_id].update({
                        "status": "error",
                        "error": "Comment requests must include a valid Facebook post URL.",
                    })
                    return
                intent["target_url"] = normalized_url

        if action == "unknown":
            tasks[task_id].update({
                "status": "error",
                "error": "I couldn't understand what you want to do on Facebook. Try something like 'post about X'.",
            })
            return

        content = generate_post_text(brief) if action == "post" else generate_comment_text(brief)

        tasks[task_id].update({
            "status": "draft",
            "generated_content": content,
            "action": action,
            "intent": intent,
            "target_url": intent.get("target_url"),
        })
    except Exception as e:
        logger.exception("Draft %s failed", task_id)
        tasks[task_id].update({
            "status": "error",
            "error": _user_facing_error(e),
        })


async def publish_task(task_id: str, content: str, action: str, target_url: str | None):
    """Build agent task string and run Browserbase automation with user-confirmed text."""
    try:
        context_id = load_context_id()
        if not context_id:
            tasks[task_id].update({"status": "error", "result": None, "error": "Not logged in. Please log in first."})
            return

        agent_task = build_agent_task(action, content, target_url)

        from agent import run_fb_task
        result = await run_fb_task(
            agent_task,
            context_id,
            on_captcha=_make_captcha_callback(task_id),
        )

        failure_prefixes = ("Login failed", "Login expired", "Agent failed", "Agent stopped", "CAPTCHA was not")
        is_failure = any(result.startswith(p) for p in failure_prefixes)

        if is_failure:
            tasks[task_id].update({"status": "error", "result": None, "error": result})
            return

        tasks[task_id].update({"status": "done", "result": result, "error": None})

    except Exception as e:
        logger.exception("Publish task %s failed", task_id)
        tasks[task_id].update({"status": "error", "result": None, "error": _user_facing_error(e)})
    finally:
        _captcha_events.pop(task_id, None)


def _user_facing_error(e: Exception) -> str:
    """Map internal exceptions to short, safe messages for the UI."""
    msg = str(e).strip()
    name = type(e).__name__
    if isinstance(e, NotImplementedError):
        return "Browser automation couldn't start on this system. Check the backend logs."
    if "credentials" in msg.lower():
        return msg
    if msg:
        return f"{name}: {msg[:200]}"
    return f"{name} (see backend logs for details)."


def _normalize_facebook_url(url: str | None) -> str | None:
    """Normalize and validate a URL that must point to Facebook."""
    if not url:
        return None

    candidate = url.strip()
    if not candidate:
        return None
    if not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate}"

    try:
        parsed = urlparse(candidate)
    except Exception:
        return None

    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return None

    is_facebook = host == "facebook.com" or host.endswith(".facebook.com")
    is_fb_watch = host == "fb.watch" or host.endswith(".fb.watch")
    if not (is_facebook or is_fb_watch):
        return None

    return candidate
