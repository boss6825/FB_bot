import logging
import os
from pathlib import Path

from browser_use import Agent, BrowserSession
from browser_use.llm import ChatAnthropic
from dotenv import load_dotenv

from session import SESSION_FILE, load_session, save_session
from auth import load_credentials
from config import ANTHROPIC_MODEL

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

logger = logging.getLogger("fb_agent.agent")

FB_URL = "https://www.facebook.com"
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").strip().lower() in {"1", "true", "yes", "on"}
BROWSER_KEEP_OPEN = os.getenv("BROWSER_KEEP_OPEN", "false").strip().lower() in {"1", "true", "yes", "on"}
BROWSER_USER_DATA_DIR = os.getenv(
    "BROWSER_USER_DATA_DIR",
    str(Path(__file__).parent / "storage" / "tmp-browser-use-profile"),
)


def _build_task(task_description: str, has_session: bool) -> str:
    """
    Wrap the user's task with a login-aware preface.

    Credentials are referenced via placeholders (fb_email / fb_password). browser-use
    substitutes the real values only when typing into the page — the LLM never sees
    the actual email/password.
    """
    efficiency_rules = (
        "EFFICIENCY RULES (critical — follow strictly):\n"
        "- Return MULTIPLE actions in a single response whenever the next steps are "
        "predictable from the current screen. Do not stop after each action.\n"
        "- On the Facebook login page, emit ONE response containing all three actions: "
        "type `fb_email` into the email field, type `fb_password` into the password field, "
        "then click the Log In button. Do not split this across separate responses.\n"
        "- For the composer flow, emit ONE response containing: click the 'What's on your "
        "mind' opener, type the post text, then click Post. Do not split.\n"
        "- Only break the batch if you actually need to read new page state (e.g. a "
        "checkpoint, 2FA, or unexpected dialog appears).\n"
        "- DONE CONDITION: the moment the requested action is visibly performed (post "
        "appears in feed, message sent, comment submitted, etc.), call the `done` tool "
        "immediately with success=true. Do not keep verifying or navigating.\n"
        "- If the composer is already open and the Post button is enabled, click Post "
        "immediately and finish.\n"
    )

    login_block = (
        "If a login screen, checkpoint, or any sign-in prompt appears, log in in a single "
        "batched response: type `fb_email` into the email field, type `fb_password` into "
        "the password field, and click the Log In button — all three actions in ONE model "
        "response. Then wait for the Facebook home feed to load before continuing."
    )

    if has_session:
        preface = (
            f"You are operating an existing logged-in Facebook session. "
            f"Start by navigating to {FB_URL}.\n"
            f"If the saved session has expired: {login_block}\n"
            "Otherwise proceed straight to the task.\n"
        )
    else:
        preface = (
            f"You need to log in to Facebook first. Navigate to {FB_URL}.\n"
            f"{login_block}\n"
            "Once logged in, perform the task below.\n"
        )

    return f"{preface}\n{efficiency_rules}\nTask:\n{task_description}"


async def run_fb_task(task_description: str) -> str:
    """
    Main entry point. Given a plain-English task, run it on Facebook.
    browser-use handles login (and session refresh) end-to-end.
    """
    creds = load_credentials()
    if not creds:
        return "Login failed: no Facebook credentials saved."

    session_state = load_session()
    has_session = session_state is not None

    storage_state_arg = str(SESSION_FILE) if has_session else None
    browser_session = BrowserSession(
        storage_state=storage_state_arg,
        user_data_dir=BROWSER_USER_DATA_DIR,
        headless=BROWSER_HEADLESS,
        keep_alive=BROWSER_KEEP_OPEN,
    )

    llm = ChatAnthropic(model=ANTHROPIC_MODEL)
    full_task = _build_task(task_description, has_session=has_session)

    try:
        agent = Agent(
            task=full_task,
            llm=llm,
            browser=browser_session,
            sensitive_data={
                "fb_email": creds["email"],
                "fb_password": creds["password"],
            },
            use_thinking=False,
            flash_mode=True,
            enable_planning=False,
            max_actions_per_step=10,
        )

        history = await agent.run(max_steps=35)
        final_result = history.final_result()

        if history.has_errors() and not history.is_done():
            last_error = next((err for err in reversed(history.errors()) if err), None)
            return f"Agent failed before completion: {last_error}" if last_error else "Agent failed before completion."

        if not history.is_done():
            return "Agent stopped before confirming the task was done."

        # Persist any cookie/session changes made during the task.
        try:
            updated_state = await browser_session.export_storage_state()
            if updated_state:
                save_session(updated_state)
        except Exception:
            logger.exception("Could not export storage_state after agent run")

        return final_result or "Task completed."

    except Exception:
        logger.exception("Agent run failed")
        return "Agent failed during execution. Check the backend logs."
    finally:
        if not BROWSER_KEEP_OPEN:
            try:
                await browser_session.stop()
            except Exception:
                pass
