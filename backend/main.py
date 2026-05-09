import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from auth import save_credentials, credentials_exist, load_credentials
from session import session_exists, clear_session
from llm import parse_intent, generate_post_text, generate_comment_text, build_agent_task

load_dotenv()

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


# ── Routes ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status/setup")
def setup_status():
    """Tell the frontend what's already configured."""
    return {
        "credentials_saved": credentials_exist(),
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

    tasks[body.task_id] = {"status": "processing", "result": None, "error": None}
    background_tasks.add_task(run_task, body.task_id, body.message)

    return {"task_id": body.task_id, "status": "processing"}


@app.get("/task/{task_id}")
def get_task_status(task_id: str):
    """Poll this to get the result of a chat command."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found.")
    return tasks[task_id]


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

        # Step 4: run the agent (import here to avoid circular + lazy load)
        from agent import run_fb_task
        result = await run_fb_task(agent_task)

        tasks[task_id] = {
            "status": "done",
            "result": result,
            "generated_content": content,
            "action": action,
            "error": None,
        }

    except Exception as e:
        tasks[task_id] = {
            "status": "error",
            "result": None,
            "error": str(e),
        }