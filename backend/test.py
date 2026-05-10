import anthropic
import os

from config import ANTHROPIC_MODEL

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model=ANTHROPIC_MODEL,
    max_tokens=50,
    messages=[
        {"role": "user", "content": "hello"}
    ]
)

print(response.content)