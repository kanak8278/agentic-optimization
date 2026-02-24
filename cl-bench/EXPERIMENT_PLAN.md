# CL-bench Agentic Solver: Experiment Plan

## Blog Post Thesis

**Can agentic scaffolding improve LLM context learning?**

CL-bench tests whether LLMs can learn from provided context (not pre-trained knowledge) to solve complex tasks. The best model (GPT-5.1 High) scores 23.7%. Average across 10 frontier models is 17.2%. We build an agent with search/read tools over the reference document and systematically test what helps and what doesn't.

**Leaderboard reference (full 1,899 tasks):**

| Model | Solving Rate |
|-------|-------------|
| GPT-5.1 (High) | 23.7% |
| GPT-5.1 | 21.1% |
| Claude Opus 4.5 Thinking | 21.1% |
| Claude Opus 4.5 | 19.1% |
| Kimi K2.5 | 19.4% |
| Average (10 models) | 17.2% |

---

## Model

All experiments use **`claude-opus-4-5-20251101`** for both the agent and generator.

Judge model: `claude-sonnet-4-5-20250929` (for grading).

---

## Dataset Splits

- **Observation set**: `data/observation_8.jsonl` — 8 tasks (2 per category, multi-turn preferred, seed=42). For development, debugging, qualitative analysis. Results never reported.
- **Evaluation set**: `data/eval_500.jsonl` — 500 tasks (sampled, seed=42). All reported numbers. Task IDs locked in `data/eval_500_task_ids.json`.
- **Full run**: All 1,899 tasks (`CL-bench.jsonl`). Decision on whether to run after eval results.

Eval set category distribution: Domain Knowledge 161, Rule Systems 153, Procedural Tasks 139, Empirical Discovery 47.

We never tune on the evaluation set.

---

## Experiments

### Experiment 1: Basic Agent (Search + Read, No Verification)

**What**: Agent with `search_context` (regex) and `read_lines` tools. Agent loop: LLM calls tools iteratively until it produces a text-only response (the answer). No verification step.

**Why**: This is our core hypothesis test — does giving the LLM the ability to incrementally search and read the document improve context learning over raw LLM inference?

**Hypothesis**: The agent should outperform raw LLM (leaderboard: Opus 4.5 at 19.1%) because it can focus attention on specific parts of the document rather than processing everything at once.

**Architecture**:
- Task's system message → API system prompt (dominant)
- Agent instructions (tool descriptions + rules) → appended to system prompt
- Reference document → temp file, accessed via tools
- Loop: LLM response → tool calls? → execute → feed back → repeat until text answer

**Key variable**: Tools + agent loop vs no tools.

**Results (500 tasks, seed=42, claude-opus-4-5-20251101):**

| Metric | Value |
|--------|-------|
| Solving rate | **146/500 (29.2%)** |
| Rubric pass rate | 6593/8050 (81.9%) |
| Avg tool calls | 6.0 |
| Avg time/task | 59s |
| Grading errors | 87 |

By category:

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 51/161 (31.7%) | 2150/2615 (82.2%) |
| Empirical Discovery & Simulation | 12/47 (25.5%) | 403/529 (76.2%) |
| Procedural Task Execution | 46/139 (33.1%) | 2368/2768 (85.5%) |
| Rule System Application | 37/153 (24.2%) | 1672/2138 (78.2%) |

Top subcategories: Management 75.0%, Workflow Orchestration 47.8%, Legal Advisory 39.3%
Bottom subcategories: Lifestyle 0.0%, Mathematical Formalism 5.6%, Instructional Procedures 5.9%

Leaderboard comparison (theirs on 1,899 tasks, ours on 500):
- **Our agent (Opus 4.5 + tools): 29.2%**
- GPT-5.1 High: 23.7%
- Claude Opus 4.5 Thinking: 21.1%
- Claude Opus 4.5 (no tools): 19.1%

Output: `outputs/exp1_eval.jsonl`, config: `outputs/exp1_eval_config.json`

**Full run (1,899 tasks):**

