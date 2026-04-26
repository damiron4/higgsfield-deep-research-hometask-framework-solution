"""Scorer: given a trace dict and a TestCase, produce a CaseResult.

Dispatches to HARD_REGISTRY for deterministic checks and SOFT_REGISTRY for
LLM-judge checks. Re-scoring a cached trace works without calling the agent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.models import AssertionResult, CaseResult, TestCase
from eval.metrics import HARD_REGISTRY, SOFT_REGISTRY, GLOBAL_METRICS


def score_trace(
    trace: dict[str, Any],
    case: TestCase,
    trace_path: Path,
    repeat_index: int = 0,
) -> CaseResult:
    results: list[AssertionResult] = []

    # Hard assertions — deterministic, no LLM calls.
    for assertion in case.expected_behavior.hard:
        fn = HARD_REGISTRY.get(assertion.type)
        if fn is None:
            results.append(
                AssertionResult(
                    assertion_type=assertion.type,
                    passed=False,
                    reason=f"Unknown hard assertion type: {assertion.type!r}",
                )
            )
            continue
        try:
            result = fn(trace, assertion.params)
        except Exception as e:
            result = AssertionResult(
                assertion_type=assertion.type,
                passed=False,
                reason=f"Assertion raised an exception: {e}",
            )
        results.append(result)

    # Global metrics — run on every case regardless of per-case declarations.
    for fn, params in GLOBAL_METRICS:
        try:
            result = fn(trace, params)
        except Exception as e:
            result = AssertionResult(
                assertion_type=getattr(fn, "__name__", "global"),
                passed=False,
                reason=f"Global metric raised an exception: {e}",
            )
        results.append(result)

    # Soft assertions — LLM judge.
    for assertion in case.expected_behavior.soft:
        fn = SOFT_REGISTRY.get(assertion.type)
        if fn is None:
            results.append(
                AssertionResult(
                    assertion_type=assertion.type,
                    passed=False,
                    reason=f"Unknown soft assertion type: {assertion.type!r}",
                )
            )
            continue
        try:
            result = fn(trace, assertion)
        except Exception as e:
            result = AssertionResult(
                assertion_type=assertion.type,
                passed=False,
                reason=f"Judge raised an exception: {e}",
            )
        results.append(result)

    # Count real tool calls (exclude 'finish').
    tool_calls = []
    for msg in trace.get("messages", []):
        if msg.get("role") == "assistant":
            tool_calls.extend(
                c for c in msg.get("tool_calls", []) if c.get("name") != "finish"
            )

    passed = all(r.passed for r in results)
    return CaseResult(
        case_id=case.id,
        run_id=trace.get("run_id", ""),
        repeat_index=repeat_index,
        passed=passed,
        assertion_results=results,
        trace_path=trace_path,
        wall_time_ms=trace.get("wall_time_ms", 0),
        cost_usd=trace.get("cost_usd", 0.0),
        tool_call_count=len(tool_calls),
        stopped_reason=trace.get("stopped_reason", ""),
        error=trace.get("error"),
    )


def rescore_from_file(trace_path: Path, case: TestCase) -> CaseResult:
    """Re-score a cached trace without calling the agent."""
    trace = json.loads(trace_path.read_text())
    return score_trace(trace, case, trace_path)
