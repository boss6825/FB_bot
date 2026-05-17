import os
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

# Latest IDs: https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Browser channel: "chrome" launches the real installed Chrome (lower automation
# fingerprint). Set to "chromium" to fall back to the Playwright-bundled build.
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome").strip()
# Optional UA override; empty string means let the browser use its own UA.
BROWSER_USER_AGENT = os.getenv("BROWSER_USER_AGENT", "").strip()
