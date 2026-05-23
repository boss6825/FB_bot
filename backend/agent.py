import asyncio
import sys
import threading
import logging
import os
from pathlib import Path
from typing import Any

from browser_use import Agent, BrowserSession
from browser_use.llm import ChatAnthropic
from dotenv import load_dotenv

from session import SESSION_FILE, load_session, save_session
from config import (
    ANTHROPIC_MODEL,
    BROWSER_CHANNEL,
    BROWSER_USER_AGENT,
    BROWSER_USER_DATA_DIR,
)

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

logger = logging.getLogger("fb_agent.agent")

FB_URL = "https://www.facebook.com"
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").strip().lower() in {"1", "true", "yes", "on"}
BROWSER_KEEP_OPEN = os.getenv("BROWSER_KEEP_OPEN", "false").strip().lower() in {"1", "true", "yes", "on"}

POST_CLICK_FALLBACK_ATTEMPTS = 3
POST_CLICK_FALLBACK_SLEEP_SECONDS = 1.2
COMMENT_CLICK_FALLBACK_ATTEMPTS = 3
COMMENT_CLICK_FALLBACK_SLEEP_SECONDS = 1.0

_manual_login_sessions: dict[str, dict[str, Any]] = {}
_browser_loop: asyncio.AbstractEventLoop | None = None
_browser_loop_ready = threading.Event()
_browser_loop_lock = threading.Lock()


def _browser_launch_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "headless": False,
        "viewport": {"width": 1365, "height": 900},
    }
    if BROWSER_CHANNEL:
        kwargs["channel"] = BROWSER_CHANNEL
    return kwargs


def _browser_loop_thread() -> None:
    global _browser_loop
    if sys.platform == "win32" and hasattr(asyncio, "ProactorEventLoop"):
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _browser_loop = loop
    _browser_loop_ready.set()
    loop.run_forever()


def _get_browser_loop() -> asyncio.AbstractEventLoop:
    global _browser_loop
    with _browser_loop_lock:
        if _browser_loop and _browser_loop.is_running():
            return _browser_loop

        _browser_loop_ready.clear()
        thread = threading.Thread(
            target=_browser_loop_thread,
            name="playwright-login-loop",
            daemon=True,
        )
        thread.start()
        _browser_loop_ready.wait(timeout=10)
        if not _browser_loop or not _browser_loop.is_running():
            raise RuntimeError("Could not start Playwright browser loop.")
        return _browser_loop


async def _run_on_browser_loop(coro):
    try:
        if asyncio.get_running_loop() is _browser_loop:
            return await coro
    except RuntimeError:
        pass

    future = asyncio.run_coroutine_threadsafe(coro, _get_browser_loop())
    return await asyncio.wrap_future(future)


async def start_login_session(context_id: str | None = None) -> dict:
    return await _run_on_browser_loop(_start_login_session_local(context_id))


async def _start_login_session_local(context_id: str | None = None) -> dict:
    """Open a local browser window for manual Facebook login."""
    import uuid
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=BROWSER_USER_DATA_DIR,
        **_browser_launch_kwargs(),
    )
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(FB_URL, wait_until="domcontentloaded")

    session_id = str(uuid.uuid4())
    _manual_login_sessions[session_id] = {
        "playwright": playwright,
        "context": context,
    }
    logger.info("Local login browser opened: %s", session_id)

    return {
        "session_id": session_id,
        "session_url": None,
        "live_view_url": None,
        "mode": "local_browser",
    }


async def verify_login_session(session_id: str) -> dict:
    return await _run_on_browser_loop(_verify_login_session_local(session_id))


async def _verify_login_session_local(session_id: str) -> dict:
    """Persist local browser cookies after the user confirms login."""
    session = _manual_login_sessions.get(session_id)
    if not session:
        return {"logged_in": False, "state": "other", "details": "Login browser is not active."}

    context = session["context"]
    cookies = await context.cookies(FB_URL)
    logged_in = any(cookie.get("name") == "c_user" for cookie in cookies)
    if not logged_in:
        return {
            "logged_in": False,
            "state": "login",
            "details": "Facebook login cookie was not found yet.",
        }

    await context.storage_state(path=str(SESSION_FILE))
    await _end_session_local(session_id)
    return {"logged_in": True, "state": "feed", "details": "Saved local browser session."}


async def end_session(session_id: str) -> None:
    await _run_on_browser_loop(_end_session_local(session_id))


