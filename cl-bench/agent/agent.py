"""Agent that solves CL-bench tasks using context search tools."""

import os
import re
import tempfile

from . import llm
from .tools import ContextTools, TOOL_DEFINITIONS
from .prompts import (
    AGENT_INSTRUCTIONS,
    VERIFY_INSTRUCTION,
    VERIFY_MESSAGE,
    VERIFIER_SYSTEM_PROMPT,
    REVISION_MESSAGE,
)


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
    """Write context to a temp file for tool access.

    Includes system message + all user messages up to current turn.
    Messages format: [system, user1, (gold_assistant, user2, ...)]
    """
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
    """Convert CL-bench message format to agent conversation.

    Input: [system_msg, user_msg, (gold_assistant, user_followup, ...)]
    Output: [user: first_user_msg, (assistant: gold, user: followup, ...)]

    System msg goes in the API system prompt, not here.
    """
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

def agent_loop(client, system, agent_messages, ctx_tools, model=None,
               max_tool_calls=None, verbose=False):
    """Run the agent tool loop until a text-only response.

    Args:
        client: Anthropic client
        system: System prompt string
        agent_messages: Conversation messages (mutated in place)
        ctx_tools: ContextTools instance
        model: LLM model
        max_tool_calls: Max tool calls (None = unlimited)
        verbose: Print tool calls

    Returns:
        tuple: (answer_text, tool_log, tool_call_count)
    """
    tool_call_count = 0
    tool_log = []

    while True:
        response = llm.chat(
            client=client,
            system=system,
            messages=agent_messages,
            tools=TOOL_DEFINITIONS,
            model=model,
        )

        # Text-only response — agent is done
        if not llm.has_tool_use(response):
            raw = llm.extract_text(response)
            answer = extract_answer(raw)
            if verbose:
                print(f"  [ANSWER] {answer[:200]}...")
            return answer, tool_log, tool_call_count

        # Process tool calls
        tool_calls = llm.extract_tool_calls(response)
        # Serialize Pydantic content blocks to plain dicts for message history
        content_dicts = [block.model_dump() for block in response.content]
        agent_messages.append({"role": "assistant", "content": content_dicts})

        tool_results = []
        for tc in tool_calls:
            tool_call_count += 1
            if verbose:
                print(f"  [TOOL {tool_call_count}] {tc.name}({tc.input})")

            result = ctx_tools.execute(tc.name, tc.input)

            if verbose:
                print(f"    -> {result['status']}: {result['message'][:150]}...")

            tool_log.append({
                "tool": tc.name,
                "input": tc.input,
                "status": result["status"],
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result["message"],
            })

        agent_messages.append({"role": "user", "content": tool_results})

        # Tool call limit reached — force final response without tools
        if max_tool_calls is not None and tool_call_count >= max_tool_calls:
            response = llm.chat(
                client=client,
                system=system,
                messages=agent_messages,
                tools=None,
                model=model,
            )
            raw = llm.extract_text(response)
            answer = extract_answer(raw)
            if verbose:
                print(f"  [FORCED ANSWER] {answer[:200]}...")
            return answer, tool_log, tool_call_count


# =============================================================================
# Experiment runners
# =============================================================================

def run_exp1(client, messages, ctx_tools, ctx_file, model=None,
             max_tool_calls=None, verbose=False):
    """Exp 1: Basic agent. Search + read, no verification."""
    role_context = messages[0]["content"]
    system = build_system_prompt(role_context)
    agent_messages = build_agent_messages(messages)

    answer, tool_log, _ = agent_loop(
        client, system, agent_messages, ctx_tools,
        model=model, max_tool_calls=max_tool_calls, verbose=verbose,
    )
    return answer, tool_log, system


def run_exp2(client, messages, ctx_tools, ctx_file, model=None,
             max_tool_calls=None, verbose=False):
    """Exp 2: Agent + self-verification in system prompt."""
    role_context = messages[0]["content"]
    system = build_system_prompt_with_verify(role_context)
    agent_messages = build_agent_messages(messages)

    answer, tool_log, _ = agent_loop(
        client, system, agent_messages, ctx_tools,
        model=model, max_tool_calls=max_tool_calls, verbose=verbose,
    )
    return answer, tool_log, system


