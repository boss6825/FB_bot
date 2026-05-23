import asyncio
import logging
import os
import re
from pathlib import Path

from stagehand import AsyncStagehand
from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

logger = logging.getLogger("fb_agent.agent")

FB_URL = "https://www.facebook.com"
STAGEHAND_MODEL = os.getenv("STAGEHAND_MODEL", "anthropic/claude-sonnet-4-6")
CAPTCHA_WAIT_SECONDS = int(os.getenv("STAGEHAND_CAPTCHA_WAIT_SECONDS", "600"))
CAPTCHA_RESUME_SECONDS = 30
# How long the manual-login Browserbase session is allowed to stay open
# (in seconds).  The user needs enough time to handle Facebook OTP / 2FA /
# email-verification flows, so give them a generous window.
LOGIN_SESSION_TIMEOUT_SECONDS = int(os.getenv("STAGEHAND_LOGIN_TIMEOUT_SECONDS", "1800"))


def _extract_data(result) -> dict:
    if hasattr(result, "data") and isinstance(result.data, dict):
        return result.data
    return {}


async def _get_facebook_state(client: AsyncStagehand, session_id: str) -> dict:
    """Classify the current Facebook page."""
    try:
        result = await client.sessions.extract(
            session_id,
            instruction=(
                "Classify the current Facebook page. Say whether it is the logged-in "
                "home/feed, a normal login page, a captcha/security challenge page, "
                "a checkpoint/identity verification page, or something else."
            ),
            schema={
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "enum": ["feed", "login", "captcha", "checkpoint", "other"],
                    },
                    "details": {
                        "type": "string",
                        "description": "Short visible reason for the classification",
                    },
                },
                "required": ["state"],
            },
        )
        data = _extract_data(result)
        if data.get("state") in {"feed", "login", "captcha", "checkpoint", "other"}:
            return data
    except Exception:
        logger.debug("Could not determine Facebook page state", exc_info=True)

    return {"state": "other", "details": "Could not classify page state"}


async def _is_logged_in(client: AsyncStagehand, session_id: str) -> bool:
    """Check if the current page shows the Facebook feed (logged in)."""
    state = await _get_facebook_state(client, session_id)
    return state.get("state") == "feed"


# ── Login session management (user logs in manually) ─────────────

async def start_login_session(context_id: str) -> dict:
    """Start a Browserbase session for manual Facebook login.

    Creates the session directly via Browserbase REST (bypassing Stagehand)
    so our backend isn't holding a Playwright connection that Browserbase
    would tear down a few seconds after the HTTP request returns.

    Returns { session_id, session_url, live_view_url, connect_url, context_id }.
    The session stays alive (keepAlive=True) until verified or cancelled.
    """
    from session import (
        create_browserbase_session,
        get_session_debug_urls,
    )

    session_info = await create_browserbase_session(
        context_id=context_id,
        keep_alive=True,
        timeout_seconds=LOGIN_SESSION_TIMEOUT_SECONDS,
    )
    session_id = session_info["id"]
    connect_url = session_info.get("connectUrl")
    logger.info(
        "Login session started: %s (keepAlive=True, timeout=%ds)",
        session_id, LOGIN_SESSION_TIMEOUT_SECONDS,
    )

    # We can't pre-navigate without Playwright/Stagehand attaching (which
    # would create the same "Stagehand drops connection" problem).  The
    # iframe will load whatever page the browser is on; we tell the user
    # to navigate to facebook.com from a small banner.  In practice
    # Browserbase opens a blank page; we surface this URL to the frontend
    # so it can encourage the user to navigate.

    live_view_url = None
    try:
        debug = await get_session_debug_urls(session_id)
        # Prefer the chrome version (has a URL bar) so the user can navigate
        # to facebook.com themselves — we no longer pre-navigate because
        # doing so via Stagehand/Playwright would re-introduce the
        # connection-drop bug that killed the session in 3–4 seconds.
        live_view_url = (
            debug.get("debuggerUrl")
            or debug.get("debuggerFullscreenUrl")
            or debug.get("liveViewUrl")
        )
    except Exception:
        logger.warning("Could not fetch live-view URL for %s", session_id, exc_info=True)

    return {
        "session_id": session_id,
        "session_url": f"https://www.browserbase.com/sessions/{session_id}",
        "live_view_url": live_view_url,
        "connect_url": connect_url,
        "context_id": context_id,
    }


async def verify_login_session(session_id: str) -> dict:
    """Optimistic verify: trust the user clicked 'I'm Logged In'.

    We can't inspect the page without re-attaching a Playwright/Stagehand
    client (which is what was killing the session earlier).  Cookies are
    persisted to the context when the session ends; if the user actually
    didn't log in, the next automation task will fail with 'Login expired'
    and they can re-run the login flow.
    """
    return {"logged_in": True, "state": "feed", "details": "optimistic"}


async def end_session(session_id: str) -> None:
    """End a Browserbase session via REST."""
    from session import release_browserbase_session
    await release_browserbase_session(session_id)
    logger.info("Session released: %s", session_id)


# ── Task parsing ─────────────────────────────────────────────────

