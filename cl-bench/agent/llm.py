"""Unified LLM interface via litellm + Azure OpenAI direct client.

Supports:
  - Anthropic:  anthropic/claude-haiku-4-5-20251001
  - Bedrock:    bedrock/converse/qwen.qwen3-next-80b-a3b
  - Azure:      azure/gpt-5-mini  (via TR AI Platform)
"""

import json
import os
import random
import threading
import time
from pathlib import Path

import litellm
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# Suppress litellm noise
litellm.suppress_debug_info = True
# NOTE: We do NOT set litellm.drop_params = True globally because it
# drops tool_choice="required" which we need. Instead we handle
# tool_choice selectively per call.

DEFAULT_MODEL = "anthropic/claude-opus-4-5-20251101"
JUDGE_MODEL = "azure/gpt-5.1"
MAX_RETRIES = 5
BASE_DELAY = 4.0     # seconds
MAX_DELAY = 60.0     # cap for exponential backoff
JITTER = 0.3         # ±30% jitter


def _backoff(attempt):
    """Exponential backoff with jitter. attempt is 0-indexed.

    attempt=0 → ~4s, attempt=1 → ~8s, attempt=2 → ~16s, attempt=3 → ~32s, attempt=4 → ~60s
    """
    base = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
    return base * (1.0 + random.uniform(-JITTER, JITTER))

# --- TR AI Platform (Azure OpenAI + OpenAI Direct) ---
AZURE_WORKSPACE_ID = os.getenv("AZURE_WORKSPACE_ID", "PracticalLawwDKa")
_tr_clients = {}  # cache per model
_tr_lock = threading.Lock()

# Models that use OpenAI Direct (not Azure)
OPENAI_DIRECT_MODELS = {
    "gpt-5.1", "gpt-5.1-codex", "gpt-5.1-codex-mini",
    "gpt-5-2025-08-07", "gpt-5-mini-2025-08-07", "gpt-5-nano-2025-08-07",
    "gpt-5-pro", "o1", "o3-mini",
}


def _get_tr_client(model_name):
    """Get or create a client via TR AI Platform credentials.

    Handles both Azure OpenAI and OpenAI Direct models.
    Thread-safe: only one thread fetches credentials at a time.
    """
    if model_name in _tr_clients:
        return _tr_clients[model_name]

    with _tr_lock:
        if model_name in _tr_clients:
            return _tr_clients[model_name]

        import requests
        from openai import OpenAI, AzureOpenAI

        url = "https://aiplatform.gcs.int.thomsonreuters.com/v1/openai/token"

        # Try OpenAI Direct first for known direct models
        is_direct = model_name in OPENAI_DIRECT_MODELS
        payload = {"workspace_id": AZURE_WORKSPACE_ID, "model_name": model_name}
        if is_direct:
            payload["oai_access"] = "openai_direct"

        resp = requests.post(url, json=payload, timeout=30)
        creds = json.loads(resp.content)

        # OpenAI Direct path
        if creds.get("is_direct_openai") and "openai_api_key" in creds:
            client = OpenAI(
                api_key=creds["openai_api_key"],
                base_url="https://us.api.openai.com/v1",
            )
            _tr_clients[model_name] = client
            return client

        # Azure OpenAI path
        if "openai_key" not in creds:
            # Try again without oai_access flag (Azure fallback)
            if is_direct:
                payload.pop("oai_access", None)
                resp = requests.post(url, json=payload, timeout=30)
                creds = json.loads(resp.content)
            if "openai_key" not in creds:
                raise RuntimeError(f"Failed to get credentials for '{model_name}': {resp.text}")

        deployment_id = creds["azure_deployment"]
        llm_profile_key = deployment_id.split("/")[0]

        headers = {
            "Authorization": f"Bearer {creds['token']}",
            "api-key": creds["openai_key"],
            "Content-Type": "application/json",
            "x-tr-chat-profile-name": "ai-platforms-chatprofile-prod",
            "x-tr-userid": AZURE_WORKSPACE_ID,
            "x-tr-llm-profile-key": llm_profile_key,
            "x-tr-user-sensitivity": "true",
            "x-tr-sessionid": deployment_id,
            "x-tr-asset-id": AZURE_WORKSPACE_ID,
            "x-tr-authorization": "https://eais2-use.int.thomsonreuters.com",
        }

        client = AzureOpenAI(
            azure_endpoint="https://eais2-use.int.thomsonreuters.com",
            api_key=creds["openai_key"],
            api_version=creds["openai_api_version"],
            azure_deployment=deployment_id,
            default_headers=headers,
        )
        _tr_clients[model_name] = client
        return client


