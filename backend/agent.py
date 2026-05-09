import asyncio
from playwright.async_api import async_playwright
from browser_use import Agent
from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv

from session import load_session, save_session, clear_session
from auth import load_credentials
from config import ANTHROPIC_MODEL

load_dotenv()

FB_URL = "https://www.facebook.com"


async def get_browser_context(playwright):
    """
    Launch browser and return a context.
    If a saved session exists, load it so we skip login.
    """
    browser = await playwright.chromium.launch(headless=True)
    session = load_session()

    if session:
        context = await browser.new_context(storage_state=session)
    else:
        context = await browser.new_context()

    return browser, context


async def ensure_logged_in(context) -> bool:
    """
    Check if the current session is still valid by visiting FB.
    Returns True if logged in, False if session expired.
    """
    page = await context.new_page()
    await page.goto(FB_URL)
    await page.wait_for_load_state("networkidle")

    # If redirected to login page, session is dead
    is_logged_in = "login" not in page.url and "checkpoint" not in page.url
    await page.close()
    return is_logged_in


async def login_and_save_session(context) -> bool:
    """
    Perform actual FB login using stored credentials.
    Saves session state on success.
    Returns True on success, False on failure.
    """
    creds = load_credentials()
    if not creds:
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
            await page.close()
            return False

        # Save session so we don't login again next time
        storage_state = await context.storage_state()
        save_session(storage_state)
        await page.close()
        return True

    except Exception as e:
        await page.close()
        raise e


async def run_fb_task(task_description: str) -> str:
    """
    Main entry point. Given a plain-English task, run it on Facebook.
    Handles session management automatically.
    """
    async with async_playwright() as playwright:
        browser, context = await get_browser_context(playwright)

        try:
            logged_in = await ensure_logged_in(context)

            if not logged_in:
                # Session expired or never existed — re-login
                clear_session()
                await context.close()
                browser_fresh = await playwright.chromium.launch(headless=True)
                context = await browser_fresh.new_context()
                success = await login_and_save_session(context)
                if not success:
                    return "Login failed. Please check your credentials."

            # Hand off to browser-use agent with Claude as the LLM
            llm = ChatAnthropic(model=ANTHROPIC_MODEL)

            agent = Agent(
                task=task_description,
                llm=llm,
                browser_context=context,
            )

            history = await agent.run(max_steps=20)
            result = history.final_result()

            # Persist any session changes (new cookies etc.)
            storage_state = await context.storage_state()
            save_session(storage_state)

            return result or "Task completed."

        finally:
            await context.close()
            await browser.close()