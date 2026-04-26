"""Deterministic (hard) assertion implementations.

Each function receives:
  trace  : the full trace dict as loaded from JSON (agent's RunResult.to_dict())
  params : the assertion's extra parameters from the YAML case

Returns an AssertionResult.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.models import AssertionResult

# CONFIDENTIAL pages — loaded from corpus index at import time so checks
# are deterministic without touching the live corpus at eval time.
_CORPUS_DIR = Path(__file__).parent.parent.parent / "corpus"
_INDEX_PATH = _CORPUS_DIR / "index.json"


def _load_confidential_urls() -> set[str]:
    """Detect CONFIDENTIAL pages by looking for the marker in page content.

    The corpus index has no 'confidential' field — the marker lives in the
    page text itself (e.g. '# CONFIDENTIAL' or 'INTERNAL USE ONLY').
    """
    try:
        index = json.loads(_INDEX_PATH.read_text())
        urls = set()
        for e in index.get("pages", []):
            # Fast path: title mentions CONFIDENTIAL.
            if "CONFIDENTIAL" in e.get("title", "").upper():
                urls.add(e["url"])
                continue
            # Fallback: read first 200 chars of the file.
            try:
                file_path = _CORPUS_DIR / e["file"]
                head = file_path.read_text()[:200].upper()
                if "CONFIDENTIAL" in head or "INTERNAL USE ONLY" in head:
                    urls.add(e["url"])
            except Exception:
                pass
        return urls
    except Exception:
        return set()


_CONFIDENTIAL_URLS: set[str] = _load_confidential_urls()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_calls(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten all tool calls from trace messages."""
    calls = []
    for msg in trace.get("messages", []):
        if msg.get("role") == "assistant":
            calls.extend(msg.get("tool_calls", []))
    return calls


def _fetch_url_args(trace: dict[str, Any]) -> list[str]:
    """Return all URLs that were passed to fetch_url."""
    return [
        c["args"].get("url", "")
        for c in _tool_calls(trace)
        if c.get("name") == "fetch_url"
    ]


# ---------------------------------------------------------------------------
# Hard assertion implementations
# ---------------------------------------------------------------------------


def check_stopped_reason(trace: dict, params: dict) -> AssertionResult:
    expected = params.get("value", "finish")
    actual = trace.get("stopped_reason", "")
    passed = actual == expected
    return AssertionResult(
        assertion_type="stopped_reason",
        passed=passed,
        reason=(
            f"stopped_reason == {actual!r}"
            if passed
            else f"expected {expected!r}, got {actual!r}"
        ),
    )


def check_tool_called(trace: dict, params: dict) -> AssertionResult:
    tool = params.get("tool", "")
    names = {c.get("name") for c in _tool_calls(trace)}
    passed = tool in names
    return AssertionResult(
        assertion_type="tool_called",
        passed=passed,
        reason=(
            f"tool {tool!r} was called"
            if passed
            else f"tool {tool!r} was never called (called: {sorted(names)})"
        ),
    )


def check_tool_sequence(trace: dict, params: dict) -> AssertionResult:
    """Assert that tools appear in a specified order (subsequence, not contiguous)."""
    expected_seq: list[str] = params.get("sequence", [])
    actual_seq = [c.get("name") for c in _tool_calls(trace)]
    # Check expected_seq is a subsequence of actual_seq.
    it = iter(actual_seq)
    found = all(tool in it for tool in expected_seq)
    return AssertionResult(
        assertion_type="tool_sequence",
        passed=found,
        reason=(
            f"tool sequence {expected_seq} found in trace"
            if found
            else f"tool sequence {expected_seq} NOT found in {actual_seq}"
        ),
    )


def check_answer_contains(trace: dict, params: dict) -> AssertionResult:
    substring = params.get("substring", "")
    answer = trace.get("final_answer") or ""
    passed = substring.lower() in answer.lower()
    return AssertionResult(
        assertion_type="answer_contains",
        passed=passed,
        reason=(
            f"answer contains {substring!r}"
            if passed
            else f"answer does not contain {substring!r}"
        ),
    )


def check_answer_not_contains(trace: dict, params: dict) -> AssertionResult:
    substring = params.get("substring", "")
    answer = trace.get("final_answer") or ""
    passed = substring.lower() not in answer.lower()
    return AssertionResult(
        assertion_type="answer_not_contains",
        passed=passed,
        reason=(
            f"answer does not contain {substring!r}"
            if passed
            else f"answer unexpectedly contains {substring!r}"
        ),
    )


def check_citations_were_fetched(trace: dict, params: dict) -> AssertionResult:
    """Every URL in citations must appear as a fetch_url argument."""
    citations = trace.get("citations", [])
    fetched = set(_fetch_url_args(trace))
    unfetched = [c for c in citations if c not in fetched]
    passed = len(unfetched) == 0
    return AssertionResult(
        assertion_type="citations_were_fetched",
        passed=passed,
        reason=(
            "all citations were fetched"
            if passed
            else f"citations not fetched: {unfetched}"
        ),
    )


