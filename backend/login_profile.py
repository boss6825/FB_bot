import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from session import SESSION_FILE


ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

FB_URL = "https://www.facebook.com"
BROWSER_USER_DATA_DIR = Path(
    os.getenv(
        "BROWSER_USER_DATA_DIR",
        str(Path(__file__).parent / "storage" / "persistent-profile"),
    )
)


async def main() -> None:
    BROWSER_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_USER_DATA_DIR),
            headless=False,
            viewport={"width": 1365, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(FB_URL, wait_until="domcontentloaded")

        print()
        print(f"Opened Facebook with profile: {BROWSER_USER_DATA_DIR}")
        print("Log in manually, complete any checkpoint/CAPTCHA, and wait until the feed is visible.")
        await asyncio.to_thread(input, "Press Enter here after Facebook is fully logged in...")

        await context.storage_state(path=str(SESSION_FILE))
        await context.close()

    print(f"Saved session state to: {SESSION_FILE}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
