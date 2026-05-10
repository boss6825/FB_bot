import asyncio
from playwright.async_api import async_playwright
from browser_use import Agent, BrowserSession
from browser_use.llm import ChatAnthropic
from dotenv import load_dotenv

from session import load_session, save_session, clear_session
from auth import load_credentials
from config import ANTHROPIC_MODEL

load_dotenv()

FB_URL = "https://www.facebook.com"


async def _check_and_login() -> dict | None:
    """
    Verify saved session is still valid; if not, perform a fresh login.
    Returns a playwright storage_state dict on success, None on login failure.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
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
    browser_session = BrowserSession(storage_state=state, headless=True)

    try:
        agent = Agent(
            task=task_description,
            llm=llm,
            browser=browser_session,
        )

        history = await agent.run(max_steps=20)

        # Persist any cookie/session changes made during the task
        try:
            updated_state = await browser_session.export_storage_state()
            save_session(updated_state)
        except Exception:
            pass

        return history.final_result() or "Task completed."
    finally:
        try:
            await browser_session.stop()
        except Exception:
            pass
