"""Agent that solves CL-bench tasks using context search tools."""

import os
import re
import tempfile
from dataclasses import dataclass, field

from . import llm
from .tools import ContextTools, TOOLS_OPENAI_FORMAT
from .prompts import (
    AGENT_INSTRUCTIONS,
    VERIFY_INSTRUCTION,
    VERIFY_MESSAGE,
    VERIFIER_SYSTEM_PROMPT,
    REVISION_MESSAGE,
)


@dataclass
class AgentConfig:
    """All runtime config for agent experiments."""
    model: str = None
    max_tool_calls: int = None
    verbose: bool = False
    force_first_tool: bool = True


# =============================================================================
# System prompt builders
# =============================================================================

def build_system_prompt(role_context):
    """Exp 1, 3, 4: role context + agent instructions."""
    return f"{role_context}\n\n---\n\n{AGENT_INSTRUCTIONS}"


def build_system_prompt_with_verify(role_context):
    """Exp 2: role context + agent instructions + verification instruction."""
    return f"{role_context}\n\n---\n\n{AGENT_INSTRUCTIONS}\n\n{VERIFY_INSTRUCTION}"


# =============================================================================
# Context file
# =============================================================================

def write_context_file(messages):
    """Write context to a temp file for tool access."""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="clbench_ctx_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("## System Message\n\n")
        f.write(messages[0]["content"])

        user_num = 0
        for msg in messages[1:]:
            if msg["role"] == "user":
                user_num += 1
                label = "First" if user_num == 1 else f"#{user_num}"
                f.write(f"\n\n## User Message {label}\n\n")
                f.write(msg["content"])
    return path


def build_agent_messages(messages):
    """Convert CL-bench message format to agent conversation."""
    agent_msgs = [{"role": "user", "content": messages[1]["content"]}]
    for msg in messages[2:]:
        agent_msgs.append({"role": msg["role"], "content": msg["content"]})
    return agent_msgs


# =============================================================================
# Answer tag parsing
# =============================================================================

def extract_answer(text):
    """Extract content from <answer></answer> tags. Falls back to full text."""
    match = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


# =============================================================================
# Core agent loop (shared by all experiments)
# =============================================================================

def agent_loop(system, agent_messages, ctx_tools, cfg, max_tool_calls_override=None):
    """Run the agent tool loop until a text-only response.

    Args:
        system: System prompt string
        agent_messages: Conversation messages (mutated in place)
        ctx_tools: ContextTools instance
        cfg: AgentConfig
        max_tool_calls_override: Override cfg.max_tool_calls (used for remaining budget in exp3/4)

    Returns:
        tuple: (answer_text, tool_log, tool_call_count, token_usage)
        token_usage: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int, "api_calls": int}
    """
    max_tool_calls = max_tool_calls_override if max_tool_calls_override is not None else cfg.max_tool_calls
    tool_call_count = 0
    tool_log = []
    total_prompt = 0
    total_completion = 0
    api_calls = 0
    is_first_call = True

    while True:
        response = llm.chat(
            system=system,
            messages=agent_messages,
            tools=TOOLS_OPENAI_FORMAT,
            model=cfg.model,
            force_tool=(is_first_call and cfg.force_first_tool),
        )
        is_first_call = False

        # Accumulate token usage
        usage = llm.get_usage(response)
        total_prompt += usage["prompt_tokens"]
        total_completion += usage["completion_tokens"]
        api_calls += 1

        token_usage = {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "api_calls": api_calls,
        }

        # Text-only response — agent is done
        if not llm.has_tool_use(response):
            raw = llm.extract_text(response)
            answer = extract_answer(raw)
            if cfg.verbose:
                print(f"  [ANSWER] {answer[:200]}...")
            return answer, tool_log, tool_call_count, token_usage

        # Process tool calls
        tool_calls = llm.extract_tool_calls(response)
        agent_messages.append(llm.build_assistant_message(response))

        tool_calls_with_results = []
        for tc in tool_calls:
            tool_call_count += 1
            args = llm.get_tool_call_args(tc)
            if cfg.verbose:
                print(f"  [TOOL {tool_call_count}] {tc.function.name}({args})")

            result = ctx_tools.execute(tc.function.name, args)

            if cfg.verbose:
                print(f"    -> {result['status']}: {result['message'][:150]}...")

            tool_log.append({
                "tool": tc.function.name,
                "input": args,
                "status": result["status"],
            })
            tool_calls_with_results.append((tc, result["message"]))

        agent_messages.extend(llm.build_tool_results(tool_calls_with_results))

        # Tool call limit reached — force final response without tools
        if max_tool_calls is not None and tool_call_count >= max_tool_calls:
            response = llm.chat(
                system=system,
                messages=agent_messages,
                tools=None,
                model=cfg.model,
            )
            # Accumulate final call tokens
            usage = llm.get_usage(response)
            total_prompt += usage["prompt_tokens"]
            total_completion += usage["completion_tokens"]
            api_calls += 1
            token_usage = {
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "total_tokens": total_prompt + total_completion,
                "api_calls": api_calls,
            }

            raw = llm.extract_text(response)
            answer = extract_answer(raw)
            if cfg.verbose:
                print(f"  [FORCED ANSWER] {answer[:200]}...")
            return answer, tool_log, tool_call_count, token_usage


