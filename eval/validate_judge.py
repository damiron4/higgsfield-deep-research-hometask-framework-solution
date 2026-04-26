"""Rubric validation tool.

Re-runs only the soft (LLM-judge) assertions from a previous run and prints
each verdict in a format suitable for human spot-checking.

Usage:
    python -m eval.validate_judge                   # uses traces/ + cases/
    python -m eval.validate_judge --case-id happy_voyager

Output: structured table + per-verdict detail block.
Write your human agreement/disagreement next to each verdict, then run
with --summary to see the agreement rate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.models import TestCase, SoftAssertion
from eval.metrics.soft import check_soft_assertion


def _load_cases(cases_dir: Path) -> dict[str, TestCase]:
    cases = {}
    for f in sorted(cases_dir.glob("*.yaml")):
        raw = yaml.safe_load(f.read_text())
        tc = TestCase.from_dict(raw)
        cases[tc.id] = tc
    return cases


def _load_traces(traces_dir: Path) -> dict[str, dict]:
    """Return {question: trace_dict} for all traces."""
    by_question = {}
    for tf in traces_dir.glob("*.json"):
        t = json.loads(tf.read_text())
        q = (t.get("question") or "").strip()
        if q:
            by_question[q] = t
    return by_question


def _bar(length: int = 70) -> str:
    return "-" * length


def run_validation(case_filter: str | None = None) -> list[dict]:
    cases = _load_cases(_ROOT / "cases")
    traces = _load_traces(_ROOT / "traces")

    records = []

    for case_id, case in cases.items():
        if case_filter and case_id != case_filter:
            continue
        if not case.expected_behavior.soft:
            continue

        trace = traces.get(case.input.strip())
        if trace is None:
            print(f"[SKIP] {case_id} — no trace found (run eval_run.py first)")
            continue

        for assertion in case.expected_behavior.soft:
            result = check_soft_assertion(trace, assertion)
            records.append({
                "case_id": case_id,
                "assertion_type": assertion.type,
                "verdict": "PASS" if result.passed else "FAIL",
                "rationale": result.rationale or "",
                "question": trace.get("question", ""),
                "answer": (trace.get("final_answer") or "")[:300],
            })

    return records


def print_verdicts(records: list[dict]) -> None:
    print(f"\n{'='*70}")
    print(f"  Judge Validation Report — {len(records)} soft assertions")
    print(f"{'='*70}\n")

    pass_count = sum(1 for r in records if r["verdict"] == "PASS")
    fail_count = len(records) - pass_count
    print(f"  PASS: {pass_count}   FAIL: {fail_count}\n")

    for i, r in enumerate(records, 1):
        verdict_tag = f"[{r['verdict']}]"
        print(f"  {i:>2}. {verdict_tag:<7} {r['case_id']} / {r['assertion_type']}")
        print(f"      Q: {r['question'][:80]!r}")
        print(f"      A: {r['answer'][:120]!r}")
        print(f"      Judge: {r['rationale']}")
        print()

    print(_bar())
    print(
        "  For each verdict above, mark H=agree or D=disagree in your notes.\n"
        "  Agreement rate = H / total.\n"
        "  Known judge failure modes to watch for:\n"
        "    - Leniency on vague hedged answers (judge gives PASS, human says FAIL)\n"
        "    - Over-strictness on format (judge fails on phrasing, human says PASS)\n"
        "    - Injection through agent output (agent answer contains misleading text)\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Spot-check LLM judge verdicts")
    parser.add_argument("--case-id", default=None, help="Filter to one case")
    args = parser.parse_args()

    records = run_validation(case_filter=args.case_id)
    if not records:
        print("No soft assertions found.")
        return
    print_verdicts(records)


if __name__ == "__main__":
    main()
