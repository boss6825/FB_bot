import asyncio
import logging
import os
from pathlib import Path
from typing import Any

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

POST_CLICK_FALLBACK_ATTEMPTS = 3
POST_CLICK_FALLBACK_SLEEP_SECONDS = 1.2
COMMENT_CLICK_FALLBACK_ATTEMPTS = 3
COMMENT_CLICK_FALLBACK_SLEEP_SECONDS = 1.0


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
    click_script = r"""
(() => {
  const isVisible = (el) => !!el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
  const isEnabled = (el) => !!el && el.getAttribute('aria-disabled') !== 'true';
  const clickElement = (el) => {
    ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type => {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    });
    if (typeof el.click === 'function') el.click();
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
        clickElement(node);
        return { clicked: true, strategy: selector };
      }
    }
  }

  const textMatches = [...document.querySelectorAll('div[role="button"],button')]
    .filter(el => (el.textContent || '').trim() === 'Post');
  for (const node of textMatches) {
    if (isVisible(node) && isEnabled(node)) {
      clickElement(node);
      return { clicked: true, strategy: 'text-content' };
    }
  }

  return { clicked: false, strategy: 'none' };
})()
"""

    before_visible = await _composer_has_visible_post_button(browser_session)
    if not before_visible:
        return False, "No visible Post button found in composer before fallback click."

    for attempt in range(1, POST_CLICK_FALLBACK_ATTEMPTS + 1):
        value = await _evaluate_js(browser_session, click_script)
        logger.info("Post-click JS fallback attempt %s result: %s", attempt, value)
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
    click_script = r"""
(() => {
  const isVisible = (el) => !!el && (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0);
  const isEnabled = (el) => !!el && el.getAttribute('aria-disabled') !== 'true' && !(el.disabled === true);
  const clickElement = (el) => {
    ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type => {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    });
    if (typeof el.click === 'function') el.click();
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
        clickElement(node);
        return { clicked: true, strategy: selector };
      }
    }
  }

  const textMatches = [...document.querySelectorAll('div[role="button"],button')]
    .filter(el => (el.textContent || '').trim() === 'Comment');
  for (const node of textMatches) {
    if (isVisible(node) && isEnabled(node)) {
      clickElement(node);
      return { clicked: true, strategy: 'text-content' };
    }
  }

  return { clicked: false, strategy: 'none' };
})()
"""

    before_visible = await _comment_composer_has_visible_submit_button(browser_session)
    if not before_visible:
        return False, "No visible Comment submit button found before fallback click."

    for attempt in range(1, COMMENT_CLICK_FALLBACK_ATTEMPTS + 1):
        value = await _evaluate_js(browser_session, click_script)
        logger.info("Comment-click JS fallback attempt %s result: %s", attempt, value)
        if value and value.get("clicked"):
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
            max_failures=2,
            final_response_after_failure=False,
            include_tool_call_examples=True,
        )

        history = await agent.run(max_steps=35)
        final_result = history.final_result()

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
