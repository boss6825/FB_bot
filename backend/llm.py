import anthropic
import json
from dotenv import load_dotenv

from config import ANTHROPIC_MODEL

load_dotenv()

client = anthropic.Anthropic()


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
        system="""You are an intent parser for a Facebook automation agent.
Given the user's message, extract their intent as JSON with these fields:
- action: "post" (create a new FB post) | "comment" (comment on a specific post) | "unknown"
- target_url: the Facebook post URL to comment on, or null if posting
- content_brief: a short description of what the post/comment should say

Respond ONLY with valid JSON, no markdown, no explanation.""",
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
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