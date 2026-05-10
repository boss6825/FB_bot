import anthropic
import json
from dotenv import load_dotenv

from config import ANTHROPIC_MODEL

load_dotenv()

client = anthropic.Anthropic()


def _parse_json_dict(raw: str) -> dict | None:
    """Parse a single JSON object; tolerate markdown fences or leading/trailing chatter."""
    text = raw.strip()
    attempts = [text]
    if text.startswith("```"):
        inner = text[3:].lstrip()
        if inner.lower().startswith("json"):
            inner = inner[4:].lstrip("\n")
        inner = inner.strip()
        if inner.endswith("```"):
            inner = inner[:-3].strip()
        attempts.append(inner)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        attempts.append(text[start : end + 1])

    for candidate in attempts:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_intent(user_message: str) -> dict:
    """
    Given a user's chat message, extract:
    - action: "post" | "comment" | "unknown"
    - target_url: URL to comment on (if action is comment)
    - content_brief: what the post/comment should be about
    Returns a dict.
    """
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=500,
        system="""You are an intent parser.

Extract the user's Facebook automation request.

Return ONLY valid minified JSON:
{
  "action": "post" | "comment" | "unknown",
  "target_url": string or null,
  "content_brief": string
}

Examples:

User: post about AI changing sales
Output:
{"action":"post","target_url":null,"content_brief":"AI changing sales"}

User: comment on https://facebook.com/post123 saying great insights
Output:
{"action":"comment","target_url":"https://facebook.com/post123","content_brief":"great insights"}

No markdown. No explanation.""",
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    print("RAW CLAUDE RESPONSE:", raw)

    parsed = _parse_json_dict(raw)
    if parsed is not None:
        return parsed

    return {"action": "unknown", "target_url": None, "content_brief": user_message}


def generate_post_text(brief: str, context: str = "") -> str:
    """
    Generate the actual Facebook post text from a brief description.
    Optionally uses prior post context for continuity.
    """
    system_prompt = """You are a social media copywriter. Write a natural, engaging Facebook post.
Keep it concise (2-4 sentences max). No hashtag overload. Sound human, not corporate.
Do not include any explanation or preamble — just the post text."""

    user_content = f"Write a Facebook post about: {brief}"
    if context:
        user_content += f"\n\nContext from previous posts for continuity:\n{context}"

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    return response.content[0].text.strip()


def generate_comment_text(brief: str, post_context: str = "") -> str:
    """
    Generate a comment text. Optionally takes the post content for context.
    """
    system_prompt = """You are writing a Facebook comment. Keep it short (1-2 sentences), 
natural and relevant. No fluff. Just the comment text, nothing else."""

    user_content = f"Write a comment that: {brief}"
    if post_context:
        user_content += f"\n\nThe post being commented on:\n{post_context}"

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=150,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    return response.content[0].text.strip()


def build_agent_task(action: str, content: str, target_url: str = None) -> str:
    """
    Convert parsed intent + generated content into a browser-use task string.
    """
    if action == "post":
        return f"""Go to https://www.facebook.com. 
Create a new Facebook post with exactly this text:
\"{content}\"
Click the post button to publish it."""

    elif action == "comment" and target_url:
        return f"""Go to this Facebook post: {target_url}
Leave a comment with exactly this text:
\"{content}\"
Click the comment button to submit it."""

    else:
        return f"Go to https://www.facebook.com and {content}"