| Metric | Value |
|--------|-------|
| Solving rate | **539/1899 (28.4%)** |
| Rubric pass rate | 25998/31581 (82.3%) |
| Avg tool calls | 5.9 |
| Avg time/task | 61s |
| Grading errors | 354 |

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 210/663 (31.7%) | 9447/11091 (85.2%) |
| Empirical Discovery & Simulation | 41/199 (20.6%) | 2092/2732 (76.6%) |
| Procedural Task Execution | 145/471 (30.8%) | 7931/9472 (83.7%) |
| Rule System Application | 143/566 (25.3%) | 6528/8286 (78.8%) |

**Beats every model on the CL-bench leaderboard** (GPT-5.1 High: 23.7%, Opus 4.5: 19.1%).

Output: `outputs/exp1_full.jsonl`, config: `outputs/exp1_full_config.json`

---

### Experiment 2: Agent + Self-Verification (System Prompt)

**What**: Same as Exp 1, but add verification instructions to the system prompt. Tell the agent to follow a 3-phase workflow: RESEARCH → VERIFY → RESPOND. The agent is instructed to re-read the system message and check its answer before responding.

**Why**: Tests the cheapest possible verification — just tell the LLM to check its own work. No code changes, no extra API calls.

**Hypothesis**: Prompt-based verification will be shallow. The LLM will treat it as a checkbox, not genuinely re-examine its answer. Minimal impact on scores.

**What changes from Exp 1**: Modified system prompt only. Same tools, same loop.

**Results (500 tasks, seed=42, claude-opus-4-5-20251101):**

| Metric | Exp 1 | Exp 2 | Delta |
|--------|-------|-------|-------|
| Solving rate | 146/500 (29.2%) | **140/500 (28.0%)** | -1.2% |
| Rubric pass rate | 81.9% | 81.9% | 0.0% |
| Avg tool calls | 6.0 | 6.8 | +0.8 |
| Avg time/task | 59s | 62s | +3s |
| Grading errors | 87 | 87 | 0 |

By category:

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 49/161 (30.4%) | 2171/2615 (83.0%) |
| Empirical Discovery & Simulation | 11/47 (23.4%) | 402/529 (76.0%) |
| Procedural Task Execution | 42/139 (30.2%) | 2353/2766 (85.1%) |
| Rule System Application | 38/153 (24.8%) | 1669/2138 (78.1%) |

**Conclusion**: Prompt-based verification had no meaningful impact. Rubric rate identical, solving rate marginally worse. The agent used slightly more tools but the verification instruction was treated as a checkbox.

Output: `outputs/exp2_eval.jsonl`, config: `outputs/exp2_eval_config.json`

---

### Experiment 3: Agent + Self-Verification (Code-Enforced)

**What**: Same as Exp 1, but after the agent generates its first answer, the code injects a follow-up user message (`VERIFY_MESSAGE`) asking it to verify against the system message, check completeness, verify facts with tools, and check output format. The agent re-enters the tool loop and produces a final answer.

**Why**: Tests whether *forcing* a verification pass catches errors that prompt-based verification misses. The agent must now genuinely re-engage with the document.

**Hypothesis**: The agent will verify more thoroughly than Exp 2, but may second-guess correct answers. The same LLM context that generated the answer will struggle to objectively critique it.

**What changes from Exp 1**: After first text response, inject VERIFY_MESSAGE as user message, agent continues with tools. Two-phase: draft → verify → final.

**Results (499 tasks*, seed=42, claude-opus-4-5-20251101):**

*1 task errored out.

| Metric | Exp 1 | Exp 2 | Exp 3 | Delta (1→3) |
|--------|-------|-------|-------|-------------|
| Solving rate | 146/500 (29.2%) | 140/500 (28.0%) | **131/499 (26.3%)** | **-2.9%** |
| Rubric pass rate | 81.9% | 81.9% | 80.2% | -1.7% |
| Avg tool calls | 6.0 | 6.8 | 13.6 | +7.6 |
| Avg time/task | 59s | 62s | 106s | +47s |
| Grading errors | 87 | 87 | 91 | +4 |

By category:

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 46/161 (28.6%) | 2162/2615 (82.7%) |
| Empirical Discovery & Simulation | 10/47 (21.3%) | 387/530 (73.0%) |
| Procedural Task Execution | 42/139 (30.2%) | 2245/2766 (81.2%) |
| Rule System Application | 33/152 (21.7%) | 1619/2086 (77.6%) |

