import os

from dotenv import load_dotenv

load_dotenv()

# Latest IDs: https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