# =============================================================================
# Experiment runners
# =============================================================================

def run_exp0(messages, ctx_tools, ctx_file, cfg):
    """Exp 0: Vanilla baseline. No tools, no agent instructions.

    Passes messages directly to the LLM exactly like official infer.py.
    This reproduces the leaderboard vanilla numbers.
    """
    # Pass all messages as-is. System message is messages[0].
    # For multi-turn: includes gold assistant answers.
    system = messages[0]["content"]
    conversation = [{"role": m["role"], "content": m["content"]} for m in messages[1:]]

    response = llm.chat(
        system=system,
        messages=conversation,
        tools=None,
        model=cfg.model,
    )
    answer = llm.extract_text(response)
    usage = llm.get_usage(response)
    token_usage = {
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "api_calls": 1,
    }
    return answer, [], system, token_usage


def _merge_usage(*usages):
    """Sum token usage dicts across multiple agent_loop phases."""
    merged = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_calls": 0}
    for u in usages:
        for k in merged:
            merged[k] += u.get(k, 0)
    return merged


def run_exp1(messages, ctx_tools, ctx_file, cfg):
    """Exp 1: Basic agent. Search + read, no verification."""
    system = build_system_prompt(messages[0]["content"])
    agent_messages = build_agent_messages(messages)
    answer, tool_log, _, usage = agent_loop(system, agent_messages, ctx_tools, cfg)
    return answer, tool_log, system, usage


def run_exp2(messages, ctx_tools, ctx_file, cfg):
    """Exp 2: Agent + self-verification in system prompt."""
    system = build_system_prompt_with_verify(messages[0]["content"])
    agent_messages = build_agent_messages(messages)
    answer, tool_log, _, usage = agent_loop(system, agent_messages, ctx_tools, cfg)
    return answer, tool_log, system, usage


def run_exp3(messages, ctx_tools, ctx_file, cfg):
    """Exp 3: Agent + code-enforced verification."""
    system = build_system_prompt(messages[0]["content"])
    agent_messages = build_agent_messages(messages)

    if cfg.verbose:
        print("  [PHASE 1: DRAFT]")
    draft, tool_log, count, usage1 = agent_loop(system, agent_messages, ctx_tools, cfg)

    if cfg.verbose:
        print("  [PHASE 2: VERIFY]")
    agent_messages.append({"role": "assistant", "content": draft})
    agent_messages.append({"role": "user", "content": VERIFY_MESSAGE})

    remaining = None
    if cfg.max_tool_calls is not None:
        remaining = max(0, cfg.max_tool_calls - count)

    final, verify_log, _, usage2 = agent_loop(
        system, agent_messages, ctx_tools, cfg, max_tool_calls_override=remaining,
    )
    return final, tool_log + verify_log, system, _merge_usage(usage1, usage2)


def run_exp4(messages, ctx_tools, ctx_file, cfg):
    """Exp 4: Two-agent architecture (generator + verifier)."""
    system = build_system_prompt(messages[0]["content"])
    agent_messages = build_agent_messages(messages)

    if cfg.verbose:
        print("  [PHASE 1: GENERATE]")
    draft, gen_log, gen_count, usage1 = agent_loop(system, agent_messages, ctx_tools, cfg)

    if cfg.verbose:
        print("  [PHASE 2: VERIFY (separate agent)]")
    verifier_user_msg = (
        f"## Question\n\n{messages[1]['content']}\n\n"
        f"## Answer to Verify\n\n{draft}"
    )
    verifier_messages = [{"role": "user", "content": verifier_user_msg}]
    verifier_tools = ContextTools(ctx_file)
    feedback, verify_log, _, usage2 = agent_loop(
        VERIFIER_SYSTEM_PROMPT, verifier_messages, verifier_tools, cfg,
    )

    if cfg.verbose:
        print("  [PHASE 3: REVISE]")
    revision_msg = REVISION_MESSAGE.format(verifier_feedback=feedback)
    agent_messages.append({"role": "assistant", "content": draft})
    agent_messages.append({"role": "user", "content": revision_msg})

    remaining = None
    if cfg.max_tool_calls is not None:
        remaining = max(0, cfg.max_tool_calls - gen_count)

    final, revise_log, _, usage3 = agent_loop(
        system, agent_messages, ctx_tools, cfg, max_tool_calls_override=remaining,
    )
    return final, gen_log + verify_log + revise_log, system, _merge_usage(usage1, usage2, usage3)


# =============================================================================
# Dispatch
# =============================================================================

EXPERIMENTS = {
    0: run_exp0,
    1: run_exp1,
    2: run_exp2,
    3: run_exp3,
    4: run_exp4,
}


def run_task(messages, experiment=1, cfg=None):
    """Run an experiment on a single task.

    Returns:
        tuple: (answer_text, tool_log, system_prompt, token_usage)
    """
    cfg = cfg or AgentConfig()
    runner = EXPERIMENTS.get(experiment)
    if runner is None:
        raise ValueError(f"Unknown experiment: {experiment}. Valid: {list(EXPERIMENTS.keys())}")

    ctx_file = write_context_file(messages)
    try:
        ctx_tools = ContextTools(ctx_file)
        return runner(messages=messages, ctx_tools=ctx_tools, ctx_file=ctx_file, cfg=cfg)
    finally:
        os.unlink(ctx_file)