**Conclusion**: Code-enforced verification made things worse. 2x tool calls, 2x time, -3 percentage points on solving rate. The agent second-guesses correct answers during verification, introducing new errors. Verification cannot fix the root cause (information never found in the first place).

Output: `outputs/exp3_eval.jsonl`, config: `outputs/exp3_eval_config.json`

---

### Experiment 4: Two-Agent Architecture (Generator + Verifier)

**What**: Two separate LLM agents with distinct roles:

**Phase 1 — Generator**: Same as Exp 1. Searches document, produces answer.

**Phase 2 — Verifier**: Fresh LLM context. Receives:
- The reference document (via tools — same search/read access)
- The generator's answer (as text to evaluate)
- The original question

The verifier's job (in order):
1. Read the system message from the context to understand the role, persona, and constraints
2. Read the user question to understand what's being asked
3. **Generate its own checklist** from the context: What should be in the answer? What tone/personality? What format? What specific facts?
4. Compare the generator's answer against this self-derived checklist
5. Search the document to fact-check specific claims in the answer
6. Produce structured feedback: a list of specific issues to fix (missing info, wrong facts, format violations, tone mismatches)

**Phase 3 — Revision**: The generator receives the verifier's feedback as a new user message. It must:
1. First validate the feedback (the verifier might be wrong)
2. Then improve the answer based on valid feedback
3. This revised answer is the final submission

**Why**: Exp 3 showed self-verification hurts because the same context second-guesses itself. A fresh agent that independently derives what the answer *should* contain — without seeing rubrics — is a more honest test of whether verification can work.

**Hypothesis**: The verifier's fresh perspective will catch genuine errors (format, tone, missing facts) without the self-second-guessing problem. However, it adds latency and cost (3 LLM calls instead of 1). The revision step where the generator validates feedback before applying it should prevent the verifier from introducing new errors.

**Key design decisions**:
- Verifier does NOT receive the rubrics (that would be cheating)
- Verifier derives its own checklist from the context itself
- Generator validates feedback before applying (prevents blind trust in verifier)
- Single revision cycle only (generator → verifier → revision). No infinite loops.
- Verifier model: same as generator (`claude-opus-4-5-20251101`) — we want fair comparison, not cost optimization

**Results (499 tasks*, seed=42, claude-opus-4-5-20251101):**

*1 task errored out.

| Metric | Exp 1 | Exp 2 | Exp 3 | Exp 4 |
|--------|-------|-------|-------|-------|
| Solving rate | 146/500 (29.2%) | 140/500 (28.0%) | 131/499 (26.3%) | **119/499 (23.8%)** |
| Rubric pass rate | 81.9% | 81.9% | 80.2% | 78.7% |
| Avg tool calls | 6.0 | 6.8 | 13.6 | 16.1 |
| Avg time/task | 59s | 62s | 106s | 131s |
| Grading errors | 87 | 87 | 91 | 94 |

By category:

| Category | Tasks | Rubrics |
|----------|-------|---------|
| Domain Knowledge Reasoning | 33/160 (20.6%) | 2090/2599 (80.4%) |
| Empirical Discovery & Simulation | 10/47 (21.3%) | 388/529 (73.3%) |
| Procedural Task Execution | 42/139 (30.2%) | 2239/2766 (80.9%) |
| Rule System Application | 34/153 (22.2%) | 1592/2123 (75.0%) |

**Conclusion**: The two-agent architecture performed worst of all experiments. Despite using a fresh context for verification and having the generator validate feedback, scores dropped further. The verifier introduces noise that the generator cannot reliably filter. Domain Knowledge Reasoning was hit hardest (31.7% → 20.6%). More verification = worse results, regardless of mechanism.

Output: `outputs/exp4_eval.jsonl`, config: `outputs/exp4_eval_config.json`

---

### Experiment 5: Enhanced Search Depth

**What**: Same agent as Exp 1, but with modifications to encourage deeper document exploration:

Possible changes (to be finalized after observation set analysis):
- Increase `max_matches` in search tool (10 → 20 or higher)
- Add a `get_outline` tool that returns document structure / section headers
- System prompt instruction: "For comprehensive questions, search at least 5 different patterns before answering"
- Increase `context_lines` in search results for better surrounding context