async def _end_session_local(session_id: str) -> None:
    """Close a local manual-login browser session."""
    session = _manual_login_sessions.pop(session_id, None)
    if not session:
        return
    try:
        await session["context"].close()
    finally:
        await session["playwright"].stop()
        logger.info("Local login browser closed: %s", session_id)


def _is_post_publish_task(task_description: str) -> bool:
    text = task_description.lower()
    return "create a new facebook post" in text and "click the post button" in text


def _is_comment_publish_task(task_description: str) -> bool:
    text = task_description.lower()
    return "leave a comment with exactly this text" in text and "click the comment button" in text


async def _evaluate_js(browser_session: BrowserSession, expression: str) -> Any:
    cdp_session = await browser_session.get_or_create_cdp_session()
    result = await cdp_session.cdp_client.send.Runtime.evaluate(
        params={"expression": expression, "returnByValue": True, "awaitPromise": True},
        session_id=cdp_session.session_id,
    )
    if result.get("exceptionDetails"):
        raise RuntimeError(result["exceptionDetails"].get("text", "JavaScript evaluation failed"))
    return result.get("result", {}).get("value")


async def _dispatch_cdp_mouse_click(browser_session: BrowserSession, x: float, y: float) -> None:
    cdp_session = await browser_session.get_or_create_cdp_session()
    for event_type in ("mouseMoved", "mousePressed", "mouseReleased"):
        params: dict[str, Any] = {
            "type": event_type,
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        }
        if event_type == "mousePressed":
            params["buttons"] = 1
        await cdp_session.cdp_client.send.Input.dispatchMouseEvent(
            params=params,
            session_id=cdp_session.session_id,
        )


async def _composer_has_visible_post_button(browser_session: BrowserSession) -> bool:
    script = r"""
(() => {
  const isVisible = (el) => !!el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
  const isEnabled = (el) => !!el && el.getAttribute('aria-disabled') !== 'true';
  const candidates = [
    ...document.querySelectorAll('div[role="button"][aria-label="Post"], button[aria-label="Post"], [role="button"][aria-label="Post"]'),
    ...[...document.querySelectorAll('div[role="button"],button')].filter(el => (el.textContent || '').trim() === 'Post')
  ];
  return candidates.some(el => isVisible(el) && isEnabled(el));
})()
"""
    value = await _evaluate_js(browser_session, script)
    return bool(value)


async def _force_click_post_button(browser_session: BrowserSession) -> tuple[bool, str]:
    locate_script = r"""
(() => {
  const isVisible = (el) => !!el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
  const isEnabled = (el) => !!el && el.getAttribute('aria-disabled') !== 'true';
  const describe = (el, strategy) => {
    el.scrollIntoView({ block: 'center', inline: 'center' });
    const rect = el.getBoundingClientRect();
    return {
      found: true,
      strategy,
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
      width: rect.width,
      height: rect.height
    };
  };

  const selectorCandidates = [
    'div[role="button"][aria-label="Post"]',
    'button[aria-label="Post"]',
    '[role="button"][aria-label="Post"]'
  ];

  for (const selector of selectorCandidates) {
    const nodes = [...document.querySelectorAll(selector)];
    for (const node of nodes) {
      if (isVisible(node) && isEnabled(node)) {
        return describe(node, selector);
      }
    }
  }

  const textMatches = [...document.querySelectorAll('div[role="button"],button')]
    .filter(el => (el.textContent || '').trim() === 'Post');
  for (const node of textMatches) {
    if (isVisible(node) && isEnabled(node)) {
      return describe(node, 'text-content');
    }
  }

  return { found: false, strategy: 'none' };
})()
"""

    before_visible = await _composer_has_visible_post_button(browser_session)
    if not before_visible:
        return False, "No visible Post button found in composer before fallback click."

    for attempt in range(1, POST_CLICK_FALLBACK_ATTEMPTS + 1):
        value = await _evaluate_js(browser_session, locate_script)
        logger.info("Post-click fallback attempt %s target: %s", attempt, value)
        if not value or not value.get("found"):
            await asyncio.sleep(POST_CLICK_FALLBACK_SLEEP_SECONDS)
            continue
        await _dispatch_cdp_mouse_click(browser_session, float(value["x"]), float(value["y"]))
        await asyncio.sleep(POST_CLICK_FALLBACK_SLEEP_SECONDS)

        after_visible = await _composer_has_visible_post_button(browser_session)
        if not after_visible:
            return True, f"Deterministic Post click succeeded via fallback (attempt {attempt})."

    return False, "Post button remained visible after deterministic fallback clicks."


