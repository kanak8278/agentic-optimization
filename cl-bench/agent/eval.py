"""Evaluation script — matches official CL-bench eval.py exactly.

Uses the same grading prompt, same JSON parsing, same retry logic.
Judge model configurable (default: gpt-5 via Azure, matching official gpt-5.1).
"""

import json
import os
import argparse
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from tqdm import tqdm

from . import llm

# Default judge — official CL-bench uses gpt-5.1 (OpenAI Direct).
# gpt-5.1 only works from AI Workspace (SageMaker), not local.
# Fallback: gpt-5 via Azure is the closest available locally.
JUDGE_MODEL = "azure/gpt-5"
MAX_RETRIES = 3
RETRY_DELAY = 3


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
    """Build rubrics checklist — matches official eval.py exactly."""
    if not rubrics:
        return "No specific rubrics provided."

    lines = []
    for i, rubric in enumerate(rubrics, 1):
        if isinstance(rubric, dict):
            criteria = rubric.get("rubric_criteria", "").strip()
        else:
            criteria = str(rubric).strip()
        if criteria:
            lines.append(f"{i}. {criteria}")

    return "\n".join(lines) if lines else "No specific rubrics provided."


def _build_grading_prompt(rubrics_text, model_output):
    """Build grading prompt — exact copy of official eval.py grading_prompt."""
    return (
        "Starting now, you are a rigorous instruction-following grading teacher. "
        "Your task is to accurately grade and score student answers based on the 【Rubrics】.\n\n"
        "Grading Criteria\n"
        "This is a strict, all-or-nothing grading system. The final score is binary.\n"
        "To receive a score of 1, the student's answer must perfectly satisfy every single "
        "requirement listed in the 【Rubrics】.\n"
        "If even one requirement is not fully met, the final score will be 0.\n"
        "Grading Process\n"
        "Please strictly follow the steps below for analysis—no steps may be skipped:\n"
        "Step 1: Analyze the Standard Answer\n"
        "List all explicit requirements in the 【Rubrics】 item by item "
        "(including format, content, quantity, order, etc.).\n"
        "Identify implicit requirements in the 【Rubrics】 (e.g., language style, logical structure).\n"
        "Define specific evaluation criteria for each requirement "
        "(e.g., \"must include X,\" \"must not exceed Y\").\n"
        "Step 2: Check Each Requirement Against the Student's Answer\n"
        "For every requirement in the 【Rubrics】, verify one by one whether the student's answer "
        "fully satisfies it.\n"
        "Step 3: Self-Reflection\n"
        "Before giving the final score, you must conduct the following checks:\n"
        "  Completeness Check: Whether all requirements in the standard answer have been reviewed "
        "with no omissions.\n"
        "  Strictness Check: Whether the evaluation strictly adheres to the \"fully satisfied\" "
        "standard without relaxing requirements due to subjective judgment.\n"
        "  Consistency Check: Whether the grading rationale aligns logically with the final score.\n"
        "  Objectivity Check: Whether judgments are based on objective facts rather than subjective "
        "speculation.\n"
        "Output Format Requirements\n"
        "【Grading Rationale】: xxx\n"
        "【List of Requirement Satisfaction Status】: [x₁, x₂, …, xᵢ, …, xₙ] "
        "(where n is the total number of requirements in the 【Rubrics】, and xᵢ indicates "
        "whether the student's answer meets the i-th requirement, with values \"yes\"/\"no\")\n"
        "【Overall Score】: x points (x is an integer, either 0 or 1.)\n\n"
        "Content to Be Graded\n"
        f"【Rubrics】:\n{rubrics_text}\n"
        f"【Student Response】:\n{model_output}\n"
        "\nPlease strictly output ONLY the following JSON format (do not output any other content):\n"
        "{\n"
        '  "Grading Rationale": "Your detailed grading rationale",\n'
        '  "List of Requirement Satisfaction Status": ["yes", "no", ...],\n'
        '  "Overall Score": 0 or 1\n'
        "}\n"
    )


