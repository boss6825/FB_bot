import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright
from browser_use import Agent, BrowserSession
from browser_use.llm import ChatAnthropic
from dotenv import load_dotenv

from session import SESSION_FILE, load_session, save_session, clear_session
from auth import load_credentials
from config import ANTHROPIC_MODEL

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

FB_URL = "https://www.facebook.com"
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").strip().lower() in {"1", "true", "yes", "on"}
BROWSER_KEEP_OPEN = os.getenv("BROWSER_KEEP_OPEN", "false").strip().lower() in {"1", "true", "yes", "on"}
BROWSER_USER_DATA_DIR = os.getenv(
    "BROWSER_USER_DATA_DIR",
    str(Path(__file__).parent / "storage" / "tmp-browser-use-profile"),
)


async def _check_and_login() -> dict | None:
    """
    Verify saved session is still valid; if not, perform a fresh login.
    Returns a playwright storage_state dict on success, None on login failure.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=BROWSER_HEADLESS)
        session = load_session()
        context = (
            await browser.new_context(storage_state=session)
            if session
            else await browser.new_context()
        )

        # Check current login state
        page = await context.new_page()
        await page.goto(FB_URL)
        await page.wait_for_load_state("networkidle")
        logged_in = "login" not in page.url and "checkpoint" not in page.url
        await page.close()

        if not logged_in:
            clear_session()
            await context.close()
            context = await browser.new_context()

            creds = load_credentials()
            if not creds:
                await browser.close()
                raise ValueError("No credentials saved. Please provide FB credentials first.")

            page = await context.new_page()
            try:
                await page.goto(FB_URL)
                await page.wait_for_load_state("networkidle")
                await page.fill('input[name="email"]', creds["email"])
                await page.fill('input[name="pass"]', creds["password"])
                await page.click('button[name="login"]')
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(3000)

                if "login" in page.url or "checkpoint" in page.url:
                    await browser.close()
                    return None
            finally:
                await page.close()

        state = await context.storage_state()
        await browser.close()
        return state


async def run_fb_task(task_description: str) -> str:
    """
    Main entry point. Given a plain-English task, run it on Facebook.
    Handles session management automatically.
    """
    state = await _check_and_login()
    if state is None:
        return "Login failed. Please check your credentials."

    save_session(state)

    llm = ChatAnthropic(model=ANTHROPIC_MODEL)
    browser_session = BrowserSession(
        storage_state=str(SESSION_FILE),
        user_data_dir=BROWSER_USER_DATA_DIR,
        headless=BROWSER_HEADLESS,
        keep_alive=BROWSER_KEEP_OPEN,
    )

    try:
        agent = Agent(
            task=task_description,
            llm=llm,
            browser=browser_session,
            use_thinking=False,
            flash_mode=True,
            enable_planning=False,
        )

        history = await agent.run(max_steps=20)
        final_result = history.final_result()

        # Do not report success when the run ended in retries/errors.
        if history.has_errors() and not history.is_done():
            last_error = next((err for err in reversed(history.errors()) if err), None)
            if last_error:
                return f"Agent failed before completion: {last_error}"
            return "Agent failed before completion."

        if not history.is_done():
            return "Agent stopped before confirming the task was done."

        # Persist any cookie/session changes made during the task
        try:
            updated_state = await browser_session.export_storage_state()
            save_session(updated_state)
        except Exception:
            pass

        return final_result or "Task completed."
    finally:
        if not BROWSER_KEEP_OPEN:
            try:
                await browser_session.stop()
            except Exception:
                pass
