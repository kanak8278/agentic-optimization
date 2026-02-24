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

## Open Questions

1. How to make the agent search more deeply on large documents? Current prompt says "always search" but the agent decides 3 searches is enough.
2. How to make the agent pick up implicit format conventions from conversation history?
3. Is the scoring cliff (80%+ rubrics but ~30% tasks) addressable, or is it inherent to the all-or-nothing scoring?
4. Would a different model (e.g., Sonnet for generation) perform differently on the rubric-level?
5. Does increasing `max_tokens` or adding explicit "be exhaustive" instructions help with content depth?