def _call_judge(rubrics_text, model_output, model=None):
    """Call judge LLM. Returns raw text or None on failure.

    Matches official: no system prompt, just the user message.
    """
    model = model or JUDGE_MODEL
    prompt = _build_grading_prompt(rubrics_text, model_output)
    # Official eval uses no system prompt — just messages=[{role: user, content: prompt}]
    # Our llm.chat() prepends system as a message, so pass empty string
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(MAX_RETRIES):
        try:
            response = llm.chat(system="", messages=messages, model=model)
            result_text = llm.extract_text(response).strip()

            # Remove code block wrappers (matches official)
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

            return result_text
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                return None


def grade_task(answer, rubrics, model=None):
    """Grade a task's answer against rubrics with JSON parse retry.

    Matches official eval.py process_single_item logic:
    - If JSON parse fails, re-call the LLM (up to MAX_RETRIES times)
    - Validates "Overall Score" field exists
    """
    if not answer or not answer.strip():
        return {"score": 0, "grading_rationale": "Empty output",
                "requirement_status": [], "rubrics_passed": 0, "rubrics_total": 0}

    rubrics_text = build_rubrics_text(rubrics)

    for parse_attempt in range(MAX_RETRIES):
        result_text = _call_judge(rubrics_text, answer, model=model)

        if not result_text:
            if parse_attempt < MAX_RETRIES - 1:
                time.sleep(2)
                continue
            return {"score": 0, "grading_rationale": "API call failed",
                    "requirement_status": [], "rubrics_passed": 0, "rubrics_total": 0}

        try:
            result_json = json.loads(result_text)

            if "Overall Score" not in result_json:
                raise ValueError("Missing 'Overall Score' field")

            status = result_json.get("List of Requirement Satisfaction Status", [])
            return {
                "score": result_json.get("Overall Score", 0),
                "grading_rationale": result_json.get("Grading Rationale", ""),
                "requirement_status": status,
                "rubrics_passed": sum(1 for s in status if s == "yes"),
                "rubrics_total": len(status),
            }
        except (json.JSONDecodeError, ValueError):
            if parse_attempt < MAX_RETRIES - 1:
                time.sleep(2)
                continue
            return {
                "score": 0,
                "grading_rationale": f"JSON parse failed: {result_text[:500]}",
                "requirement_status": [],
                "rubrics_passed": 0,
                "rubrics_total": 0,
            }


def get_task_id(item):
    metadata = item.get("metadata", {})
    return metadata.get("task_id", item.get("idx", -1))


def calculate_statistics(output_path):
    if not os.path.exists(output_path):
        return

    data = load_jsonl(output_path)
    total = len(data)
    score_1 = sum(1 for item in data if item.get("score") == 1)

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
    parser = argparse.ArgumentParser(description="CL-bench Eval (matches official eval.py)")
    parser.add_argument("--input", type=str, required=True, help="Input JSONL with model_output")
    parser.add_argument("--output", type=str, default=None, help="Output JSONL")
    parser.add_argument("--model", type=str, default=None,
                        help=f"Judge model (default: {JUDGE_MODEL})")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers")
    args = parser.parse_args()

    if args.output is None:
        base = os.path.splitext(os.path.basename(args.input))[0]
        args.output = f"outputs/{base}_graded.jsonl"

    judge_model = args.model or JUDGE_MODEL

    log(f"Input: {args.input}")
    log(f"Output: {args.output}")
    log(f"Judge: {judge_model}")
    log(f"Workers: {args.workers}")

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
        model_output = item.get("model_output", "")

        if not model_output or not model_output.strip():
            result = {**item, "score": 0, "grading_rationale": "Empty output",
                      "requirement_status": [], "rubrics_passed": 0, "rubrics_total": 0}
            append_jsonl(result, args.output)
            return

        grading = grade_task(model_output, item.get("rubrics", []), model=judge_model)
        result = {**item, **grading}
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
