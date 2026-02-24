"""Evaluation script using Anthropic as the judge. Drop-in replacement for the original eval.py."""

import json
import os
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from tqdm import tqdm

from . import llm

JUDGE_MODEL = "claude-sonnet-4-5-20250929"


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


def build_rubrics_text(rubrics):
    lines = []
    for i, rubric in enumerate(rubrics, 1):
        criteria = rubric.get("rubric_criteria", "").strip() if isinstance(rubric, dict) else str(rubric).strip()
        if criteria:
            lines.append(f"{i}. {criteria}")
    return "\n".join(lines) if lines else "No specific rubrics provided."


GRADING_PROMPT = """Starting now, you are a rigorous instruction-following grading teacher. Your task is to accurately grade and score student answers based on the 【Rubrics】.

Grading Criteria
This is a strict, all-or-nothing grading system. The final score is binary.
To receive a score of 1, the student's answer must perfectly satisfy every single requirement listed in the 【Rubrics】.
If even one requirement is not fully met, the final score will be 0.

Grading Process
Please strictly follow the steps below for analysis—no steps may be skipped:

Step 1: Analyze the Standard Answer
List all explicit requirements in the 【Rubrics】 item by item (including format, content, quantity, order, etc.).
Identify implicit requirements in the 【Rubrics】 (e.g., language style, logical structure).
Define specific evaluation criteria for each requirement (e.g., "must include X," "must not exceed Y").

Step 2: Check Each Requirement Against the Student's Answer
For every requirement in the 【Rubrics】, verify one by one whether the student's answer fully satisfies it.

Step 3: Self-Reflection
Before giving the final score, you must conduct the following checks:
  Completeness Check: Whether all requirements in the standard answer have been reviewed with no omissions.
  Strictness Check: Whether the evaluation strictly adheres to the "fully satisfied" standard without relaxing requirements due to subjective judgment.
  Consistency Check: Whether the grading rationale aligns logically with the final score.
  Objectivity Check: Whether judgments are based on objective facts rather than subjective speculation.

Output Format Requirements
Please strictly output ONLY the following JSON format (do not output any other content):
{{
  "Grading Rationale": "Your detailed grading rationale",
  "List of Requirement Satisfaction Status": ["yes", "no", ...],
  "Overall Score": 0 or 1
}}

Content to Be Graded
【Rubrics】:
{rubrics_text}

【Student Response】:
{model_output}"""


def grade_single(client, rubrics_text, model_output, model=None):
    """Grade a single response using Anthropic as judge. Returns raw grading dict."""
    model = model or JUDGE_MODEL
    prompt = GRADING_PROMPT.format(rubrics_text=rubrics_text, model_output=model_output)
    messages = [{"role": "user", "content": prompt}]

    response = llm.chat(client=client, system="You are a strict grading judge.", messages=messages, model=model)
    result_text = llm.extract_text(response).strip()

    # Strip code block wrappers
    if result_text.startswith("```json"):
        result_text = result_text[7:]
    if result_text.startswith("```"):
        result_text = result_text[3:]
    if result_text.endswith("```"):
        result_text = result_text[:-3]
    result_text = result_text.strip()

    return json.loads(result_text)


def grade_task(client, answer, rubrics, model=None):
    """
    Grade a task's answer against its rubrics.

    Returns:
        dict with keys: score, grading_rationale, requirement_status
    """
    if not answer or not answer.strip():
        return {"score": 0, "grading_rationale": "Empty output", "requirement_status": [],
                "rubrics_passed": 0, "rubrics_total": 0}

    rubrics_text = build_rubrics_text(rubrics)
    try:
        grading = grade_single(client, rubrics_text, answer, model=model)
        status = grading.get("List of Requirement Satisfaction Status", [])
        return {
            "score": grading.get("Overall Score", 0),
            "grading_rationale": grading.get("Grading Rationale", ""),
            "requirement_status": status,
            "rubrics_passed": sum(1 for s in status if s == "yes"),
            "rubrics_total": len(status),
        }
    except Exception as e:
        return {"score": 0, "grading_rationale": f"Grading error: {e}", "requirement_status": [],
                "rubrics_passed": 0, "rubrics_total": 0}


def get_task_id(item):
    metadata = item.get("metadata", {})
    return metadata.get("task_id", item.get("idx", -1))


