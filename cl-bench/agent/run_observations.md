# Run Observations

## Run 1 — 2026-02-15 01:51
- Tasks: 2 (Game Mechanics, Rule System Application)
- Model: claude-sonnet-4-5-20250929
- Result: 0/2 scored

### Task 1: "What do Sighting Cards do?"
- Score: 0 (11/14 rubrics passed)
- Question was vague — just "what do Sighting Cards do?" but rubrics expected 14 specific details
- Agent stopped searching too early — found the basics (4 types, scoring role) but missed:
  - Gameplay sequence for revealing sightings (reveal → check → resolve)
  - Encounter site selection rules (most humans + hiding spot, tiebreaker)
  - Partial resolution mechanics (what if effect can't fully resolve)

### Task 2: "What actions can I take during my turn?"
- Score: 0 (10/15 rubrics passed)
- Format violations: Used numbered lists when question explicitly said "use bullet points not numbered list"
- Trap rubric: User says "leave jokes out" but system prompt says always include jokes. Rubric tests that system prompt overrides user request. Agent followed user instruction (wrong).
- Missing details: Deck exhaustion mechanics, draw-to-5 rule, what happens after playing a card
- Agent used 0 tool calls on this task — answered entirely from conversation memory of turn 1. Should have searched.

### Observations

1. **Questions are vague, rubrics expect completeness.** CL-bench questions often ask broad questions ("what does X do?") but rubrics test for exhaustive coverage of all related rules/mechanics.

2. **Agent doesn't search deeply enough.** On task 1, the agent made only 3 tool calls and stopped. Found the surface-level answer but missed 3 specific sub-mechanics.

3. **Follow-up tasks may skip tool use entirely.** Task 2 used 0 tool calls — the agent relied on conversation history from task 1. But the follow-up asked about different mechanics (action cards, not sighting cards).

4. **Format instructions matter and must be followed exactly.** "Bullet points not numbered lists" — the agent used numbered lists anyway.

5. **System prompt vs user message precedence.** The benchmark tests whether the model respects the system prompt (role context) over conflicting user requests. Our agent dumps the system msg as part of the user message — this may confuse precedence.

6. **Meta-commentary in answers.** First answer started with "Perfect! Now I have all the information needed..." despite the prompt saying not to do this.

## Run 2 — 2026-02-15 02:17
- Change: Moved their system message into actual system prompt (was in user message before)
- Tasks: 2 (same Game Mechanics tasks)
- Result: 0/2 scored, rubrics 21/29 (72.4%)
- Task 1: 10/14 (dropped 1 — lost rubric 6 "players can look at own sighting cards")
- Task 2: 11/15 (gained 1 — picked up rubric on card resolution)
- Task 2 now uses 19 tool calls (was 0 in run 1)
- Still failing: joke rubric, bullet points, same 3 deep sighting card mechanics

## Run 3 — 2026-02-15 02:27
- Change: Simplified agent system prompt — minimal tool instructions only, their role context is dominant voice
- Tasks: 2 (same Game Mechanics tasks)
- Result: 0/2 scored, rubrics 22/29 (75.9%)
- Task 1: 11/14 (back to run 1 level, same 3 failures: reveal sequence, encounter site, partial resolution)
- Task 2: 11/15 (same as run 2, same 4 failures: bullet points, joke, draw-to-5, deck exhaustion)
- Task 2 used 20 tool calls — agent is actively searching now
- Persona adoption improved — answer starts with conspiracy theorist tone

### Persistent failures across all runs
- **Task 1 rubrics 5, 11, 14**: Agent consistently misses 3 specific sub-mechanics of sighting cards. Only makes 3 tool calls and stops. Needs to search more thoroughly.
- **Task 2 rubric 1 (bullet points)**: Agent keeps using numbered lists despite explicit instruction.
- **Task 2 rubric 3 (joke)**: Agent obeys user "no jokes" instead of system prompt "always quip". System prompt authority still not strong enough.
- **Task 2 rubrics 8, 15 (draw-to-5, deck exhaustion)**: Agent searches for these topics but doesn't include them in the answer.

## Run 4 (100-sample, v1 code) — 2026-02-15
- Sample: 100 contexts → 395 tasks (context-level sampling)
- Workers: 25
- Result: **111/395 tasks (28.1%), 6109/7223 rubrics (84.6%)**
- Note: This run had the broken follow-up bug (multi-turn tasks used garbled messages)

## Verification Experiments — 2026-02-15

### Experiment: Prompt-based verification (PHASE 2 MANDATORY)
- Added three-phase workflow to system prompt: RESEARCH → VERIFY (MANDATORY) → RESPOND
- Required agent to call `search_context("## System Message")` before answering
- Result: Agent DID make the verification tool call, but only step 1 (read system message). Skipped steps 2-5 (check all parts, verify facts, check format). Treated it as a checkbox.
- Scores: Task 1: 9/14, Task 2: 7/10 (slight improvement on Task 2 vs no-verify 6/10)

### Experiment: Code-enforced verification (injected user message)
- Removed verification from system prompt. After agent's first answer, inject a user message asking it to verify using tools, then re-enter the agent loop.
- Result: Agent now does genuine verification — Task 1: 4 verification tool calls, Task 2: 9 verification tool calls.
- Scores: Task 1: 9/14, Task 2: 6/10. Mechanism works but scores didn't improve.

### Deep dive into rubric failures

**Task 1 (Game Mechanics, 9/14)** — 5 failures are all **content depth**:
- Missing "award/penalize Myth" in definition
- Missing gameplay sequence for revealing sightings (exact order)
- Missing "can look at own cards anytime, others hidden"
- Missing encounter site selection rules (most humans + hiding spot, tiebreaker)
- Missing "partial resolve" mechanic
- Root cause: 159K char rulebook, agent only made 3 search calls. Not enough research depth.

**Task 2 (Operational Procedures, 6/10)** — 4 failures are all **format**:
- Not in slide deck format (rubric: "present as slide deck")
- No slide numbers/titles
- No max 5 bullet points per slide
- No "next steps" section
- Root cause: The gold assistant's turn 1 response used slide deck format. Rubrics expect the same for turn 3. The user's question doesn't mention slides — it's an implicit format convention from the conversation history. The agent has access to the gold history but doesn't mirror the established output pattern.

### Key findings

1. **Two distinct failure modes:**
   - **Insufficient research depth** — agent stops searching too early on large documents. 3 tool calls for a 159K document is not enough.
   - **Format non-compliance** — agent doesn't pick up on implicit format conventions from conversation history (e.g., previous answers used slide decks, so the next one should too).

2. **Verification helps mechanically but not on these failure types:**
   - Verification can't fix "didn't find the info" — the info was never searched for.
   - Verification reads back the system message but system message doesn't mention slide decks — the format convention is in the gold assistant history.

3. **Context file now includes all user messages with ## headers** for better searchability during verification. But the gold assistant messages (which establish format conventions) are NOT in the context file — they're only in the conversation.

### Changes made to codebase
- Removed context grouping from `run.py` — `--sample 100` now means 100 tasks, not 100 contexts
- `write_context_file` now includes all user messages with `## System Message`, `## User Message First`, `## User Message #2` headers
- Added code-enforced verification: after agent's first answer, injects `VERIFY_MESSAGE` as user message and re-enters the agent loop with tools
- System prompt simplified to research-focused rules only (no verification instructions)