async def _comment_composer_has_visible_submit_button(browser_session: BrowserSession) -> bool:
    script = r"""
(() => {
  const isVisible = (el) => !!el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
  const isEnabled = (el) => !!el && el.getAttribute('aria-disabled') !== 'true' && !(el.disabled === true);
  const directCandidates = [
    ...document.querySelectorAll('div[role="button"][aria-label="Comment"], button[aria-label="Comment"], [role="button"][aria-label="Comment"]')
  ];
  const textCandidates = [...document.querySelectorAll('div[role="button"],button')]
    .filter(el => (el.textContent || '').trim() === 'Comment');
  const candidates = [...directCandidates, ...textCandidates];
  return candidates.some(el => isVisible(el) && isEnabled(el));
})()
"""
    value = await _evaluate_js(browser_session, script)
    return bool(value)


async def _force_click_comment_button(browser_session: BrowserSession) -> tuple[bool, str]:
    locate_script = r"""
(() => {
  const isVisible = (el) => !!el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
  const isEnabled = (el) => !!el && el.getAttribute('aria-disabled') !== 'true' && !(el.disabled === true);
  const describe = (el, strategy) => {
    el.scrollIntoView({ block: 'center', inline: 'center' });
    const rect = el.getBoundingClientRect();
    return {
      found: true,
      strategy,
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
      width: rect.width,
      height: rect.height
    };
  };

  const selectorCandidates = [
    'div[role="button"][aria-label="Comment"]',
    'button[aria-label="Comment"]',
    '[role="button"][aria-label="Comment"]'
  ];

  for (const selector of selectorCandidates) {
    const nodes = [...document.querySelectorAll(selector)];
    for (const node of nodes) {
      if (isVisible(node) && isEnabled(node)) {
        return describe(node, selector);
      }
    }
  }

  const textMatches = [...document.querySelectorAll('div[role="button"],button')]
    .filter(el => (el.textContent || '').trim() === 'Comment');
  for (const node of textMatches) {
    if (isVisible(node) && isEnabled(node)) {
      return describe(node, 'text-content');
    }
  }

  return { found: false, strategy: 'none' };
})()
"""

    before_visible = await _comment_composer_has_visible_submit_button(browser_session)
    if not before_visible:
        return False, "No visible Comment submit button found before fallback click."

    for attempt in range(1, COMMENT_CLICK_FALLBACK_ATTEMPTS + 1):
        value = await _evaluate_js(browser_session, locate_script)
        logger.info("Comment-click fallback attempt %s target: %s", attempt, value)
        if value and value.get("found"):
            await _dispatch_cdp_mouse_click(browser_session, float(value["x"]), float(value["y"]))
            await asyncio.sleep(COMMENT_CLICK_FALLBACK_SLEEP_SECONDS)
            return True, f"Deterministic Comment click executed via fallback (attempt {attempt})."

    return False, "Comment submit fallback could not click any visible Comment button."


async def _persist_session_state(browser_session: BrowserSession) -> None:
    try:
        updated_state = await browser_session.export_storage_state()
        if updated_state:
            save_session(updated_state)
    except Exception:
        logger.exception("Could not export storage_state after agent run")