def calculate_statistics(output_path):
    if not os.path.exists(output_path):
        return

    data = load_jsonl(output_path)
    total = len(data)
    score_1 = sum(1 for item in data if item.get("score") == 1)
    score_0 = sum(1 for item in data if item.get("score") == 0)

    # Rubric-level stats
    total_rubrics = 0
    passed_rubrics = 0
    for item in data:
        statuses = item.get("requirement_status", [])
        total_rubrics += len(statuses)
        passed_rubrics += sum(1 for s in statuses if s == "yes")

    log(f"\nFinal Statistics:")
    log(f"  Tasks: {score_1}/{total} passed (solving rate: {score_1 / total:.4f})" if total else "  No tasks")
    log(f"  Rubrics: {passed_rubrics}/{total_rubrics} passed ({passed_rubrics / total_rubrics:.4f})" if total_rubrics else "  No rubrics")

    # Per-task breakdown
    log(f"\nPer-task breakdown:")
    for item in data:
        tid = get_task_id(item)
        sub = item.get("metadata", {}).get("sub_category", "?")
        score = item.get("score", "?")
        statuses = item.get("requirement_status", [])
        passed = sum(1 for s in statuses if s == "yes")
        log(f"  {str(tid)[:16]}... [{sub}] score={score} rubrics={passed}/{len(statuses)}")

    # Category breakdown
    category_stats = {}
    for item in data:
        cat = item.get("metadata", {}).get("context_category", "Unknown")
        statuses = item.get("requirement_status", [])
        stats = category_stats.setdefault(cat, {"total": 0, "score_1": 0, "rubrics_passed": 0, "rubrics_total": 0})
        stats["total"] += 1
        if item.get("score") == 1:
            stats["score_1"] += 1
        stats["rubrics_passed"] += sum(1 for s in statuses if s == "yes")
        stats["rubrics_total"] += len(statuses)

    if category_stats:
        log(f"\nBy category:")
        for cat in sorted(category_stats):
            s = category_stats[cat]
            task_rate = s["score_1"] / s["total"] if s["total"] else 0
            rubric_rate = s["rubrics_passed"] / s["rubrics_total"] if s["rubrics_total"] else 0
            log(f"  {cat}: tasks={s['score_1']}/{s['total']} ({task_rate:.4f}) rubrics={s['rubrics_passed']}/{s['rubrics_total']} ({rubric_rate:.4f})")


def main():
    parser = argparse.ArgumentParser(description="CL-bench Eval (Anthropic judge)")
    parser.add_argument("--input", type=str, required=True, help="Input graded JSONL")
    parser.add_argument("--output", type=str, default=None, help="Output JSONL")
    parser.add_argument("--model", type=str, default=None, help="Judge model")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers")
    args = parser.parse_args()

    if args.output is None:
        base = os.path.splitext(os.path.basename(args.input))[0]
        args.output = f"outputs/{base}_graded.jsonl"

    log(f"Input: {args.input}")
    log(f"Output: {args.output}")
    log(f"Workers: {args.workers}")

    client = llm.get_client()
    data = load_jsonl(args.input)
    log(f"Loaded {len(data)} samples")

    # Resume support
    completed = set()
    if os.path.exists(args.output):
        for item in load_jsonl(args.output):
            tid = get_task_id(item)
            if tid:
                completed.add(tid)
        log(f"Found {len(completed)} already graded, resuming")

    pending = [d for d in data if get_task_id(d) not in completed]
    if not pending:
        log("All done.")
        calculate_statistics(args.output)
        return

    log(f"Grading {len(pending)} tasks...")

    def _grade_item(item):
        task_id = get_task_id(item)
        model_output = item.get("model_output", "")

        if not model_output or not model_output.strip():
            result = {**item, "score": 0, "grading_rationale": "Empty output"}
            append_jsonl(result, args.output)
            return

        rubrics_text = build_rubrics_text(item.get("rubrics", []))

        try:
            grading = grade_single(client, rubrics_text, model_output, model=args.model)
            result = {
                **item,
                "score": grading.get("Overall Score", 0),
                "grading_rationale": grading.get("Grading Rationale", ""),
                "requirement_status": grading.get("List of Requirement Satisfaction Status", []),
            }
        except Exception as e:
            log(f"  Failed grading {task_id[:12]}...: {e}")
            result = {**item, "score": 0, "grading_rationale": f"Grading error: {e}"}

        append_jsonl(result, args.output)

    if args.workers == 1:
        for item in tqdm(pending, desc="Grading"):
            _grade_item(item)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(_grade_item, item) for item in pending]
            for future in tqdm(as_completed(futures), total=len(futures), desc="Grading"):
                try:
                    future.result()
                except Exception as e:
                    log(f"  Worker error: {e}")

    calculate_statistics(args.output)


if __name__ == "__main__":
    main()
