"""Reporter: aggregates CaseResults into a RunReport and diffs vs previous run."""

from __future__ import annotations

import json
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.models import CaseResult, CaseSummary, RunReport

_REPORTS_DIR = Path(__file__).parent.parent / "reports"
_REPORTS_DIR.mkdir(exist_ok=True)

_LATEST_POINTER = _REPORTS_DIR / "latest.json"


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (p / 100) * (len(sorted_data) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_data) - 1)
    frac = idx - lo
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac


def build_report(
    results: list[CaseResult],
    model: str,
    repeats: int,
) -> RunReport:
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # Group by case_id.
    by_case: dict[str, list[CaseResult]] = {}
    for r in results:
        by_case.setdefault(r.case_id, []).append(r)

    summaries = []
    for case_id, case_results in by_case.items():
        passes = sum(1 for r in case_results if r.passed)
        summaries.append(
            CaseSummary(
                case_id=case_id,
                total_repeats=len(case_results),
                passes=passes,
                failures=len(case_results) - passes,
            )
        )

    latencies = [r.wall_time_ms for r in results if r.wall_time_ms > 0]
    tool_counts = [r.tool_call_count for r in results]
    total_cost = sum(r.cost_usd for r in results)

    report = RunReport(
        run_id=run_id,
        timestamp=timestamp,
        model=model,
        total_cases=len(by_case),
        total_repeats=repeats,
        summaries=summaries,
        all_results=results,
        total_cost_usd=total_cost,
        p50_latency_ms=_percentile([float(l) for l in latencies], 50),
        p95_latency_ms=_percentile([float(l) for l in latencies], 95),
        mean_tool_calls=statistics.mean(tool_counts) if tool_counts else 0.0,
    )

    # Diff against previous run if one exists.
    if _LATEST_POINTER.exists():
        try:
            prev = json.loads(_LATEST_POINTER.read_text())
            report.previous_run_id = prev.get("run_id")
            prev_rates = {c["case_id"]: c["pass_rate"] for c in prev.get("cases", [])}
            for s in summaries:
                prev_rate = prev_rates.get(s.case_id)
                if prev_rate is None:
                    continue
                if s.pass_rate < prev_rate - 0.01:
                    report.regressions.append(
                        f"{s.case_id}: {prev_rate:.0%} -> {s.pass_rate:.0%}"
                    )
                elif s.pass_rate > prev_rate + 0.01:
                    report.improvements.append(
                        f"{s.case_id}: {prev_rate:.0%} -> {s.pass_rate:.0%}"
                    )
        except Exception:
            pass

    return report


def save_report(report: RunReport) -> Path:
    path = _REPORTS_DIR / f"{report.run_id}.json"
    report.save(path)
    # Update the latest pointer for future diffs.
    _LATEST_POINTER.write_text(json.dumps(report.to_dict(), indent=2))
    return path


def print_report(report: RunReport) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  Run: {report.run_id[:8]}...  |  {report.timestamp[:19]}Z")
    print(f"  Model: {report.model}")
    print("=" * width)

    # Regressions banner.
    if report.regressions:
        print("\n  !! REGRESSIONS DETECTED !!")
        for r in report.regressions:
            print(f"     {r}")

    if report.improvements:
        print("\n  ** Improvements **")
        for i in report.improvements:
            print(f"     {i}")

    print(f"\n  Pass rate : {report.pass_rate:.1%}  ({sum(s.passes for s in report.summaries)}/{sum(s.total_repeats for s in report.summaries)})")
    print(f"  Cost      : ${report.total_cost_usd:.4f}")
    print(f"  Latency   : p50={report.p50_latency_ms:.0f}ms  p95={report.p95_latency_ms:.0f}ms")
    print(f"  Tool calls: mean={report.mean_tool_calls:.1f}/case")

    print(f"\n  {'Case':<35} {'Result':<16} {'Failures'}")
    print("  " + "-" * (width - 2))
    for s in report.summaries:
        label = s.label()
        failures = [
            r
            for res in report.all_results
            if res.case_id == s.case_id
            for r in res.failure_reasons()
        ]
        first_failure = failures[0] if failures else ""
        # Truncate long failure messages for console.
        if len(first_failure) > 40:
            first_failure = first_failure[:37] + "..."
        print(f"  {s.case_id:<35} {label:<16} {first_failure}")

    print("=" * width + "\n")
