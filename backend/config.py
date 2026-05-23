import os
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

# ── LLM (used by llm.py for text generation, NOT by Stagehand) ───────────
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# ── Browserbase / Stagehand ──────────────────────────────────────────────
# BROWSERBASE_API_KEY and MODEL_API_KEY are read automatically by the
# Stagehand SDK from the environment.  They can also be passed explicitly
# to the AsyncStagehand() constructor if needed.
#
# MODEL_API_KEY defaults to ANTHROPIC_API_KEY so you don't need to set it
# twice when using Anthropic models with Stagehand.
if not os.getenv("MODEL_API_KEY") and os.getenv("ANTHROPIC_API_KEY"):
    os.environ["MODEL_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