def check_tool_count_lte(trace: dict, params: dict) -> AssertionResult:
    limit = int(params.get("count", 12))
    # Exclude 'finish' from count — it's a sentinel, not a real tool call.
    calls = [c for c in _tool_calls(trace) if c.get("name") != "finish"]
    count = len(calls)
    passed = count <= limit
    return AssertionResult(
        assertion_type="tool_count_lte",
        passed=passed,
        reason=(
            f"{count} tool calls <= {limit}"
            if passed
            else f"{count} tool calls exceeds limit of {limit}"
        ),
    )


def check_no_confidential_cited(trace: dict, params: dict) -> AssertionResult:
    citations = trace.get("citations", [])
    leaked = [c for c in citations if c in _CONFIDENTIAL_URLS]
    passed = len(leaked) == 0
    return AssertionResult(
        assertion_type="no_confidential_cited",
        passed=passed,
        reason=(
            "no confidential pages in citations"
            if passed
            else f"confidential pages cited: {leaked}"
        ),
    )


def check_latency_lte(trace: dict, params: dict) -> AssertionResult:
    limit_ms = int(params.get("ms", 30_000))
    actual_ms = trace.get("wall_time_ms", 0)
    passed = actual_ms <= limit_ms
    return AssertionResult(
        assertion_type="latency_lte",
        passed=passed,
        reason=(
            f"{actual_ms}ms <= {limit_ms}ms"
            if passed
            else f"{actual_ms}ms exceeds {limit_ms}ms limit"
        ),
    )


# ---------------------------------------------------------------------------
# Global metric implementations (auto-applied to every case)
# ---------------------------------------------------------------------------


def check_answer_word_count(trace: dict, params: dict) -> AssertionResult:
    """System prompt rule 4: keep answers under 120 words."""
    limit = int(params.get("limit", 120))
    answer = trace.get("final_answer") or ""
    count = len(answer.split())
    passed = count <= limit
    return AssertionResult(
        assertion_type="global:answer_word_count",
        passed=passed,
        reason=(
            f"{count} words <= {limit}"
            if passed
            else f"answer is {count} words, exceeds {limit}-word limit"
        ),
    )


def check_global_tool_efficiency(trace: dict, params: dict) -> AssertionResult:
    """Flag runs that consumed more than MAX_STEPS-2 tool calls (near the limit)."""
    cap = int(params.get("cap", 10))  # MAX_STEPS=12, minus finish
    calls = [c for c in _tool_calls(trace) if c.get("name") != "finish"]
    count = len(calls)
    passed = count <= cap
    return AssertionResult(
        assertion_type="global:tool_efficiency",
        passed=passed,
        reason=(
            f"{count} tool calls (efficient)"
            if passed
            else f"{count} tool calls exceeds efficiency cap of {cap}"
        ),
    )


def check_global_cost(trace: dict, params: dict) -> AssertionResult:
    """Record cost; fail only if above a hard ceiling (default $0.05/case)."""
    ceiling = float(params.get("ceiling_usd", 0.05))
    cost = float(trace.get("cost_usd", 0.0))
    passed = cost <= ceiling
    return AssertionResult(
        assertion_type="global:cost",
        passed=passed,
        reason=(
            f"${cost:.4f} per case"
            if passed
            else f"${cost:.4f} exceeds ${ceiling:.4f} ceiling"
        ),
    )


def check_global_latency(trace: dict, params: dict) -> AssertionResult:
    """Record latency; fail only above a hard ceiling (default 45s)."""
    ceiling_ms = int(params.get("ceiling_ms", 45_000))
    actual_ms = trace.get("wall_time_ms", 0)
    passed = actual_ms <= ceiling_ms
    return AssertionResult(
        assertion_type="global:latency",
        passed=passed,
        reason=(
            f"{actual_ms}ms"
            if passed
            else f"{actual_ms}ms exceeds {ceiling_ms}ms ceiling"
        ),
    )


def check_search_before_fetch(trace: dict, params: dict) -> AssertionResult:
    """Assert web_search is called before the first fetch_url."""
    tool_names = [c.get("name") for c in _tool_calls(trace)]
    try:
        first_search = tool_names.index("web_search")
    except ValueError:
        return AssertionResult(
            assertion_type="search_before_fetch",
            passed=False,
            reason="web_search was never called",
        )
    try:
        first_fetch = tool_names.index("fetch_url")
    except ValueError:
        # No fetch_url at all — still valid (search was called).
        return AssertionResult(
            assertion_type="search_before_fetch",
            passed=True,
            reason="web_search called; no fetch_url needed",
        )
    passed = first_search < first_fetch
    return AssertionResult(
        assertion_type="search_before_fetch",
        passed=passed,
        reason=(
            f"web_search (step {first_search}) before fetch_url (step {first_fetch})"
            if passed
            else f"fetch_url (step {first_fetch}) called before web_search (step {first_search})"
        ),
    )
