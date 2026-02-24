"""Runner that iterates CL-bench tasks and runs the agent."""

import json
import os
import argparse
import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from . import llm
from .agent import run_task, EXPERIMENTS
from .eval import grade_task, calculate_statistics, JUDGE_MODEL
from .prompts import (
    AGENT_INSTRUCTIONS,
    VERIFY_INSTRUCTION,
    VERIFY_MESSAGE,
    VERIFIER_SYSTEM_PROMPT,
    REVISION_MESSAGE,
)


def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def load_jsonl(path):
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


_write_lock = threading.Lock()


def append_jsonl(item, path):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def save_config(args, task_count, pending_count):
    """Save run config alongside output for reproducibility."""
    config_path = os.path.splitext(args.output)[0] + "_config.json"

    # Collect prompts relevant to this experiment
    prompts = {"agent_instructions": AGENT_INSTRUCTIONS}
    if args.experiment == 2:
        prompts["verify_instruction"] = VERIFY_INSTRUCTION
    elif args.experiment == 3:
        prompts["verify_message"] = VERIFY_MESSAGE
    elif args.experiment == 4:
        prompts["verifier_system_prompt"] = VERIFIER_SYSTEM_PROMPT
        prompts["revision_message"] = REVISION_MESSAGE

    config = {
        "timestamp": datetime.now().isoformat(),
        "experiment": args.experiment,
        "input": args.input,
        "output": args.output,
        "agent_model": args.model or llm.DEFAULT_MODEL,
        "judge_model": args.judge_model or JUDGE_MODEL,
        "max_tool_calls": args.max_tool_calls,
        "sample": args.sample,
        "seed": args.seed if args.sample else None,
        "category_filter": args.category,
        "subcategory_filter": args.subcategory,
        "workers": args.workers,
        "total_tasks_in_dataset": task_count,
        "tasks_to_run": pending_count,
        "prompts": prompts,
    }

    os.makedirs(os.path.dirname(config_path) if os.path.dirname(config_path) else ".", exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    log(f"Config saved: {config_path}")


def load_completed(path):
    """Load already-completed task IDs for resume support."""
    if not os.path.exists(path):
        return set()
    completed = set()
    for item in load_jsonl(path):
        tid = item.get("idx") or item.get("metadata", {}).get("task_id")
        if tid:
            completed.add(tid)
    return completed


def process_task(client, task, output_path, experiment=1, model=None,
                 judge_model=None, max_tool_calls=None, verbose=False):
    """Run a single task: generate answer then grade it."""
    task_id = task["metadata"]["task_id"]
    category = task["metadata"]["context_category"]
    subcategory = task["metadata"]["sub_category"]
    msg_count = len(task["messages"])

    start_time = time.time()

    # Generate
    answer, tool_log, _ = run_task(
        client=client,
        messages=task["messages"],
        experiment=experiment,
        model=model,
        max_tool_calls=max_tool_calls,
        verbose=verbose,
    )

    # Grade
    grading = grade_task(client, answer, task.get("rubrics", []), model=judge_model)

    elapsed = time.time() - start_time

    result = {
        "idx": task_id,
        "experiment": experiment,
        "messages": task["messages"],
        "model_output": answer,
        "rubrics": task.get("rubrics", []),
        "metadata": task.get("metadata", {}),
        "tool_log": tool_log,
        "tool_call_count": len(tool_log),
        **grading,
        "elapsed_seconds": round(elapsed, 1),
    }
    append_jsonl(result, output_path)

    log(f"  Task {task_id[:12]}... [{category}/{subcategory}] ({msg_count} msgs, {len(tool_log)} tools) "
        f"score={grading['score']} rubrics={grading['rubrics_passed']}/{grading['rubrics_total']} "
        f"in {elapsed:.1f}s")

    return 1


def main():
    parser = argparse.ArgumentParser(description="CL-bench Agent Runner")
    parser.add_argument("--input", type=str, default="CL-bench.jsonl", help="Input JSONL path")
    parser.add_argument("--output", type=str, default="outputs/agent.jsonl", help="Output JSONL path")
    parser.add_argument("--experiment", type=int, default=1, choices=list(EXPERIMENTS.keys()),
                        help="Experiment number (1-4)")
    parser.add_argument("--model", type=str, default=None, help="Anthropic model name")
    parser.add_argument("--max-tool-calls", type=int, default=None, help="Max tool calls per task (None=unlimited)")
    parser.add_argument("--max-tasks", type=int, default=None, help="Max tasks to process (for testing)")
    parser.add_argument("--sample", type=int, default=None, help="Sample N tasks (deterministic with --seed)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling (default: 42)")
    parser.add_argument("--category", type=str, default=None, help="Filter by category")
    parser.add_argument("--subcategory", type=str, default=None, help="Filter by subcategory")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers")
    parser.add_argument("--judge-model", type=str, default=None, help="Model for grading")
    parser.add_argument("--verbose", action="store_true", help="Print tool calls and reasoning")
    args = parser.parse_args()

    log(f"Experiment: {args.experiment}")
    log(f"Input: {args.input}")
    log(f"Output: {args.output}")
    log(f"Model: {args.model or llm.DEFAULT_MODEL}")
    log(f"Max tool calls: {args.max_tool_calls or 'unlimited'}")

    client = llm.get_client()

    # Load data
    data = load_jsonl(args.input)
    log(f"Loaded {len(data)} tasks")

    # Filter by category/subcategory
    if args.category:
        data = [d for d in data if d["metadata"]["context_category"] == args.category]
        log(f"Filtered to {len(data)} tasks in category '{args.category}'")
    if args.subcategory:
        data = [d for d in data if d["metadata"]["sub_category"] == args.subcategory]
        log(f"Filtered to {len(data)} tasks in subcategory '{args.subcategory}'")

    # Load completed for resume support
    completed = load_completed(args.output)
    if completed:
        log(f"Found {len(completed)} completed tasks, resuming")

    # Filter out completed
    pending = [t for t in data if t["metadata"]["task_id"] not in completed]

    # Sample if requested
    if args.sample and args.sample < len(pending):
        random.seed(args.seed)
        sorted_pending = sorted(pending, key=lambda t: t["metadata"]["task_id"])
        pending = random.sample(sorted_pending, args.sample)
        log(f"Sampled {args.sample} tasks with seed={args.seed}")

    log(f"Tasks to process: {len(pending)}")
    log(f"Workers: {args.workers}")

    save_config(args, task_count=len(data), pending_count=len(pending))

    if args.workers == 1:
        total_processed = 0
        for i, task in enumerate(pending, 1):
            log(f"Task {i}/{len(pending)}")
            try:
                total_processed += process_task(
                    client=client, task=task, output_path=args.output,
                    experiment=args.experiment, model=args.model,
                    judge_model=args.judge_model,
                    max_tool_calls=args.max_tool_calls, verbose=args.verbose,
                )
            except Exception as e:
                tid = task["metadata"]["task_id"]
                log(f"  ERROR on task {tid[:12]}...: {e}")
                continue

            if args.max_tasks and total_processed >= args.max_tasks:
                log(f"Reached max tasks limit ({args.max_tasks})")
                break
    else:
        total_processed = 0

        def _process(task):
            try:
                return process_task(
                    client=client, task=task, output_path=args.output,
                    experiment=args.experiment, model=args.model,
                    judge_model=args.judge_model,
                    max_tool_calls=args.max_tool_calls, verbose=args.verbose,
                )
            except Exception as e:
                tid = task["metadata"]["task_id"]
                log(f"  ERROR on task {tid[:12]}...: {e}")
                return 0

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(_process, task): task for task in pending}
            for future in as_completed(futures):
                try:
                    total_processed += future.result()
                except Exception as e:
                    log(f"  Worker error: {e}")
                log(f"  Progress: {total_processed}/{len(pending)} tasks done")

    log(f"Done. Processed {total_processed} tasks. Output: {args.output}")
    calculate_statistics(args.output)


if __name__ == "__main__":
    main()