def _build_task(task_description: str, has_session: bool) -> str:
    """
    Wrap the user's task with a login-aware preface.

    The app requires a manually saved session. If Facebook asks for login again,
    stop and tell the user to reconnect.
    """
    efficiency_rules = (
        "EFFICIENCY RULES (critical — follow strictly):\n"
        "- Return MULTIPLE actions in a single response whenever the next steps are "
        "predictable from the current screen. Do not stop after each action.\n"
        "- For the composer flow, emit ONE response containing: click the 'What's on your "
        "mind' opener, type the post text, then click Post. Do not split.\n"
        "- Only break the batch if you actually need to read new page state (e.g. a "
        "checkpoint, 2FA, or unexpected dialog appears).\n"
        "- DONE CONDITION: the moment the requested action is visibly performed (post "
        "appears in feed, message sent, comment submitted, etc.), call the `done` tool "
        "immediately with success=true. Do not keep verifying or navigating.\n"
        "- If the composer is already open and the Post button is enabled, click Post "
        "immediately and finish.\n"
        "- RECOVERY RULE: if a click on Post fails with 'Element index ... not available', "
        "do not retry the same index. Switch to the evaluate action immediately and click "
        "Post by stable selector/text.\n"
        "- VALID ACTION FORMAT: action objects must use browser-use action names and fields "
        "(example: {'click': {'index': 123}}). Never use unknown fields like "
        "{'click': {'element_index': 123}}.\n"
        "- POST CONTENT RULE: do not alter text content, do not add emojis, and do not open "
        "'Add to your post' menus unless strictly required.\n"
        "- COMMENT FLOW RULE: when task is to comment on a specific post URL, stay on that exact "
        "target post page, type the exact provided comment text, then submit comment.\n"
        "- COMMENT RECOVERY RULE: if comment submission click fails with 'Element index ... not "
        "available', switch to evaluate action and click a visible Comment submit button by stable "
        "selector/text instead of retrying stale indices.\n"
    )

    login_block = (
        "If a login screen, checkpoint, captcha, identity check, or any sign-in prompt "
        "appears, stop immediately and report that the user must reconnect Facebook "
        "manually from Settings. Do not enter credentials or try to solve challenges."
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


async def run_fb_task(task_description: str, context_id: str | None = None, on_captcha=None) -> str:
    return await _run_on_browser_loop(_run_fb_task_local(task_description, context_id, on_captcha))


async def _run_fb_task_local(task_description: str, context_id: str | None = None, on_captcha=None) -> str:
    """
    Main entry point. Given a plain-English task, run it on Facebook.
    browser-use operates the locally saved manual-login browser profile.
    """
    session_state = load_session()
    has_session = session_state is not None
    if not has_session:
        return "Login expired. Please log in to Facebook again via Settings."

    session_kwargs: dict[str, Any] = {
        # The manual login flow uses a persistent Chrome profile. Passing
        # storage_state as well makes browser-use overwrite that profile.
        "storage_state": None,
        "user_data_dir": BROWSER_USER_DATA_DIR,
        "headless": BROWSER_HEADLESS,
        "keep_alive": BROWSER_KEEP_OPEN,
    }
    if BROWSER_CHANNEL:
        session_kwargs["channel"] = BROWSER_CHANNEL
    if BROWSER_USER_AGENT:
        session_kwargs["user_agent"] = BROWSER_USER_AGENT

    browser_session = BrowserSession(**session_kwargs)

    llm = ChatAnthropic(model=ANTHROPIC_MODEL)
    full_task = _build_task(task_description, has_session=has_session)
    is_publish_task = _is_post_publish_task(task_description) or _is_comment_publish_task(task_description)
    max_steps = 18 if is_publish_task else 35
    deterministic_result: dict[str, str | None] = {"message": None}

    async def click_publish_button_when_ready(agent: Agent) -> None:
        if deterministic_result["message"] or agent.history.is_done():
            return

        try:
            if _is_post_publish_task(task_description) and await _composer_has_visible_post_button(browser_session):
                clicked, fallback_message = await _force_click_post_button(browser_session)
            elif (
                _is_comment_publish_task(task_description)
                and await _comment_composer_has_visible_submit_button(browser_session)
            ):
                clicked, fallback_message = await _force_click_comment_button(browser_session)
            else:
                return
        except Exception:
            logger.exception("Deterministic publish click during agent step failed")
            return

        if clicked:
            deterministic_result["message"] = fallback_message
            agent.stop()

    try:
        agent = Agent(
            task=full_task,
            llm=llm,
            browser=browser_session,
            use_thinking=False,
            flash_mode=True,
            enable_planning=False,
            max_actions_per_step=10,
            max_failures=2,
            final_response_after_failure=False,
            include_tool_call_examples=True,
        )

        history = await agent.run(max_steps=max_steps, on_step_end=click_publish_button_when_ready)
        final_result = history.final_result()

        if deterministic_result["message"]:
            await _persist_session_state(browser_session)
            return deterministic_result["message"] or "Task completed."

        if not history.is_done():
            if _is_post_publish_task(task_description):
                try:
                    clicked, fallback_message = await _force_click_post_button(browser_session)
                    if clicked:
                        await _persist_session_state(browser_session)
                        return fallback_message
                    logger.warning("Post publish fallback did not complete: %s", fallback_message)
                except Exception:
                    logger.exception("Deterministic post publish fallback failed")
            elif _is_comment_publish_task(task_description):
                try:
                    clicked, fallback_message = await _force_click_comment_button(browser_session)
                    if clicked:
                        await _persist_session_state(browser_session)
                        return fallback_message
                    logger.warning("Comment publish fallback did not complete: %s", fallback_message)
                except Exception:
                    logger.exception("Deterministic comment publish fallback failed")

        if history.has_errors() and not history.is_done():
            last_error = next((err for err in reversed(history.errors()) if err), None)
            return f"Agent failed before completion: {last_error}" if last_error else "Agent failed before completion."

        if not history.is_done():
            return "Agent stopped before confirming the task was done."

        await _persist_session_state(browser_session)

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
