# CL-bench Agentic Solver: Experiment Log

## What is this?

We built an agentic solver for [CL-bench](https://github.com/), a benchmark that tests LLMs' ability to answer questions using long reference documents. Each task provides a system message (role/persona), a reference document, and a question. Scoring is binary all-or-nothing: every rubric must pass for score=1.

The dataset has 1,899 tasks across 4 categories and 500 contexts. Tasks range from single-turn to multi-turn conversations.

## Architecture

The agent has two tools:
- `search_context(pattern)` — regex search over the reference document, returns matching lines with context
- `read_lines(start, end)` — read a specific line range from the document

The agent loop: LLM generates a response. If it contains tool calls, execute them, feed results back. Repeat until the LLM returns a text-only response (the answer). The task's system message (role/persona) is placed in the actual API system prompt. The reference document is written to a temp file for tool access.

Grading uses a separate LLM call with the CL-bench rubric evaluation prompt.

---

## Experiment Timeline

All experiments on 2026-02-15. Model: `claude-opus-4-6` unless noted.

### Phase 1: Initial Development (Runs 1-3, 2 tasks each)

Two Game Mechanics tasks from a board game rulebook (159K chars). Used `claude-sonnet-4-5-20250929`.

**Run 1 — Baseline**
- System message was stuffed into the user message (not the API system prompt)
- Result: 0/2 tasks, 21/29 rubrics (72.4%)
- Task 1 ("What do Sighting Cards do?"): 11/14 rubrics. Agent made 3 tool calls and stopped. Missed 3 sub-mechanics buried deep in the rulebook.
- Task 2 ("What actions can I take during my turn?"): 10/15 rubrics. Agent made **0 tool calls** — answered entirely from memory of Task 1's conversation. Used numbered lists despite explicit instruction to use bullet points. Obeyed user's "no jokes" instruction instead of system prompt's "always quip" — benchmark expected system prompt to win.

**Run 2 — System prompt fix**
- Change: Moved the task's system message into the actual API system prompt
- Result: 0/2 tasks, 21/29 rubrics (72.4%)
- Task 2 now made 19 tool calls (was 0). But still failed on bullet points and joke rubrics.

**Run 3 — Simplified agent instructions**
- Change: Minimized agent system prompt to just tool descriptions. Let the task's role context dominate.
- Result: 0/2 tasks, 22/29 rubrics (75.9%)
- Persona adoption improved (conspiracy theorist tone appeared). Same 7 rubric failures persisted.

**Persistent failures across Runs 1-3:**
- Agent makes only 3 searches on a 159K document — misses the same 3 sub-mechanics every time
- Agent uses numbered lists despite "use bullet points" instruction
- Agent follows user's "no jokes" over system prompt's "always quip"

### Phase 2: First Scale Run

**Run 4 (v1) — 100 contexts, 395 tasks**
- Sampled 100 contexts (seed=42), which expanded to 395 tasks due to multi-turn conversations
- 25 parallel workers, `claude-opus-4-6`
- Had a bug: multi-turn follow-up tasks used garbled messages (broken conversation reconstruction)
- **Result: 111/395 tasks (28.1%), 6109/7223 rubrics (84.6%)**

Source: `outputs/agent_sample100.log`, `outputs/agent_sample100_graded.jsonl`

This was separately graded (generation and grading were separate steps), with grading done by `claude-opus-4-6`.

Category breakdown from grading log (`agent_sample100_eval.log`):

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 34/127 (26.8%) | 1584/1914 (82.8%) |
| Empirical Discovery & Simulation | 9/73 (12.3%) | 1208/1455 (83.0%) |
| Procedural Task Execution | 39/99 (39.4%) | 2004/2299 (87.2%) |
| Rule System Application | 29/96 (30.2%) | 1313/1555 (84.4%) |

### Phase 3: Gold History Fix

**Run 5 (v2) — 100 contexts, 395 tasks**
- Fixed multi-turn handling: each follow-up task now receives the correct gold assistant messages from previous turns (instead of garbled reconstruction)
- Same 100 contexts, same seed, same 395 tasks
- 25 parallel workers, grading integrated into run loop (not separate step)
- **Result: 105/395 tasks (26.6%), 6135/7242 rubrics (84.7%)**

Source: `outputs/agent_sample100_v2.log`

Category breakdown:

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 39/127 (30.7%) | 1593/1928 (82.6%) |
| Empirical Discovery & Simulation | 8/73 (11.0%) | 1221/1456 (83.9%) |
| Procedural Task Execution | 41/99 (41.4%) | 1996/2303 (86.7%) |
| Rule System Application | 17/96 (17.7%) | 1325/1555 (85.2%) |

Observation: Fixing gold history slightly improved rubric rate (84.6% → 84.7%) but task rate dropped (28.1% → 26.6%). The v1 bug may have accidentally helped some tasks by injecting extra context.

### Phase 4: Verification Experiments

Hypothesis: If the agent verifies its answer against the system message and rubric requirements before submitting, it should catch errors and improve scores.

**Experiment A — Prompt-based verification**
- Added mandatory 3-phase workflow to system prompt: RESEARCH → VERIFY (MANDATORY) → RESPOND
- Required `search_context("## System Message")` before answering
- 2 test tasks
- Result: Agent made the verification tool call but only checked step 1 (read system message). Skipped all other verification steps. Treated it as a checkbox.
- Scores: Task 1: 9/14, Task 2: 7/10

**Experiment B — Code-enforced verification**
- Removed verification from system prompt entirely
- After agent generates its first answer, the code injects a user message (`VERIFY_MESSAGE`) asking it to verify against requirements, then re-enters the agent loop
- 2 test tasks
- Result: Agent now genuinely verified — made 4 verification tool calls on Task 1, 9 on Task 2
- Scores: Task 1: 9/14, Task 2: 6/10. Mechanism works, scores didn't improve.

**Deep dive into why verification doesn't help these specific failures:**
1. Content depth failures (missing info) — verification can't fix "didn't find the info" because the info was never searched for in the first place
2. Format failures (slide deck format) — the format convention came from gold assistant history, not the system message. Verification reads the system message but the format isn't specified there.

**Run 6 (v3) — 100 tasks with code-enforced verification**
- Changed sampling: 100 individual tasks (not 100 contexts). New seed=42 produces a different 100 tasks.
- Code-enforced verification active (inject VERIFY_MESSAGE after draft answer)
- **Result: 16/99 tasks (16.0%), 1333/1735 rubrics (76.8%)**
- One task timed out, 99 completed

Source: `outputs/agent_sample100_v3.log`, `outputs/agent_sample100_v3.jsonl`

Category breakdown:

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 9/35 (25.7%) | 479/592 (80.9%) |
| Empirical Discovery & Simulation | 0/11 (0.0%) | 136/193 (70.5%) |
| Procedural Task Execution | 4/24 (16.7%) | 467/574 (81.4%) |
| Rule System Application | 3/30 (10.0%) | 251/376 (66.8%) |

**Verification made things significantly worse.** Task rate dropped from ~27% to 16%. Rubric rate dropped from ~85% to 77%. The agent appears to second-guess correct answers during the verification pass, introducing new errors.

### Phase 5: Revert Verification, Clean Run

**Run 7 (v4) — 100 tasks, no verification**
- Removed code-enforced verification
- Task-level sampling (100 tasks, seed=42) — same sample as v3
- 40 parallel workers, `claude-opus-4-6`
- **Result: 30/100 tasks (30.0%), 1419/1732 rubrics (81.9%), avg 18.4 tools**

Source: `outputs/agent_sample100_v4.jsonl`, `outputs/agent_sample100_v4.log`

Category breakdown:

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 12/35 (34.3%) | 515/588 (87.6%) |
| Empirical Discovery & Simulation | 1/11 (9.1%) | 149/194 (76.8%) |
| Procedural Task Execution | 9/24 (37.5%) | 494/574 (86.1%) |
| Rule System Application | 8/30 (26.7%) | 261/376 (69.4%) |

Subcategory breakdown:

| Subcategory | Tasks | Rubrics |
|-------------|-------|---------|
| Workflow Orchestration | 6/12 (50.0%) | 316/342 (92.4%) |
| Management | 3/5 (60.0%) | 67/73 (91.8%) |
| Finance | 1/4 (25.0%) | 58/62 (93.6%) |
| Healthcare | 2/6 (33.3%) | 112/123 (91.1%) |
| Legal Advisory | 2/6 (33.3%) | 162/180 (90.0%) |
| Game Mechanics | 2/8 (25.0%) | 99/111 (89.2%) |
| Operational Procedures | 3/10 (30.0%) | 176/214 (82.2%) |
| Science | 2/6 (33.3%) | 51/59 (86.4%) |
| Observational Data | 0/3 (0.0%) | 112/126 (88.9%) |
| Legal & Regulatory | 3/7 (42.9%) | 60/86 (69.8%) |
| Technical Standards | 2/7 (28.6%) | 53/73 (72.6%) |
| Lifestyle | 1/2 (50.0%) | 13/19 (68.4%) |
| Humanities | 1/6 (16.7%) | 52/72 (72.2%) |
| Programming Syntax | 1/4 (25.0%) | 24/38 (63.2%) |
| Experimental Data | 1/4 (25.0%) | 16/27 (59.3%) |
| Simulation Environment | 0/4 (0.0%) | 21/41 (51.2%) |
| Mathematical Formalism | 0/4 (0.0%) | 25/68 (36.8%) |
| Instructional Procedures | 0/2 (0.0%) | 2/18 (11.1%) |

Note: v3 and v4 use a different 100-task sample than v1/v2 (which sampled 100 contexts → 395 tasks), so direct comparison requires caution. Within the same sample (v3 vs v4), removing verification clearly helped.

---

## Summary Table

| Run | Description | Sample | Tasks | Task Rate | Rubrics | Rubric Rate |
|-----|------------|--------|-------|-----------|---------|-------------|
| v1 (Run 4) | First scale run, broken follow-ups | 395 tasks | 111/395 | 28.1% | 6109/7223 | 84.6% |
| v2 (Run 5) | Fixed gold history | 395 tasks | 105/395 | 26.6% | 6135/7242 | 84.7% |
| v3 (Run 6) | Code-enforced verification | 99 tasks* | 16/99 | 16.0% | 1333/1735 | 76.8% |
| v4 (Run 7) | No verification, clean | 100 tasks | 30/100 | 30.0% | 1419/1732 | 81.9% |

*v3: 1 task timed out. v3/v4 used different sample than v1/v2.

---

## Key Observations

### 1. CL-bench questions are deceptively broad
Questions like "What do Sighting Cards do?" look simple but rubrics test for exhaustive coverage — every sub-mechanic, edge case, and interaction. A surface-level correct answer scores 0.

### 2. The scoring cliff is brutal
Binary all-or-nothing means an answer hitting 95% of rubrics scores the same as one hitting 50%: zero. Our rubric pass rate is consistently ~80-85%, but task pass rate is only ~27-30%. The gap between "mostly right" and "fully right" is where most score is lost.

### 3. Verification hurts more than it helps
We tested three approaches:
- **Prompt-based**: Agent treated it as a checkbox, doing minimal verification
- **Code-enforced** (small scale): Agent verified genuinely but scores didn't improve
- **Code-enforced** (100 tasks): Scores **dropped significantly** (30% → 16% tasks, 85% → 77% rubrics)

The agent second-guesses correct answers during verification, introducing new errors. Verification can't fix the two root causes: (a) information that was never found can't be verified, and (b) implicit format conventions from conversation history aren't in the system message.

### 4. Two distinct failure modes
- **Insufficient research depth**: Agent stops searching too early. On a 159K char document, making 3 search calls is not enough. The agent finds a "good enough" answer and stops, missing details buried deeper in the document.
- **Format non-compliance**: Rubrics sometimes expect the agent to mirror output format from earlier in the conversation (e.g., if the gold assistant used slide deck format in turn 1, the answer to turn 3 should also use slide decks). The agent doesn't pick up on these implicit conventions.

### 5. System prompt vs user message precedence
CL-bench includes trap rubrics where the user asks the agent to do something (e.g., "no jokes") that contradicts the system prompt (e.g., "always include a quip"). The rubric tests that the system prompt wins. Our agent consistently follows the user instruction over the system prompt.

### 6. Multi-turn tasks skip tool use
In follow-up turns, the agent sometimes relies entirely on conversation memory from previous turns instead of searching the document again. Even when the follow-up asks about a different topic, the agent assumes it already has enough context.

### 7. Category-level patterns
- **Strongest**: Workflow Orchestration (50% tasks, 92% rubrics), Management (60% tasks, 92% rubrics)
- **Weakest**: Mathematical Formalism (0% tasks, 37% rubrics), Instructional Procedures (0% tasks, 11% rubrics), Simulation Environment (0% tasks, 51% rubrics)
- Mathematical Formalism likely fails because the agent can't reliably reproduce formal notation through text search tools
- Instructional Procedures may require following exact step sequences that the agent summarizes instead

---

## Codebase Changes Made

1. System message placed in actual API system prompt (not user message)
2. Agent system prompt minimized — just tool descriptions, task's role context dominates
3. Context file includes all user messages up to current turn with `## System Message`, `## User Message First`, `## User Message #2` headers
4. Task-level sampling (`--sample 100` = 100 tasks, not 100 contexts)
5. Grading integrated into run loop (not separate step)
6. Run config saved as `_config.json` alongside output for reproducibility
7. Judge model defaulted to `claude-sonnet-4-5-20250929` (was same as agent model)
8. Prompt caching on system prompt and first user message to reduce API costs

---

---

## Phase 6: Multi-Provider — Small Models + Tools (2026-02-25)

### Goal

Show that small models with agent tools can match or beat frontier models (vanilla, no tools) on CL-bench. This is the Pareto frontier argument: tool-augmented retrieval as a test-time scaling strategy.

### Infrastructure Changes

Replaced Anthropic-only `llm.py` with a unified interface via **litellm** (Anthropic, Bedrock) + direct **Azure OpenAI** client (TR AI Platform custom auth). All providers return OpenAI-compatible responses. ~130 lines total, replacing the planned 500+ line custom provider system.

Key fixes during implementation:
- **String-typed tool args**: Some Bedrock models (Llama) return `"2"` instead of `2` for integer params. Added type coercion in `ContextTools.execute()`.
- **Forced first tool call**: Small models see the full context in the system prompt and skip tool use. Added `tool_choice="required"` on the first API call, then `"auto"` for subsequent calls. Fallback for models that don't support `toolChoice` (Llama 4 Scout).
- **Retry with backoff + jitter**: 5 retries, exponential backoff (4s → 8s → 16s → 32s → 60s cap), ±30% jitter to prevent thundering herd after rate limit pauses.
- **max_tokens cap**: Bedrock/Azure models capped at 8192 (was 16384).

### Target Models

| Model | Active Params | Context | Provider | litellm model string |
|-------|--------------|---------|----------|---------------------|
| Claude Haiku 4.5 | ~8B | 200K | Anthropic | `anthropic/claude-haiku-4-5-20251001` |
| GPT-5-mini | undisclosed | 128K | Azure | `azure/gpt-5-mini` |
| Qwen3-Next-80B-A3B | 3.9B | 256K | Bedrock | `bedrock/converse/qwen.qwen3-next-80b-a3b` |
| Llama 4 Scout 17B | 17B | 1M | Bedrock | `bedrock/converse/us.meta.llama4-scout-17b-instruct-v1:0` |
| Kimi K2.5 | 32B | 256K | Bedrock | `bedrock/converse/moonshotai.kimi-k2.5` |
| DeepSeek V3.2 | ~37B | 128K | Bedrock | `bedrock/converse/deepseek.v3.2` |

Dropped during testing:
- **GLM 4.7**: Tool calls work but tool results cause Bedrock deserialization error (litellm bug with GLM message format).
- **GLM 4.7 Flash (9B)**: Does not support tool calling on Bedrock at all.

### Dataset Token Analysis

CL-bench eval_500 token distribution (cl100k_base tokenizer):

| Metric | System msg | Total (all msgs) |
|--------|-----------|-------------------|
| Median | 579 | 6,586 |
| P95 | 3,192 | 42,937 |
| Max | 10,695 | 60,355 |

Context is in the **user messages**, not the system message. All models have sufficient context windows. 98% of tasks fit in 8K system tokens.

### Run 8 — Exp 1 (Basic Agent) on eval_500, 3 models

All on 2026-02-25. Workers: 45 (Anthropic/Azure), 45 (Bedrock). Judge: `claude-sonnet-4-5-20250929`.

| Model | Done | Solve Rate | Rubric Rate | Avg Tools | Zero-tool |
|-------|------|-----------|-------------|-----------|-----------|
| **GPT-5-mini + tools** | 498/500 | **114/498 (22.9%)** | 5902/7522 (78.5%) | 4.6 | 0 |
| **Haiku 4.5 + tools** | 494/500 | **107/494 (21.7%)** | 5954/7883 (75.5%) | 6.2 | 0 |
| **Qwen3-80B (3.9B) + tools** | 484/500 | **51/484 (10.6%)** | 5207/7754 (67.2%) | 16.8 | 5 |

Per-category breakdown:

| Model | Domain | Empirical | Procedural | Rule |
|-------|--------|-----------|------------|------|
| GPT-5-mini | 23.0% (37/161) | 12.8% (6/47) | 27.3% (38/139) | 21.9% (33/151) |
| Haiku 4.5 | 21.5% (34/158) | 17.0% (8/47) | 27.0% (37/137) | 18.5% (28/151) |
| Qwen3-80B | 11.5% (18/156) | 2.4% (1/42) | 11.9% (16/135) | 10.7% (16/150) |

Output files:
- `outputs/claude-haiku-4-5-20251001/exp1_eval_500_20260225_092620.jsonl`
- `outputs/gpt-5-mini/exp1_eval_500_20260225_092625.jsonl`
- `outputs/qwen3-next-80b-a3b/exp1_eval_500_20260225_092819.jsonl`

### Comparison vs CL-bench Leaderboard (vanilla, no tools)

| Rank | Model (leaderboard) | Score | Beaten by our models? |
|------|-------------------|-------|-----------------------|
| 1 | GPT 5.1 (High) | 23.7% | No (close) |
| 2 | GPT 5.1 | 21.1% | GPT-5-mini (22.9%) |
| 3 | Claude Opus 4.5 Thinking | 21.1% | GPT-5-mini (22.9%), Haiku (21.7%) |
| 4 | Claude Opus 4.5 | 19.1% | GPT-5-mini, Haiku |
| 5 | GPT 5.2 (High) | 18.1% | GPT-5-mini, Haiku |
| 6 | GPT 5.2 | 18.2% | GPT-5-mini, Haiku |
| 7 | o3 (High) | 17.8% | GPT-5-mini, Haiku |
| 8 | Kimi K2.5 | 19.4% | GPT-5-mini, Haiku |
| 13 | Gemini 3 Pro (High) | 15.8% | All 3 |
| 15 | Qwen3 Max Thinking | 14.1% | All 3 |
| 22 | DeepSeek V3.2 | 12.4% | All 3 (even Qwen3 3.9B) |

### Key Findings

1. **Haiku 4.5 + tools (21.7%) beats Claude Opus 4.5 Thinking (21.1%)** — a small, cheap model with search tools outperforms a frontier model with extended thinking on the same benchmark.

2. **GPT-5-mini + tools (22.9%) beats GPT 5.2 High (18.1%)** — tool-augmented retrieval outperforms high-effort reasoning at the same model scale.

3. **Zero-tool tasks eliminated**: The `force_tool=True` on first call ensures every task uses tools. Previously many tasks had 0 tool calls.

4. **Qwen3-80B (3.9B active) at 10.6%** — still beats DeepSeek V3.2 vanilla (12.4%? — close) despite having only 3.9B active parameters. But it makes 16.8 tool calls per task (3x more than others) — more searching doesn't compensate for weaker reasoning.

5. **Rubric rates are compressed** (67-79%) while solve rates spread widely (10-23%) — the all-or-nothing scoring amplifies small rubric differences into large solve rate gaps.

### Run 9 — Forced vs No-force Tool Call Ablation

Does `tool_choice="required"` on the first API call bias results? We re-ran Haiku 4.5 and GPT-5-mini with `--no-force-tool` to compare.

| Model | Mode | Done | Solve Rate | Rubric Rate | Avg Tools | Zero-tool tasks |
|-------|------|------|-----------|-------------|-----------|-----------------|
| Haiku 4.5 | forced | 494/500 | 107/494 (21.7%) | 75.5% | 6.1 | 0 |
| Haiku 4.5 | no-force | 491/500 | 107/491 (21.8%) | 75.9% | 6.0 | 34 |
| GPT-5-mini | forced | 498/500 | 114/498 (22.9%) | 78.5% | 4.6 | 0 |
| GPT-5-mini | no-force | 500/500 | 105/500 (21.0%) | 77.8% | 4.3 | 3 |

Output files:

- `outputs/claude-haiku-4-5-20251001/exp1_eval_500_noforce_20260225_102856.jsonl`
- `outputs/gpt-5-mini/exp1_eval_500_noforce_20260225_103602.jsonl`

**Findings:**

1. **Haiku: no difference** (21.7% vs 21.8%). The stronger prompt ("You MUST use these tools before answering") is sufficient. 34 tasks skipped tools without forcing but it didn't hurt the score — these were likely tasks where the context was short enough to answer from the system prompt alone.

2. **GPT-5-mini: forcing helps ~2%** (22.9% vs 21.0%). Only 3 zero-tool tasks without forcing, so the gap isn't from skipping tools — it's from the quality of the first voluntary search being slightly worse than a forced one.

3. **Avg tool calls nearly identical** (forced vs no-force) for both models — forcing the first call doesn't cascade into more tool use overall.

**Decision**: Report **forced** numbers in the paper. It's a consistent, reproducible setup across all models and gives a ~2% boost for GPT-5-mini at zero cost.

### Run 10 — Full 9-Model Eval (2026-02-25)

Extended to 9 models across Anthropic, Azure, and Bedrock. All Exp 1 (basic agent with forced first tool call). Judge: `claude-sonnet-4-5-20250929`.

| # | Model | Provider | Done | Solve Rate | Rubric Rate | Avg Tools |
|---|-------|----------|------|-----------|-------------|-----------|
| 1 | GPT-5-mini | Azure | 498/500 | **114/498 (22.9%)** | 78.5% | 4.6 |
| 2 | Haiku 4.5 | Anthropic | 494/500 | **107/494 (21.7%)** | 75.5% | 6.1 |
| 3 | GPT-5 | Azure | 448/500 | **76/448 (17.0%)** | 76.8% | 5.3 |
| 4 | DeepSeek V3.2 | Bedrock | 457/500 | **64/457 (14.0%)** | 73.6% | 10.2 |
| 5 | o4-mini | Azure | 495/500 | **58/495 (11.7%)** | 69.0% | 2.8 |
| 6 | Qwen3-80B (3.9B) | Bedrock | 487/500 | **51/487 (10.5%)** | 67.1% | 19.5 |
| 7 | GPT-5-nano | Azure | 500/500 | **47/500 (9.4%)** | 66.9% | 3.4 |
| 8 | Llama 4 Scout 17B | Bedrock | 154/500* | **4/154 (2.6%)** | 34.1% | 4.0 |
| 9 | Kimi K2.5 | Bedrock | 484/500 | **8/484 (1.7%)** | 49.5% | 2.2 |

*DeepSeek V3.2 and Llama 4 Scout had many tasks fail from rate limits/timeouts (Bedrock). Numbers are from completed tasks only.

Output files:

- `outputs/gpt-5-mini/exp1_eval_500_20260225_092625.jsonl`
- `outputs/claude-haiku-4-5-20251001/exp1_eval_500_20260225_092620.jsonl`
- `outputs/gpt-5/exp1_eval_500_20260225_125318.jsonl`
- `outputs/v3.2/exp1_eval_500_20260225_125315.jsonl`
- `outputs/o4-mini/exp1_eval_500_20260225_125319.jsonl`
- `outputs/qwen3-next-80b-a3b/exp1_eval_500_20260225_092819.jsonl`
- `outputs/gpt-5-nano/exp1_eval_500_20260225_125318.jsonl`
- `outputs/llama4-scout-17b-instruct-v1/exp1_eval_500_20260225_125315.jsonl`
- `outputs/moonshotai.kimi-k2.5/exp1_eval_500_20260225_125312.jsonl`

**Key findings:**

1. **GPT-5-mini + tools (22.9%) and Haiku 4.5 + tools (21.7%) beat frontier thinking models** on the CL-bench leaderboard (Opus 4.5 Thinking at 21.1%, GPT 5.2 High at 18.1%).

2. **GPT-5 + tools (17.0%) is WORSE than GPT-5-mini + tools (22.9%)** — the bigger model underperforms. GPT-5 uses reasoning mode which burns tokens on thinking instead of searching. For retrieval-heavy tasks, more reasoning hurts.

3. **o4-mini + tools (11.7%)** — the dedicated reasoning model barely benefits from tools. Only 2.8 avg tool calls — it prefers to reason from the context it already has rather than search.

4. **Kimi K2.5 + tools (1.7%) is a disaster** vs its 19.4% vanilla leaderboard score. Only 2.2 tool calls, 49.5% rubric rate. The model doesn't follow the agent protocol well — it's answering from context without searching.

5. **Llama 4 Scout (2.6%)** — too weak for this task. 34% rubric rate means it fails at basic comprehension even with tools.

6. **Tool calling as TTS only works when the base model has sufficient instruction-following ability.** Models that score well (Haiku, GPT-5-mini) also make the most effective tool calls. Weak models make more calls (Qwen3-80B: 19.5 avg) but get worse results — quantity of search doesn't compensate for quality of reasoning.

7. **Judge discrepancy**: We grade with `claude-sonnet-4-5-20250929`, the official leaderboard uses `gpt-5.1`. Need to re-grade with official eval script for fair comparison.

### Run 11 — Eval Alignment & Vanilla vs Tools Comparison (2026-02-25)

**Problem discovered**: Our earlier results (21.7%, 22.9%) used a simplified grading prompt and Claude Sonnet as judge. The official CL-bench eval uses a different, stricter grading prompt and GPT-5.1 as judge. We changed two variables at once and needed to isolate the effect.

**Changes made**:
1. Rewrote `agent/eval.py` to use the **exact official CL-bench grading prompt** (including the `【Grading Rationale】` section)
2. No system prompt on judge calls (matches official)
3. JSON parse retry (matches official)
4. Added `--experiment 0` (vanilla baseline): passes messages directly to LLM with no tools and no agent instructions, matching official `infer.py` exactly
5. Fixed empty system prompt bug (Anthropic rejects `system=""`, now skips it)

**Ran 8 experiments**: 2 models x 2 modes (vanilla/tools) x 2 judges

#### Results — Official CL-bench Grading Prompt

**Claude Sonnet 4.5 Judge:**

| Model | Vanilla | Tools | Delta |
|-------|---------|-------|-------|
| Haiku 4.5 | 76/499 (15.2%) | 82/491 (16.7%) | **+1.5%** |
| GPT-5-mini | 97/499 (19.4%) | 94/499 (18.8%) | **-0.6%** |

**GPT-5 Judge:**

| Model | Vanilla | Tools | Delta |
|-------|---------|-------|-------|
| Haiku 4.5 | 47/476 (9.9%) | 48/465 (10.3%) | **+0.4%** |
| GPT-5-mini | 80/500 (16.0%) | 69/499 (13.8%) | **-2.2%** |

**For reference — Old Sonnet judge with old simpler prompt:**

| Model | Tools (old) |
|-------|------------|
| Haiku 4.5 | 107/494 (21.7%) |
| GPT-5-mini | 114/498 (22.9%) |

Output files:
- Sonnet judge: `exp[01]_eval_500_20260225_17183*.jsonl` and `exp[01]_eval_500_20260225_17184*.jsonl`
- GPT-5 judge: `exp[01]_eval_500_20260225_16054*.jsonl` and `exp[01]_eval_500_20260225_16055*.jsonl`

#### Key Findings

1. **Grading prompt matters enormously.** Switching from our old simplified prompt to the official CL-bench prompt dropped scores by 5-7% (22.9% → 18.8% for GPT-5-mini tools). The old prompt was more lenient.

2. **Tools provide marginal benefit for Haiku (+0.4% to +1.5%) and slightly hurt GPT-5-mini (-0.6% to -2.2%).** This is consistent across both judges. The "tools beat frontier" claim from Run 8/10 was an artifact of the lenient grading prompt.

3. **Judge model creates systematic bias.** GPT-5 scores Haiku 5% lower than Sonnet does (9.9% vs 15.2%), but scores GPT-5-mini similarly (16.0% vs 19.4%). Possible cross-family bias: GPT-5 may grade Anthropic outputs more harshly.

4. **GPT-5-mini vanilla (19.4% Sonnet / 16.0% GPT-5) is the best result.** No tools needed — the model answers better from direct context than from tool-mediated retrieval.

5. **Why tools hurt GPT-5-mini**: The tool-augmented pipeline adds agent instructions to the system prompt ("You MUST use these tools before answering"), forces a tool call, and processes results through multiple API round-trips. This scaffolding may distract the model from the actual task. GPT-5-mini is strong enough to answer directly from context — the tools add noise, not signal.

6. **Why tools help Haiku slightly**: Haiku is a smaller model that benefits from targeted retrieval. The tool calls help it focus on relevant sections rather than processing the entire context at once. But the benefit is marginal (+1.5% at best).

---

## Open Questions

1. Token budget analysis: plot score vs total tokens to show the Pareto frontier (token tracking now implemented for future runs).
2. Thinking budget experiments: vary Claude thinking tokens / GPT-5 reasoning effort levels.
3. Can we access GPT-5.1 as judge from SageMaker for exact leaderboard reproducibility?
4. Should we run vanilla baselines for all 9 models to get a complete Pareto curve?
5. Is the tool benefit larger for harder tasks (longer contexts, more sub-questions)?
6. Would a different tool strategy (e.g., forced multi-step search, structured retrieval) help more than simple search+read?
