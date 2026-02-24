"""Thin Anthropic API wrapper for chat + tool use."""

import os
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


DEFAULT_MODEL = "claude-opus-4-5-20251101"
MAX_RETRIES = 3
RETRY_DELAY = 2


def get_client():
    """Get Anthropic client."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


def chat(client, system, messages, tools=None, model=None, max_tokens=16384):
    """
    Call Anthropic messages API with prompt caching.

    The system prompt and the first user message (the big context) are marked
    for caching. This avoids re-processing them on every tool call round-trip.

    Args:
        client: Anthropic client
        system: System prompt string
        messages: List of message dicts [{"role": "user"/"assistant", "content": ...}]
        tools: Optional list of tool definitions (Anthropic format)
        model: Model name, defaults to DEFAULT_MODEL
        max_tokens: Max tokens in response

    Returns:
        response: Raw Anthropic response object
    """
    model = model or DEFAULT_MODEL

    # System prompt with cache control
    system_with_cache = [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # Mark the first user message for caching (the big context dump)
    cached_messages = _apply_cache_control(messages)

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_with_cache,
        "messages": cached_messages,
    }
    if tools:
        kwargs["tools"] = tools

    for attempt in range(MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (2 ** attempt)
                time.sleep(wait)
            else:
                raise
        except anthropic.APIError as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                raise


def extract_text(response):
    """Extract text content from response."""
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def extract_tool_calls(response):
    """Extract tool use blocks from response."""
    return [block for block in response.content if block.type == "tool_use"]


def has_tool_use(response):
    """Check if response contains tool calls."""
    return response.stop_reason == "tool_use"


def _apply_cache_control(messages):
    """
    Apply cache_control to the first user message.

    The first user message contains the big context document. Caching it
    avoids re-tokenizing on every tool call round-trip within the same task.
    """
    if not messages:
        return messages

    result = []
    for i, msg in enumerate(messages):
        if i == 0 and msg["role"] == "user" and isinstance(msg["content"], str):
            # First user message — convert to block format with cache control
            result.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": msg["content"],
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            })
        else:
            result.append(msg)

    return result