def _parse_task(task_description: str) -> tuple[str, str, str | None]:
    """Parse a task string built by build_agent_task() into (action, content, url)."""
    lower = task_description.lower()

    # Extract quoted content
    quotes = re.findall(r'"([^"]*)"', task_description)
    content = quotes[0] if quotes else task_description

    if "create a new facebook post" in lower:
        return "post", content, None

    if "leave a comment" in lower:
        url_match = re.search(r"https?://\S+", task_description)
        url = url_match.group(0).rstrip('"') if url_match else None
        return "comment", content, url

    return "generic", content, None


# ── Action handlers ──────────────────────────────────────────────

async def _do_post(client: AsyncStagehand, session_id: str, content: str) -> str:
    """Create a Facebook post."""
    logger.info("Creating Facebook post...")

    await client.sessions.act(
        session_id,
        input=(
            "Click on 'What's on your mind?' or the create post area "
            "to open the post composer dialog"
        ),
    )
    await asyncio.sleep(2)

    await client.sessions.act(
        session_id,
        input=f'Type the following text into the post composer text area: "{content}"',
    )
    await asyncio.sleep(1)

    await client.sessions.act(
        session_id,
        input="Click the Post button to publish the post",
    )
    await asyncio.sleep(3)

    return "Post published successfully."


async def _do_comment(
    client: AsyncStagehand,
    session_id: str,
    target_url: str | None,
    content: str,
) -> str:
    """Comment on a Facebook post."""
    logger.info("Commenting on Facebook post: %s", target_url)

    if target_url:
        await client.sessions.navigate(session_id, url=target_url)
        await asyncio.sleep(3)

    await client.sessions.act(
        session_id,
        input="Click on the comment input field or 'Write a comment' area",
    )
    await asyncio.sleep(1)

    await client.sessions.act(
        session_id,
        input=f'Type the following comment: "{content}"',
    )
    await asyncio.sleep(1)

    await client.sessions.act(
        session_id,
        input="Press Enter or click the submit button to post the comment",
    )
    await asyncio.sleep(2)

    return "Comment posted successfully."


async def _do_generic(
    client: AsyncStagehand, session_id: str, task: str
) -> str:
    """Handle generic Facebook tasks using Stagehand execute (agentic mode)."""
    logger.info("Executing generic task...")

    await client.sessions.execute(
        session_id,
        agent_config={"model": STAGEHAND_MODEL, "mode": "hybrid"},
        execute_options={"instruction": task, "max_steps": 20},
    )
    return "Task completed successfully."


# ── Main entry point ─────────────────────────────────────────────

async def run_fb_task(
    task_description: str,
    context_id: str,
    on_captcha=None,
) -> str:
    """Run a Facebook task using a persisted context (user already logged in).

    If the session is no longer logged in (cookies expired), returns an error
    prompting the user to log in again.  If a CAPTCHA/checkpoint appears,
    the on_captcha callback is used to notify the user.
    """
    client = AsyncStagehand()
    session = None

    try:
        session = await client.sessions.start(
            model_name=STAGEHAND_MODEL,
            wait_for_captcha_solves=True,
            browserbase_session_create_params={
                "browser_settings": {
                    "context": {"id": context_id, "persist": True},
                    "solve_captchas": True,
                    "record_session": True,
                },
            },
        )
        session_id = session.id
        logger.info("Task session started: %s", session_id)
        logger.info("Debug URL: https://www.browserbase.com/sessions/%s", session_id)

        # Navigate to Facebook
        await client.sessions.navigate(session_id, url=FB_URL)
        await asyncio.sleep(3)

        # Check login status (cookies should be restored from context)
        state_info = await _get_facebook_state(client, session_id)
        state = state_info.get("state")

        if state in {"captcha", "checkpoint"}:
            if on_captcha:
                logger.info("CAPTCHA/checkpoint detected before action: %s", state)
                event = await on_captcha(
                    session_id, state, state_info.get("details", "")
                )
                try:
                    await asyncio.wait_for(
                        event.wait(), timeout=CAPTCHA_WAIT_SECONDS
                    )
                except asyncio.TimeoutError:
                    return f"CAPTCHA was not solved within {CAPTCHA_WAIT_SECONDS}s. Please try again."
                await asyncio.sleep(CAPTCHA_RESUME_SECONDS)
                # Re-check login
                if not await _is_logged_in(client, session_id):
                    return "Login expired. Please log in to Facebook again via Settings."
            else:
                return "Login expired (security challenge). Please log in to Facebook again via Settings."

        elif state != "feed":
            return "Login expired. Please log in to Facebook again via Settings."

        # Execute the action
        action, content, target_url = _parse_task(task_description)

        if action == "post":
            return await _do_post(client, session_id, content)
        elif action == "comment":
            return await _do_comment(client, session_id, target_url, content)
        else:
            return await _do_generic(client, session_id, task_description)

    except Exception:
        logger.exception("Agent run failed")
        return "Agent failed during execution. Check the backend logs."
    finally:
        if session:
            try:
                await client.sessions.end(session.id)
                logger.info("Task session ended.")
            except Exception:
                pass
