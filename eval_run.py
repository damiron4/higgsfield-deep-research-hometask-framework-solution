"""Evaluation framework CLI.

Usage examples:

  # Run full suite (all cases in cases/ dir)
  python eval_run.py

  # Run a single case file
  python eval_run.py --cases cases/01_happy_voyager.yaml

  # Run with 3 repeats and concurrency of 3
  python eval_run.py --repeats 3 --concurrency 3

  # Re-score ALL traces from the last run without calling the agent
  python eval_run.py --rescore-all

  # Re-score a single cached trace without calling the agent
  python eval_run.py --rescore traces/abc123.json --case cases/01_happy_voyager.yaml

  # Diff against a specific previous report
  python eval_run.py --prev-report reports/some-run-id.json
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
from pathlib import Path

# Ensure stdout/stderr handle Unicode on Windows consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import yaml
from dotenv import load_dotenv

load_dotenv()

# Ensure project root is on sys.path so agent.py / tools.py are importable.
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from eval.models import TestCase
from eval.reporter import build_report, save_report, print_report
from eval.viewer import generate_html


def _load_cases(path: Path) -> list[TestCase]:
    """Load one YAML file or a directory of YAML files."""
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
    else:
        raise FileNotFoundError(f"Cases path not found: {path}")

    cases = []
    for f in files:
        raw = yaml.safe_load(f.read_text())
        if isinstance(raw, list):
            cases.extend(TestCase.from_dict(c) for c in raw)
        else:
            cases.append(TestCase.from_dict(raw))
    return cases


async def _rescore_one(
    tf: Path,
    by_question: dict,
    semaphore: asyncio.Semaphore,
    loop: asyncio.AbstractEventLoop,
) -> tuple | None:
    """Score a single trace file; returns (CaseResult, case_id) or None if unmatched."""
    from eval.scorer import score_trace

    trace = json.loads(tf.read_text())
    question = (trace.get("question") or "").strip()
    case = by_question.get(question)
    if case is None:
        return None

    async with semaphore:
        result = await loop.run_in_executor(None, score_trace, trace, case, tf)

    status = "PASS" if result.passed else "FAIL"
    print(f"  [{status}] {case.id}")
    if not result.passed:
        for reason in result.failure_reasons():
            print(f"         {reason}")
    return result


def _rescore_all(cases_path: Path, model: str, no_html: bool, concurrency: int) -> None:
    """Re-score traces from the latest run in traces/.

    Reads the latest run's trace_ids from reports/latest.json so that traces
    accumulated from older runs are not mixed in. Falls back to all traces in
    traces/ if no latest report exists (e.g. first run or fixtures workflow).
    """
    from eval.models import CaseResult
    from eval.reporter import _LATEST_POINTER

    cases = _load_cases(cases_path)
    by_question = {c.input.strip(): c for c in cases}

    traces_dir = Path("traces")

    # Determine which trace files to rescore.
    allowed_ids: set[str] | None = None
    if _LATEST_POINTER.exists():
        try:
            latest = json.loads(_LATEST_POINTER.read_text())
            ids = latest.get("trace_ids")
            if ids:
                allowed_ids = set(ids)
        except Exception:
            pass

    if allowed_ids is not None:
        trace_files = [traces_dir / f"{tid}.json" for tid in allowed_ids
                       if (traces_dir / f"{tid}.json").exists()]
    else:
        trace_files = list(traces_dir.glob("*.json"))

    if not trace_files:
        print("No traces found in traces/")
        sys.exit(1)

    print(f"\nRescoring {len(trace_files)} trace(s)  [concurrency={concurrency}]\n")

    async def _run_all() -> list[CaseResult]:
        semaphore = asyncio.Semaphore(concurrency)
        loop = asyncio.get_event_loop()
        tasks = [_rescore_one(tf, by_question, semaphore, loop) for tf in trace_files]
        scored: list[CaseResult] = []
        unmatched_count = 0
        for coro in asyncio.as_completed(tasks):
            item = await coro
            if item is None:
                unmatched_count += 1
            else:
                scored.append(item)
        if unmatched_count:
            print(f"\n  Skipped {unmatched_count} trace(s) with no matching case.")
        return scored

    results = asyncio.run(_run_all())

    if not results:
        print("No traces matched any case.")
        sys.exit(1)

    from eval.reporter import build_report, save_report, print_report
    from eval.viewer import generate_html

    report = build_report(results, model=model, repeats=1)
    report_path = save_report(report)
    print_report(report)
    print(f"  Report saved: {report_path}")
    if not no_html:
        html_path = generate_html(report)
        print(f"  HTML viewer:  {html_path}\n")


def _rescore(trace_path: Path, case_path: Path) -> None:
    """Re-score a single cached trace against a case file."""
    from eval.scorer import rescore_from_file

    cases = _load_cases(case_path)
    if len(cases) != 1:
        print(f"ERROR: --rescore expects exactly one case in --case, got {len(cases)}")
        sys.exit(1)

    case = cases[0]
    result = rescore_from_file(trace_path, case)

    print(f"\nRe-score: {case.id}")
    print(f"  Passed: {result.passed}")
    for r in result.assertion_results:
        icon = "PASS" if r.passed else "FAIL"
        print(f"  {icon} [{r.assertion_type}] {r.reason}")
        if r.rationale and not r.passed:
            print(f"      Judge: {r.rationale}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep Research Lite — Evaluation Framework")
    parser.add_argument(
        "--cases", type=Path, default=Path("cases"),
        help="Path to a YAML case file or directory of YAML cases (default: cases/)"
    )
    parser.add_argument(
        "--repeats", type=int, default=1,
        help="Run each case N times for flakiness detection (default: 1)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=5,
        help="Max concurrent agent runs (default: 5)"
    )
    parser.add_argument(
        "--model", type=str, default=os.getenv("DRL_MODEL", "claude-haiku-4-5"),
        help="Agent model override"
    )
    parser.add_argument(
        "--rescore-all", action="store_true",
        help="Re-score all traces in traces/ against cases (no agent calls)"
    )
    parser.add_argument(
        "--rescore", type=Path, default=None,
        help="Re-score a single cached trace file without calling the agent"
    )
    parser.add_argument(
        "--case", type=Path, default=None,
        help="Case file to use with --rescore"
    )
    parser.add_argument(
        "--prev-report", type=Path, default=None,
        help="Path to a previous run report JSON for diff (overrides latest.json)"
    )
    parser.add_argument(
        "--no-html", action="store_true",
        help="Skip generating the HTML trace viewer"
    )
    args = parser.parse_args()

    # Re-score all mode — no agent calls.
    if args.rescore_all:
        _rescore_all(args.cases, model=args.model, no_html=args.no_html, concurrency=args.concurrency)
        return

    # Re-score single trace mode — no agent calls.
    if args.rescore:
        if not args.case:
            print("ERROR: --rescore requires --case <case_file>")
            sys.exit(1)
        _rescore(args.rescore, args.case)
        return

    # Normal run mode.
    cases = _load_cases(args.cases)
    if not cases:
        print(f"No cases found at: {args.cases}")
        sys.exit(1)

    print(f"\nRunning {len(cases)} cases × {args.repeats} repeat(s)  "
          f"[concurrency={args.concurrency}  model={args.model}]\n")

    # Override the latest pointer if --prev-report was specified.
    if args.prev_report:
        from eval.reporter import _LATEST_POINTER
        _LATEST_POINTER.write_text(args.prev_report.read_text())

    from eval.runner import run_suite

    results = asyncio.run(
        run_suite(
            cases=cases,
            repeats=args.repeats,
            concurrency=args.concurrency,
            model=args.model,
        )
    )

    report = build_report(results, model=args.model, repeats=args.repeats)
    report_path = save_report(report)
    print_report(report)
    print(f"  Report saved: {report_path}")

    if not args.no_html:
        html_path = generate_html(report)
        print(f"  HTML viewer:  {html_path}\n")

    # Exit with non-zero if regressions detected.
    if report.regressions:
        sys.exit(1)


if __name__ == "__main__":
    main()
