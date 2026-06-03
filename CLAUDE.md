# Agentic Optimization System

## AWS Authentication (Required for S3 and Mariner)

Run `awslogin` before: S3 downloads, S3 dataset reads, Mariner-based configs.

```bash
awslogin                    # Uses cached password (try this first)
awslogin 'your_password'    # Pass new password if cached one expired
awslogin --help             # Show all options
```

- Password from **CyberArk/EPV Portal** — expires daily (~24 hours)
- If `awslogin` fails or S3 returns `ExpiredToken`, get a new password from CyberArk
- Claude Code cannot retrieve CyberArk passwords — user must provide it

Default assumed role: `arn:aws:iam::451191978663:role/service-role/a204383-ml-workspace-TRGPT24aB-prod-use1`

AWS profiles created: `tr-labs-prod` (base), `assumed-role` (TRGPT S3/Mariner access).
Whenever running any access to bedrock should be authenticated with `awslogin` first to ensure valid credentials and run with assumed role.

## Project Phase: EXPLORATION

We are in the research and idea exploration phase. No architecture is committed. No code is being written yet. The goal is to deeply understand the problem space, existing systems, and identify genuinely novel approaches before building anything.

## What This Project Is

Building an agentic optimization system — a system that uses LLMs to iteratively search over programs/solutions, evolving them toward better performance on a target task. Think: evolutionary search where the LLM is the mutation operator, but with fundamentally better mechanisms than what currently exists. We will always explore ideas from lateral fields (neuroscience, information theory, ecology, older ML) to break out into genuinely new territory.

## Existing Systems We're Studying

### Direct Competitors

- **Poetiq**: LLM-agnostic meta-system. Recursive generate→evaluate→reflect→refine loop. Adaptive model selection. Beat ARC-AGI benchmarks. Key idea: prompt as interface, not intelligence.
- **GEPA** ("Reflective Prompt Evolution Can Outperform RL"): Natural language reflection replaces scalar reward signals. 35x fewer rollouts than GRPO, 10-20% better. Key idea: language as learning medium.
- **ACE** (Agentic Context Engineering): Generator→Reflector→Curator loop with structured "Playbook" memory. Incremental deltas prevent context collapse. Key idea: structured evolving memory.
- **FunSearch** (DeepMind): Island-based evolutionary search, LLM as mutation operator, program database with fitness. Discovered novel math results. Key idea: search in program space, not solution space.
- **OpenELM**: LLM-driven mutation/crossover in evolutionary algorithms. Integrates MAP-Elites for quality-diversity. Key idea: LLMs as semantic genetic operators.
- **EvoPrompting**: Evolutionary search + LLM for neural architecture search.
- **ReEvo**: LLM-evolved heuristics with reflective component. Outperformed FunSearch with fewer calls.
- **DSPy/MIPROv2**: Prompt optimization via Bayesian surrogate models.

### "AI Solves Big Problems" Systems (Discovery-class)

These go beyond optimization — they discover genuinely new knowledge:

- **AlphaEvolve** (DeepMind, 2025): Evolutionary coding agent using Gemini Flash (breadth) + Pro (depth) ensemble. Full codebase evolution, not just single functions. Prompt sampler → LLM generation → automated evaluation → evolutionary selection. Found 48-multiplication algorithm for 4x4 complex matrices (beat Strassen's 56-year record), 23% speedup in Gemini training kernel, 32.5% FlashAttention speedup, recovered 0.7% of Google's worldwide compute via data center scheduling. Key advance over FunSearch: evolves entire codebases, not just single functions.
- **AlphaDev** (DeepMind, 2023): RL agent that discovers sorting algorithms at assembly level. Treats algorithm discovery as a single-player game where moves are assembly instructions. Found 70% faster sort for short sequences, now in LLVM C++ standard library. Key idea: search at a lower abstraction level (assembly) than humans would.
- **AlphaProof** (DeepMind, 2024): AlphaZero-inspired RL for formal math proofs in Lean. Pretrained on 12T tokens, then 80M auto-formalized problems via RL. Test-Time RL generates millions of problem variants at inference. Silver medal at 2024 IMO. Key idea: formal verification as reward signal + test-time adaptation.
- **Gemini Deep Think / Aletheia** (DeepMind, 2026): Math research agent with Generator→Verifier→Reviser loop. Solved 18 previously unsolved research problems. Cross-disciplinary: applied continuous math (Kirszbraun Theorem, measure theory) to discrete CS problems (Max-Cut, Steiner Tree). Disproved a decade-old conjecture. Key idea: cross-domain transfer of mathematical tools.
- **AlphaTensor** (DeepMind, 2022): RL as single-player game over tensor decompositions. Beat Strassen's 50-year matrix multiplication record. Key idea: reduce algorithm discovery to game-playing.
- **OpenEvolve** (open-source AlphaEvolve): MAP-Elites + island model + LLM ensemble. Program database with genealogical lineage tracking. Multi-strategy prompt sampling (elite, diversity, exploratory). Cascade evaluation for early filtering. Supports Python, Rust, R, Metal shaders.

### Patterns in Discovery-Class Systems

1. **Formal verification as reward** — AlphaProof, AlphaTensor, AlphaDev all use provably correct evaluation. No ambiguity in fitness.
2. **Lower abstraction levels** — AlphaDev searches assembly, AlphaTensor searches tensor decompositions. Going below human-level abstraction finds things humans miss.
3. **Game framing** — AlphaTensor, AlphaDev, AlphaProof all frame discovery as game-playing, leveraging AlphaZero's proven MCTS+RL framework.
4. **Cross-domain transfer** — Gemini Deep Think's biggest wins came from applying math tools from unrelated fields. This is the analogical reasoning idea in action.
5. **Ensemble models** — AlphaEvolve's Flash+Pro split (breadth vs depth) is a practical implementation of explore/exploit balance.

### Known Universal Limitations (shared by ALL existing systems)

1. They're hill-climbers wearing evolutionary costumes — no radical restructuring
2. No real diversity maintenance (except FunSearch islands, OpenELM MAP-Elites)
3. Memory is flat — no hierarchy, no abstraction levels, no compositionality
4. No metacognition about problem type before solving
5. Evaluation is the bottleneck nobody addresses smartly
6. LLM mode collapse — search gets stuck in the LLM's comfort zone
7. All bespoke — no general-purpose framework exists

## Lateral Ideas Under Investigation

### From Neuroscience

- **Predictive Processing / Free Energy** (Friston): Predict before evaluating. Only spend compute on surprise (prediction errors). Could cut eval cost 5-10x.
- **Complementary Learning Systems**: Fast episodic memory (concrete cases) + slow semantic memory (abstract rules). Periodic consolidation (like sleep).
- **Neuromodulation**: Dynamic explore/exploit ratio driven by surprise signal, not fixed schedules.

### From Information Theory

- **MDL as Fitness**: Score = accuracy - α*(complexity). Shortest correct program generalizes best.
- **Mutual Information for Diversity**: Keep N programs that maximize coverage × structural diversity, not just top-N by score.
- **Information Bottleneck**: Store compressed functional signatures, not full programs. Forces abstraction.

### From Biology / Ecology

- **Niche Construction**: Solutions modify the problem representation. Evolve (decomposition, solution) pairs.
- **Horizontal Gene Transfer**: Gene bank of useful subroutines shared across solutions to different problems.
- **Cambrian Explosion**: First evolve a toolkit/DSL, then rapidly enumerate compositions.

### From Older ML / Optimization

- **MAP-Elites (Quality-Diversity)**: Best solution per behavioral niche, not just one global best. Most underused idea in LLM program synthesis.
- **Bayesian Optimization with Surrogates**: Predict fitness, evaluate where uncertain (UCB strategy).
- **Novelty Search** (Lehman & Stanley): Reward behavioral novelty alongside/instead of fitness. Escapes local optima.

### From Cognitive Science

- **Analogical Reasoning**: Retrieve structurally similar solved problems, not surface-similar ones.
- **Constraint Relaxation**: When stuck, solve simpler version first, then tighten.

## Working Principles

- We are exploring, not building. Ideas first, code later.
- Lateral thinking over incremental improvement — we want ideas from other fields, not just ML.
- Brutal honesty about what works and what doesn't. No hype.
- When we do build: incremental, testable stages. See global CLAUDE.md.
- Save non-obvious discoveries to `DISCOVERIES.md` as we go.

## Key Research Questions (Open)

1. Can MAP-Elites + LLM generation produce meaningfully better results than simple best-of-N?
2. Does dual memory (episodic + semantic with consolidation) actually help or is it overhead?
3. Is predictive evaluation (surrogate model) practical with LLMs as the predictor?
4. Can we evolve problem decompositions as first-class artifacts?
5. What behavioral dimensions should MAP-Elites use for program synthesis?
6. How do we escape LLM mode collapse without astronomical compute?
7. Can we do "abstraction level search" — automatically find the right level to search at (like AlphaDev found assembly)?
8. Can cross-domain tool transfer (Gemini Deep Think's key move) be systematized rather than emergent?
9. Is game-framing (AlphaZero-style MCTS) composable with evolutionary search, or are they fundamentally competing paradigms?
10. Can we build formal verification into the eval loop for general program synthesis, not just math?

## Benchmark: ARC-AGI-2

We use ARC-AGI-2 as our primary benchmark. Local evaluation only (no Kaggle submission for now).

### Dataset
- **Training**: 1000 tasks — use for development (`data/arc-agi-2/data/training/`)
- **Public evaluation**: 120 tasks — use as held-out test (`data/arc-agi-2/data/evaluation/`)
- Average human performance on evaluation: 66%
- Pass@2: you get 2 attempts per test input

### Task Format
JSON files. Each task has `train` (demo pairs) and `test` (held-out pairs). Grids are 2D arrays of ints 0-9 (colors). Min 1x1, max 30x30.

### Running Evaluations
From `benchmarking/` directory:
```bash
# Single task
python main.py --data_dir ../data/arc-agi-2/data/training --config <your-config> --task_id <id> --save_submission_dir ../submissions/<name>

# Batch (all tasks in a directory)
python cli/run_all.py --data_dir ../data/arc-agi-2/data/training --config <your-config> --save_submission_dir ../submissions/<name>

# Score results
python src/arc_agi_benchmarking/scoring/scoring.py --task_dir ../data/arc-agi-2/data/training --submission_dir ../submissions/<name>
```

### Adding a Custom Solver
1. Create `benchmarking/src/arc_agi_benchmarking/adapters/<solver>.py` implementing `ProviderAdapter`
2. Export in `adapters/__init__.py`
3. Add config in `models.yml`
4. Wire up in `main.py`

### Test Set Tiers (for reference)
| Set | Size | Access | We use? |
|-----|------|--------|---------|
| Public training | 1000 | Open (cloned) | Yes — dev set |
| Public evaluation | 120 | Open (cloned) | Yes — test set |
| Semi-private | ~120 | API submission only | Not yet |
| Private (Kaggle) | ~120 | Kaggle sandbox only | No |

## File Structure

```text
data/arc-agi-2/         # ARC-AGI-2 dataset (cloned)
benchmarking/           # ARC-AGI benchmarking harness (cloned)
submissions/            # Our solver outputs
research/               # Notes, paper summaries, idea explorations
  experiments/          # Quick experiments to test hypotheses
DISCOVERIES.md          # Non-obvious findings as we explore
CLAUDE.md               # This file
```