**Why**: Analysis of failed tasks shows the #1 failure mode is insufficient search depth. The agent finds a "good enough" answer after 3-5 searches and stops, missing details buried in other parts of the document.

**Hypothesis**: Better tools and explicit depth instructions will increase rubric pass rate. Since many tasks fail by just 1-2 rubrics (the scoring cliff), even small improvements in completeness should push tasks over the threshold.

**What changes from Exp 1**: Tool configuration and/or system prompt. Same architecture.

---

## Experiment Matrix

| Exp | Description | Verification | Key Question |
|-----|------------|-------------|-------------|
| 1 | Basic agent (search + read) | None | Does agentic scaffolding help? |
| 2 | Agent + prompt verification | Self (prompt) | Does telling it to verify help? |
| 3 | Agent + code-enforced verification | Self (forced) | Does forcing verification help? |
| 4 | Generator + Verifier (two agents) | External agent | Does external verification help? |
| 5 | Enhanced search depth | None | Does searching deeper help? |

---

## Run Configuration

For each experiment:
- **Model (agent/generator)**: `claude-opus-4-5-20251101`
- **Model (verifier, Exp 4)**: `claude-opus-4-5-20251101`
- **Model (judge)**: `claude-sonnet-4-5-20250929`
- **Workers**: 40 (parallel)
- **Seed**: 42
- **Max tool calls**: None (unlimited)
- **Evaluation set**: 500 tasks (sampled with seed=42)

Config saved as `_config.json` alongside each output file for reproducibility.

All experiments re-run from scratch. No results carried over from previous runs (different model, different configs).

---

## Metrics

### Primary
- **Solving Rate** (task-level): % of tasks where ALL rubrics pass. Official CL-bench metric. Directly comparable to leaderboard.

### Secondary
- **Rubric Pass Rate**: % of individual rubrics passed. Shows proximity to passing — 95% rubrics still = score 0.
- **Tool Call Count**: Average tool calls per task. Measures search effort.
- **Per-Category Breakdown**: Solving rate by the 4 categories (Domain Knowledge, Rule Systems, Procedural Tasks, Empirical Discovery) and 18 subcategories.
- **Latency / Cost**: Average time and API cost per task per experiment.

### Diagnostic (observation set only)
- **Failure mode classification**: For failed tasks, why? Insufficient search, format error, system prompt violation, incorrect reasoning, missing information, etc.

---

## Execution Order

1. **Fix output format** (JSON array instead of JSONL) — prerequisite for clean runs
2. **Define observation set** — select 10 contexts, extract tasks
3. **Run Exp 1** on observation set → analyze failures → validate that experiment setup works
4. **Run Exp 1** on 500-task evaluation set → get baseline number
5. **Run Exp 2** on evaluation set
6. **Run Exp 3** on evaluation set
7. **Build Exp 4** (two-agent architecture) → test on observation set → run on evaluation set
8. **Design Exp 5** based on failure analysis from Exp 1-4 → test on observation set → run on evaluation set
9. **Run best-performing experiment** on full 1,899 tasks → headline number
10. **Write blog post**

---

## Blog Narrative Arc

1. **The Problem**: CL-bench is hard. Best model gets 23.7%. Context learning is a fundamental gap.
2. **The Idea**: What if the LLM could search the document like a human — ctrl+F, read sections, build understanding piece by piece?
3. **Experiment 1 — The Agent**: Adding search/read tools → X%. [Hopefully meaningful improvement over 19.1% baseline.]
4. **Experiment 2-3 — Can Verification Help?**: Self-verification (prompted and forced) → results. [Expected: doesn't help or hurts.]
5. **Experiment 4 — Separate Verifier**: Two-agent architecture where the verifier independently derives what the answer should contain → results.
6. **Experiment 5 — Search Deeper**: Addressing the root cause (insufficient document exploration) → results.
7. **Analysis**: What works, what doesn't, and why. Failure mode breakdown. The scoring cliff problem. Transferable insights about agentic scaffolding.
8. **Comparison to leaderboard**: Where our best approach lands vs frontier models.