def _call_azure(model_name, messages, tools=None, max_tokens=8192,
                tool_choice="auto"):
    """Call OpenAI via TR AI Platform (Azure or Direct)."""
    client = _get_tr_client(model_name)

    kwargs = {
        "model": model_name,
        "messages": messages,
        "max_completion_tokens": max_tokens,  # GPT-5 series requires this
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    for attempt in range(MAX_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            if attempt >= MAX_RETRIES - 1:
                raise
            error_str = str(e)
            if "429" in error_str or "Too many" in error_str or "throttl" in error_str.lower():
                time.sleep(_backoff(attempt))
            else:
                time.sleep(_backoff(0))  # short wait for non-rate-limit errors


# --- Max tokens ---

def _get_max_tokens(model, requested_max):
    """Cap max_tokens to model limits."""
    if model and "bedrock/" in model:
        return min(requested_max, 8192)
    if model and model.startswith("azure/"):
        return min(requested_max, 8192)
    return requested_max


# --- Main chat function ---

def chat(system, messages, tools=None, model=None, max_tokens=16384,
         force_tool=False):
    """
    Call an LLM with tool support.

    Uses litellm for Anthropic and Bedrock.
    Uses direct Azure OpenAI client for azure/* models (TR AI Platform auth).

    Args:
        system: System prompt string
        messages: List of message dicts
        tools: Optional list of tool definitions (OpenAI format)
        model: Model string (anthropic/*, bedrock/converse/*, azure/*)
        max_tokens: Max tokens in response
        force_tool: If True, force the model to call a tool (tool_choice="required")

    Returns:
        Response object (OpenAI-compatible format)
    """
    model = model or DEFAULT_MODEL
    max_tokens = _get_max_tokens(model, max_tokens)

    # Build messages with system prompt prepended (skip if empty)
    if system and system.strip():
        full_messages = [{"role": "system", "content": system}] + messages
    else:
        full_messages = messages

    tool_choice = "required" if force_tool else "auto"

    # Azure: use direct client (TR AI Platform custom auth)
    if model.startswith("azure/"):
        azure_model = model[len("azure/"):]
        # Pre-warm client (thread-safe, cached after first call)
        _get_tr_client(azure_model)
        return _call_azure(azure_model, full_messages, tools=tools,
                           max_tokens=max_tokens, tool_choice=tool_choice)

    # Everything else: litellm
    kwargs = {
        "model": model,
        "messages": full_messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        # Only pass tool_choice when forcing — some Bedrock models don't support it
        if tool_choice == "required":
            kwargs["tool_choice"] = "required"
            # litellm blocks tool_choice for some Bedrock models even though
            # Bedrock Converse supports it. Override with allowed_openai_params.
            if "bedrock/" in model:
                kwargs["allowed_openai_params"] = ["tool_choice"]

    for attempt in range(MAX_RETRIES):
        try:
            return litellm.completion(**kwargs)
        except (litellm.BadRequestError, litellm.UnsupportedParamsError) as e:
            # Model doesn't support tool_choice — retry without it (not a retryable error)
            err = str(e)
            if ("tool_choice" in err or "toolChoice" in err) and "tool_choice" in kwargs:
                kwargs.pop("tool_choice", None)
                kwargs.pop("allowed_openai_params", None)
                return litellm.completion(**kwargs)
            raise
        except litellm.RateLimitError:
            if attempt >= MAX_RETRIES - 1:
                raise
            time.sleep(_backoff(attempt))
        except litellm.APIError:
            if attempt >= MAX_RETRIES - 1:
                raise
            time.sleep(_backoff(0))


# --- Response helpers (work with both litellm and openai responses) ---

def extract_text(response):
    """Extract text content from response."""
    content = response.choices[0].message.content
    return content if content else ""


def has_tool_use(response):
    """Check if response contains tool calls."""
    return bool(response.choices[0].message.tool_calls)


def extract_tool_calls(response):
    """Extract tool calls from response."""
    return response.choices[0].message.tool_calls or []


def get_tool_call_args(tool_call):
    """Parse tool call arguments (JSON string -> dict)."""
    args = tool_call.function.arguments
    if isinstance(args, str):
        return json.loads(args)
    return args


def build_assistant_message(response):
    """Build assistant message dict from response for message history."""
    message = response.choices[0].message
    msg = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    return msg


def get_usage(response):
    """Extract token usage from response. Returns dict with prompt_tokens, completion_tokens, total_tokens."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }


def build_tool_results(tool_calls_with_results):
    """Build tool result messages for message history.

    Args:
        tool_calls_with_results: list of (tool_call, result_string) tuples

    Returns:
        list of message dicts (one per tool call, role="tool")
    """
    return [
        {
            "role": "tool",
            "tool_call_id": tc.id,
            "name": tc.function.name,
            "content": result,
        }
        for tc, result in tool_calls_with_results
    ]
