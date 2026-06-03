# Multi-Provider LLM Support — COMPLETE

## Architecture (Final)

Used **litellm** for unified OpenAI-compatible interface across all providers. Azure OpenAI uses direct client (TR AI Platform custom auth).

```
agent.py  →  llm.py  →  litellm  →  Anthropic / Bedrock Converse
                     →  AzureOpenAI (direct)  →  TR AI Platform
```

## Verified Models

| Model | litellm model string | Tool Calling | Active Params |
|-------|---------------------|-------------|---------------|
| Claude Haiku 4.5 | `anthropic/claude-haiku-4-5-20251001` | Yes | ~8B |
| Llama 4 Scout 17B | `bedrock/converse/us.meta.llama4-scout-17b-instruct-v1:0` | Yes | 17B |
| Qwen3-Next-80B-A3B | `bedrock/converse/qwen.qwen3-next-80b-a3b` | Yes | 3.9B |
| Kimi K2.5 | `bedrock/converse/moonshotai.kimi-k2.5` | Yes | 32B |
| GLM 4.7 | `bedrock/converse/zai.glm-4.7` | Yes | ~40B |
| ~~GLM 4.7 Flash~~ | ~~`bedrock/converse/zai.glm-4.7-flash`~~ | **No** (dropped) | ~3B |
| DeepSeek V3.2 | `bedrock/converse/deepseek.v3.2` | Yes | ~37B |
| GPT-5-mini | `azure/gpt-5-mini` | Yes | undisclosed |

## Running

```bash
# Anthropic
python -m agent.run --input data/observation_8.jsonl --experiment 1 \
  --model anthropic/claude-haiku-4-5-20251001 --verbose

# Bedrock (requires AWS_PROFILE=assumed-role)
AWS_PROFILE=assumed-role python -m agent.run --input data/observation_8.jsonl \
  --experiment 1 --model bedrock/converse/qwen.qwen3-next-80b-a3b --verbose

# Azure (uses TR AI Platform, workspace_id in env or default)
python -m agent.run --input data/observation_8.jsonl --experiment 1 \
  --model azure/gpt-5-mini --verbose
```

Output auto-generated: `outputs/<model_short>/exp<N>_<input>_<timestamp>.jsonl`

## Key Bugs Fixed

1. **String-typed integers from Llama**: Tool args like `context_lines: "2"` instead of `2`. Fixed with type coercion in `ContextTools.execute()`.
2. **max_tokens cap**: Bedrock/Azure models cap at 8192. Auto-capped in `llm._get_max_tokens()`.
3. **tool_choice unsupported**: Bedrock doesn't support `tool_choice` param. Fixed with `litellm.drop_params = True`.
4. **GPT-5 series needs max_completion_tokens**: Not `max_tokens`. Handled in `_call_azure()`.
