"""Metric plugin registry.

Adding a new assertion type = one entry in HARD_REGISTRY or SOFT_REGISTRY.
The runner and scorer core never need to change.

Each hard metric is a callable:
    fn(trace: dict, params: dict) -> AssertionResult

Each soft metric is a callable:
    fn(trace: dict, assertion: SoftAssertion, rubric_text: str | None) -> AssertionResult
"""

from __future__ import annotations

from typing import Callable, Any

from eval.metrics.hard import (
    check_stopped_reason,
    check_tool_called,
    check_tool_sequence,
    check_answer_contains,
    check_answer_not_contains,
    check_citations_were_fetched,
    check_tool_count_lte,
    check_no_confidential_cited,
    check_latency_lte,
    check_search_before_fetch,
    check_answer_word_count,
    check_global_tool_efficiency,
    check_global_cost,
    check_global_latency,
)
from eval.metrics.soft import check_soft_assertion

HARD_REGISTRY: dict[str, Callable] = {
    "stopped_reason": check_stopped_reason,
    "tool_called": check_tool_called,
    "tool_sequence": check_tool_sequence,
    "answer_contains": check_answer_contains,
    "answer_not_contains": check_answer_not_contains,
    "citations_were_fetched": check_citations_were_fetched,
    "tool_count_lte": check_tool_count_lte,
    "no_confidential_cited": check_no_confidential_cited,
    "latency_lte": check_latency_lte,
    "search_before_fetch": check_search_before_fetch,
}

SOFT_REGISTRY: dict[str, Callable] = {
    "factual_correctness": check_soft_assertion,
    "refusal_appropriate": check_soft_assertion,
    "ambiguity_disclosed": check_soft_assertion,
    "no_system_prompt_leak": check_soft_assertion,
    "injection_resistant": check_soft_assertion,
    "citation_quality": check_soft_assertion,
    "source_conflict_disclosed": check_soft_assertion,
}

# ---------------------------------------------------------------------------
# Global metrics — auto-applied to every case, no YAML declaration needed.
# Covers the four required metric categories from the task spec:
#   correctness      → per-case hard + soft assertions (above)
#   tool efficiency  → global:tool_efficiency
#   cost & latency   → global:cost, global:latency
#   safety/format    → global:answer_word_count, global:no_confidential_cited
#
# Each entry is (check_fn, default_params).
# Adding a new global metric = one tuple here. Runner/scorer untouched.
# ---------------------------------------------------------------------------

GLOBAL_METRICS: list[tuple[Callable, dict]] = [
    (check_answer_word_count,        {"limit": 120}),
    (check_global_tool_efficiency,   {"cap": 10}),
    (check_global_cost,              {"ceiling_usd": 0.05}),
    (check_global_latency,           {"ceiling_ms": 45_000}),
    (check_no_confidential_cited,    {}),
]
