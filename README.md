# Agentic Optimization for CL-bench

An agentic system that improves LLM context learning on [CL-bench](https://github.com/Tencent-Hunyuan/CL-bench) by giving the model search and read tools over reference documents, rather than forcing it to process everything in a single pass.

**Result**: 28.4% solving rate on 1,899 tasks (Claude Opus 4.5 + agent), beating the CL-bench leaderboard leader GPT-5.1 High at 23.7%.

## How It Works

CL-bench tasks give the LLM a long context document (domain knowledge, rule systems, procedures, or empirical data) and ask questions that require learning from that context. Standard LLMs score ~17-24%.

Our agent gets two tools:
- **`search_context`** — regex search over the document with surrounding context
- **`read_lines`** — read a specific line range from the document

The agent loop: LLM decides what to search/read, gets results, reasons, searches more, and eventually produces a final answer. This lets it focus attention on relevant sections instead of trying to absorb everything at once.

## Setup

### 1. Clone and set up environment

```bash
git clone <this-repo>
cd agentic-optimization

python -m venv .venv
source .venv/bin/activate
pip install anthropic python-dotenv tqdm openai
```

### 2. Set your API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your-key-here
```

### 3. Download the CL-bench dataset

Download `CL-bench.jsonl` from [Hugging Face](https://huggingface.co/datasets/tencent/CL-bench) and place it at:

```
cl-bench/CL-bench.jsonl
```

Or use the Hugging Face CLI:

```bash
pip install huggingface_hub
huggingface-cli download tencent/CL-bench --repo-type dataset --local-dir cl-bench/
```

## Running the Agent

All commands run from the project root.

### Quick test (observation set, 8 tasks)

```bash
python -m cl-bench.agent.run \
  --input cl-bench/data/observation_8.jsonl \
  --output outputs/test.jsonl \
  --experiment 1
```

### Run on evaluation set (500 tasks)

```bash
python -m cl-bench.agent.run \
  --input cl-bench/data/eval_500.jsonl \
  --output outputs/exp1_eval.jsonl \
  --experiment 1 \
  --workers 40
```

### Run on full dataset (1,899 tasks)

```bash
python -m cl-bench.agent.run \
  --input cl-bench/CL-bench.jsonl \
  --output outputs/exp1_full.jsonl \
  --experiment 1 \
  --workers 40
```

### Key arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--input` | `CL-bench.jsonl` | Input JSONL path |
| `--output` | `outputs/agent.jsonl` | Output JSONL path |
| `--experiment` | `1` | Experiment number (1-4) |
| `--model` | `claude-opus-4-5-20251101` | Anthropic model |
| `--judge-model` | `claude-sonnet-4-5-20250929` | Model for grading |
| `--max-tool-calls` | unlimited | Cap tool calls per task |
| `--workers` | `1` | Parallel workers |
| `--sample` | all | Sample N tasks randomly |
| `--seed` | `42` | Random seed for sampling |
| `--category` | all | Filter by context category |
| `--verbose` | off | Print tool calls and reasoning |

### Resume support

If a run is interrupted, re-run the same command. Completed tasks are detected from the output file and skipped automatically.

## Experiments

We ran 4 experiments to test different verification strategies:

| Exp | Description | Solving Rate (500 tasks) |
|-----|-------------|-------------------------|
| 1 | Basic agent (search + read) | **29.2%** |
| 2 | + self-verification (prompt) | 28.0% |
| 3 | + self-verification (code-enforced) | 26.3% |
| 4 | + separate verifier agent | 23.8% |

**Key finding**: Verification hurts. The basic agent without any verification performs best. More verification = worse results, regardless of mechanism. Details in `cl-bench/EXPERIMENT_PLAN.md`.

## Running the Original CL-bench Scripts

The repo also includes the original CL-bench inference and eval scripts (OpenAI API):

```bash
# Inference with any OpenAI-compatible API
python cl-bench/infer.py --model gpt-5.1 --input cl-bench/CL-bench.jsonl --output outputs/gpt5-1.jsonl

# Evaluation
python cl-bench/eval.py --input outputs/gpt5-1.jsonl --judge-model gpt-5.1
```

These require `OPENAI_API_KEY` set in your environment.

## Project Structure

```
cl-bench/
  agent/              # The agentic solver
    agent.py          # Core agent loop and experiment runners
    tools.py          # search_context and read_lines tools
    prompts.py        # All prompts (shared base + per-experiment)
    llm.py            # Anthropic API wrapper with prompt caching
    eval.py           # Grading using Anthropic as judge
    run.py            # CLI runner (entry point)
  infer.py            # Original CL-bench inference (OpenAI API)
  eval.py             # Original CL-bench evaluation (OpenAI API)
  data/
    observation_8.jsonl  # 8-task dev set for debugging
  EXPERIMENT_PLAN.md  # Detailed experiment design and results
CLAUDE.md             # Project context and research notes
README.md             # This file
.env                  # API keys (not tracked)
```
