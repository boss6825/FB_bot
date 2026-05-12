import asyncio
import logging
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks

# Playwright needs subprocess support; SelectorEventLoop on Windows doesn't have it.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = logging.getLogger("fb_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from auth import save_credentials, credentials_exist, credentials_valid, load_credentials
from session import session_exists, clear_session
from llm import parse_intent, generate_post_text, generate_comment_text, build_agent_task

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

# In-memory task store for status polling
# key: task_id, value: { status, result, error }
tasks: dict[str, dict] = {}


# ── Request models ────────────────────────────────────────────────

class CredentialsRequest(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    message: str
    task_id: str  # client generates this (e.g. uuid)


class PublishDraftRequest(BaseModel):
    text: str


# ── Routes ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status/setup")
def setup_status():
    """Tell the frontend what's already configured."""
    return {
        "credentials_saved": credentials_exist(),
        "credentials_valid": credentials_valid(),
        "session_active": session_exists(),
    }


@app.post("/auth/credentials")
def set_credentials(body: CredentialsRequest):
    """Save (encrypted) Facebook credentials. Call once from onboarding UI."""
    if not body.email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password required.")
    save_credentials(body.email, body.password)
    # Clear old session so next task triggers fresh login with new creds
    clear_session()
    return {"message": "Credentials saved successfully."}


@app.post("/auth/logout")
def logout():
    """Wipe saved session (forces re-login on next task)."""
    clear_session()
    return {"message": "Session cleared."}


@app.post("/chat")
async def chat(body: ChatRequest, background_tasks: BackgroundTasks):
    """
    Receive a natural language command, parse intent, generate content,
    and kick off the browser-use agent in the background.
    Returns immediately with task_id for polling.
    """
    if not credentials_exist():
        raise HTTPException(
            status_code=400,
            detail="No Facebook credentials saved. Please set up credentials first."
        )
    if not credentials_valid():
        raise HTTPException(
            status_code=400,
            detail="Saved credentials are unreadable/invalid. Please save credentials again."
        )

    tasks[body.task_id] = {"status": "processing", "result": None, "error": None}
    background_tasks.add_task(run_task, body.task_id, body.message)

    return {"task_id": body.task_id, "status": "processing"}


@app.get("/task/{task_id}")
def get_task_status(task_id: str):
    """Poll this to get the result of a chat command."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found.")
    return tasks[task_id]


@app.post("/draft")
async def create_draft_endpoint(body: ChatRequest, background_tasks: BackgroundTasks):
    """
    Parse intent and generate post/comment text — but do NOT run the browser yet.
    Returns immediately; poll /task/{task_id} until status == 'draft'.
    """
    if not credentials_exist():
        raise HTTPException(status_code=400, detail="No Facebook credentials saved. Please set up credentials first.")
    if not credentials_valid():
        raise HTTPException(status_code=400, detail="Saved credentials are unreadable/invalid. Please save credentials again.")

    tasks[body.task_id] = {
        "status": "processing",
        "result": None,
        "error": None,
        "generated_content": None,
        "action": None,
        "intent": None,
    }
    background_tasks.add_task(create_draft, body.task_id, body.message)
    return {"task_id": body.task_id, "status": "processing"}


@app.post("/draft/{draft_id}/publish")
async def publish_draft(draft_id: str, body: PublishDraftRequest, background_tasks: BackgroundTasks):
    """
    Take user-confirmed (and optionally edited) text and run the browser agent.
    Poll /task/{draft_id} until status == 'done' or 'error'.
    """
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


# ── Background task runner ────────────────────────────────────────

async def run_task(task_id: str, message: str):
    """Parse intent, generate content, run browser agent."""
    try:
        # Step 1: parse what the user wants
        intent = parse_intent(message)
        action = intent.get("action", "unknown")
        brief = intent.get("content_brief", message)
        target_url = intent.get("target_url")

        if action == "unknown":
            tasks[task_id] = {
                "status": "done",
                "result": "I couldn't understand what you want to do on Facebook. Try something like 'post about X' or 'comment on <url> saying Y'.",
                "error": None,
            }
            return

        # Step 2: generate the actual text
        if action == "post":
            content = generate_post_text(brief)
        elif action == "comment":
            content = generate_comment_text(brief)
        else:
            content = brief

        # Step 3: build the browser-use task string
        agent_task = build_agent_task(action, content, target_url)

        # Step 4: run the agent in a dedicated thread with a Proactor loop.
        # On Windows, asyncio.create_subprocess_exec (used by Playwright) requires
        # ProactorEventLoop. Spawning a fresh loop in a worker thread guarantees this
        # regardless of how uvicorn configured the main loop.
        from agent import run_fb_task

        def _run_in_thread() -> str:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(run_fb_task(agent_task))
            finally:
                loop.close()

        result = await asyncio.to_thread(_run_in_thread)
        failure_prefixes = (
            "Login failed",
            "Agent failed",
            "Agent stopped",
        )
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
            "error": None,
        }

    except Exception as e:
        # Log full traceback to backend console only; never leak it to the client.
        logger.exception("Task %s failed", task_id)
        tasks[task_id] = {
            "status": "error",
            "result": None,
            "error": _user_facing_error(e),
        }


async def create_draft(task_id: str, message: str):
    """Parse intent and generate text; stop before browser automation."""
    try:
        intent = parse_intent(message)
        action = intent.get("action", "unknown")
        brief = intent.get("content_brief", message)

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
        })
    except Exception as e:
        logger.exception("Draft %s failed", task_id)
        tasks[task_id].update({
            "status": "error",
            "error": _user_facing_error(e),
        })


async def publish_task(task_id: str, content: str, action: str, target_url: str | None):
    """Build agent task string and run browser automation with user-confirmed text."""
    try:
        agent_task = build_agent_task(action, content, target_url)

        from agent import run_fb_task

        def _run_in_thread() -> str:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(run_fb_task(agent_task))
            finally:
                loop.close()

        result = await asyncio.to_thread(_run_in_thread)
        failure_prefixes = ("Login failed", "Agent failed", "Agent stopped")
        is_failure = any(result.startswith(p) for p in failure_prefixes)

        if is_failure:
            tasks[task_id].update({"status": "error", "result": None, "error": result})
            return

        tasks[task_id].update({"status": "done", "result": result, "error": None})

    except Exception as e:
        logger.exception("Publish task %s failed", task_id)
        tasks[task_id].update({"status": "error", "result": None, "error": _user_facing_error(e)})


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