def run_exp3(client, messages, ctx_tools, ctx_file, model=None,
             max_tool_calls=None, verbose=False):
    """Exp 3: Agent + code-enforced verification.

    Phase 1: Agent researches and generates a draft answer.
    Phase 2: Inject VERIFY_MESSAGE, agent verifies with tools, returns final answer.
    """
    role_context = messages[0]["content"]
    system = build_system_prompt(role_context)
    agent_messages = build_agent_messages(messages)

    # Phase 1: draft
    if verbose:
        print("  [PHASE 1: DRAFT]")
    draft, tool_log, count = agent_loop(
        client, system, agent_messages, ctx_tools,
        model=model, max_tool_calls=max_tool_calls, verbose=verbose,
    )

    # Phase 2: verify
    if verbose:
        print("  [PHASE 2: VERIFY]")
    agent_messages.append({"role": "assistant", "content": draft})
    agent_messages.append({"role": "user", "content": VERIFY_MESSAGE})

    remaining = None
    if max_tool_calls is not None:
        remaining = max(0, max_tool_calls - count)

    final, verify_log, _ = agent_loop(
        client, system, agent_messages, ctx_tools,
        model=model, max_tool_calls=remaining, verbose=verbose,
    )

    return final, tool_log + verify_log, system


def run_exp4(client, messages, ctx_tools, ctx_file, model=None,
             max_tool_calls=None, verbose=False):
    """Exp 4: Two-agent architecture (generator + verifier).

    Phase 1: Generator searches document and produces answer.
    Phase 2: Verifier (fresh context) derives checklist, checks answer, gives feedback.
    Phase 3: Generator validates feedback and revises answer.
    """
    role_context = messages[0]["content"]
    system = build_system_prompt(role_context)
    agent_messages = build_agent_messages(messages)

    # Phase 1: generate
    if verbose:
        print("  [PHASE 1: GENERATE]")
    draft, gen_log, gen_count = agent_loop(
        client, system, agent_messages, ctx_tools,
        model=model, max_tool_calls=max_tool_calls, verbose=verbose,
    )

    # Phase 2: verify (fresh context, separate agent)
    if verbose:
        print("  [PHASE 2: VERIFY (separate agent)]")

    # Build the user question from original messages
    user_question = messages[1]["content"]

    verifier_user_msg = (
        f"## Question\n\n{user_question}\n\n"
        f"## Answer to Verify\n\n{draft}"
    )
    verifier_messages = [{"role": "user", "content": verifier_user_msg}]

    # Verifier gets its own tools on the same context file
    verifier_tools = ContextTools(ctx_file)

    feedback, verify_log, _ = agent_loop(
        client, VERIFIER_SYSTEM_PROMPT, verifier_messages, verifier_tools,
        model=model, max_tool_calls=max_tool_calls, verbose=verbose,
    )

    # Phase 3: revise (back to generator context)
    if verbose:
        print("  [PHASE 3: REVISE]")
    revision_msg = REVISION_MESSAGE.format(verifier_feedback=feedback)
    agent_messages.append({"role": "assistant", "content": draft})
    agent_messages.append({"role": "user", "content": revision_msg})

    remaining = None
    if max_tool_calls is not None:
        remaining = max(0, max_tool_calls - gen_count)

    final, revise_log, _ = agent_loop(
        client, system, agent_messages, ctx_tools,
        model=model, max_tool_calls=remaining, verbose=verbose,
    )

    return final, gen_log + verify_log + revise_log, system


# =============================================================================
# Dispatch
# =============================================================================

EXPERIMENTS = {
    1: run_exp1,
    2: run_exp2,
    3: run_exp3,
    4: run_exp4,
}


def run_task(client, messages, experiment=1, model=None,
             max_tool_calls=None, verbose=False):
    """Run an experiment on a single task.

    Args:
        client: Anthropic client
        messages: The task's message list [{"role": ..., "content": ...}, ...]
        experiment: Experiment number (1-4)
        model: LLM model to use
        max_tool_calls: Max tool calls allowed (None = unlimited)
        verbose: Print tool calls and reasoning

    Returns:
        tuple: (answer_text, tool_log, system_prompt)
    """
    runner = EXPERIMENTS.get(experiment)
    if runner is None:
        raise ValueError(f"Unknown experiment: {experiment}. Valid: {list(EXPERIMENTS.keys())}")

    ctx_file = write_context_file(messages)
    try:
        ctx_tools = ContextTools(ctx_file)
        return runner(
            client=client,
            messages=messages,
            ctx_tools=ctx_tools,
            ctx_file=ctx_file,
            model=model,
            max_tool_calls=max_tool_calls,
            verbose=verbose,
        )
    finally:
        os.unlink(ctx_file)
