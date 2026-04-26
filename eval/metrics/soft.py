"""Soft assertion dispatcher — routes to the LLM judge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.models import AssertionResult, SoftAssertion

_RUBRICS_DIR = Path(__file__).parent.parent.parent / "rubrics"


def _load_rubric(rubric_file: str | None) -> str | None:
    if not rubric_file:
        return None
    path = _RUBRICS_DIR / rubric_file if not Path(rubric_file).is_absolute() else Path(rubric_file)
    # Strip leading "rubrics/" prefix if it was included in the YAML.
    if not path.exists():
        path = _RUBRICS_DIR / Path(rubric_file).name
    try:
        return path.read_text()
    except FileNotFoundError:
        return None


def check_soft_assertion(
    trace: dict[str, Any],
    assertion: SoftAssertion,
    rubric_text: str | None = None,
) -> AssertionResult:
    # Import here to avoid circular imports and to keep judge lazy-loaded.
    from eval.judge import run_judge

    rubric = rubric_text or _load_rubric(assertion.rubric_file)

    verdict = run_judge(
        question=trace.get("question", ""),
        final_answer=trace.get("final_answer") or "",
        citations=trace.get("citations", []),
        assertion_type=assertion.type,
        rubric=rubric,
        reference=assertion.reference,
        context=assertion.context,
    )

    return AssertionResult(
        assertion_type=assertion.type,
        passed=verdict.verdict == "pass",
        reason=verdict.rationale,
        rationale=verdict.rationale,
    )
