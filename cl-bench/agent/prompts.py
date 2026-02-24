"""All prompts for CL-bench experiments. Modular design — shared base + per-experiment additions."""

# =============================================================================
# Shared base (all experiments)
# =============================================================================

TOOL_INSTRUCTIONS = """You have tools to search and read a reference document.
- search_context: Regex search over the document. Returns matching lines with context.
- read_lines: Read a specific line range from the document.

The document is organized with these sections:
- "## System Message" — the original instructions and role requirements
- "## User Message First", "## User Message #2", etc. — the user's questions and context"""

RULES = """Rules:
- Identify every part and sub-question being asked. Do not miss any.
- Only use information from the document. Do not use prior knowledge.
- Always search and verify before answering. Do not answer from memory alone.
- Answer only what is asked. No preambles, disclaimers, caveats, or meta-commentary.
- Match the exact output format requested (list, JSON, table, etc.). Do not add formatting that was not asked for.
- Wrap your final answer in <answer></answer> tags. Only the content inside these tags will be submitted. Do not include any reasoning, verification notes, or meta-commentary inside the tags — only the answer itself."""

# Combined agent instructions (TOOL_INSTRUCTIONS + RULES)
AGENT_INSTRUCTIONS = f"""{TOOL_INSTRUCTIONS}

{RULES}"""

# =============================================================================
# Experiment 2: Self-verification via system prompt
# Appended to system prompt after AGENT_INSTRUCTIONS
# =============================================================================

VERIFY_INSTRUCTION = """Before giving your final answer, you MUST verify:
1. Re-read "## System Message" — check that you follow every requirement, constraint, persona, and formatting rule.
2. Confirm you addressed ALL parts of the question, not just some.
3. Use search_context/read_lines to verify specific facts, numbers, and names.
4. Check your output format matches exactly what was requested."""

# =============================================================================
# Experiment 3: Self-verification via injected user message
# Injected as a user message after the agent's draft answer
# =============================================================================

VERIFY_MESSAGE = """Now verify your answer before I accept it. You MUST use tools to check each of these:

1. Search for "## System Message" and re-read the original instructions. Check that your answer follows every requirement, constraint, and formatting rule specified there.
2. Check that you answered ALL parts of the question — not just some. If the question has multiple sub-questions, confirm each one is addressed.
3. Use search_context/read_lines to verify specific facts, numbers, names, or quotes in your answer actually come from the document.
4. Check that your output format matches exactly what was requested.

After verifying, respond with your corrected final answer inside <answer></answer> tags. If nothing needs fixing, respond with the same answer in the tags. Do not include any verification notes inside the tags — only the final answer."""

# =============================================================================
# Experiment 4: Two-agent architecture
# =============================================================================

# System prompt for the verifier agent (separate LLM context)
VERIFIER_SYSTEM_PROMPT = """You are a verification agent. Your job is to check whether an answer is correct, complete, and properly formatted.

You have the same tools as the original agent:
- search_context: Regex search over the reference document.
- read_lines: Read a specific line range from the document.

Your process:
1. Read "## System Message" to understand the role, persona, tone, and constraints the answer must follow.
2. Read the user's question to understand exactly what was asked.
3. Generate a checklist of what the answer SHOULD contain: required facts, tone/personality, format, completeness requirements.
4. Compare the provided answer against your checklist.
5. Search the document to fact-check specific claims in the answer.
6. Produce a list of specific issues found. For each issue state: what is wrong, what should it be instead, and where in the document the correct information is.

If the answer is perfect, say "No issues found."
Do not rewrite the answer. Only provide feedback."""

# Injected as user message to the generator after receiving verifier feedback
REVISION_MESSAGE = """A verification agent reviewed your answer and found these issues:

{verifier_feedback}

First, validate each piece of feedback — the verifier may be wrong. Then improve your answer based on the valid feedback only. Respond with your revised final answer inside <answer></answer> tags. Do not include any reasoning or validation notes inside the tags — only the final answer."""
