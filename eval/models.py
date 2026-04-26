"""Shared data models for the evaluation framework."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Test case schema (loaded from YAML)
# ---------------------------------------------------------------------------


@dataclass
class HardAssertion:
    type: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HardAssertion:
        t = d.pop("type")
        return cls(type=t, params=d)


@dataclass
class SoftAssertion:
    type: str
    rubric_file: str | None = None
    reference: str | None = None  # ground-truth anchor (correct answer / key facts)
    context: str | None = None    # meta-instructions for the judge (how to evaluate)
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SoftAssertion:
        t = d.pop("type")
        rubric_file = d.pop("rubric_file", None)
        reference = d.pop("reference", None)
        context = d.pop("context", None)
        return cls(type=t, rubric_file=rubric_file, reference=reference, context=context, params=d)


@dataclass
class ExpectedBehavior:
    hard: list[HardAssertion] = field(default_factory=list)
    soft: list[SoftAssertion] = field(default_factory=list)


@dataclass
class TestCase:
    id: str
    input: str
    expected_behavior: ExpectedBehavior
    tags: list[str] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TestCase:
        eb_raw = d.get("expected_behavior", {})
        hard = [HardAssertion.from_dict(dict(a)) for a in eb_raw.get("hard", [])]
        soft = [SoftAssertion.from_dict(dict(a)) for a in eb_raw.get("soft", [])]
        return cls(
            id=d["id"],
            input=d["input"],
            expected_behavior=ExpectedBehavior(hard=hard, soft=soft),
            tags=d.get("tags", []),
            description=d.get("description", ""),
        )


# ---------------------------------------------------------------------------
# Scoring results
# ---------------------------------------------------------------------------


@dataclass
class AssertionResult:
    assertion_type: str
    passed: bool
    reason: str
    rationale: str | None = None  # judge rationale for soft assertions


@dataclass
class CaseResult:
    case_id: str
    run_id: str
    repeat_index: int  # 0-based when --repeats N > 1
    passed: bool
    assertion_results: list[AssertionResult]
    trace_path: Path
    wall_time_ms: int = 0
    cost_usd: float = 0.0
    tool_call_count: int = 0
    stopped_reason: str = ""
    error: str | None = None

    def failure_reasons(self) -> list[str]:
        return [
            f"[{r.assertion_type}] {r.reason}"
            for r in self.assertion_results
            if not r.passed
        ]


# ---------------------------------------------------------------------------
# Run report
# ---------------------------------------------------------------------------


@dataclass
class CaseSummary:
    case_id: str
    total_repeats: int
    passes: int
    failures: int

    @property
    def pass_rate(self) -> float:
        return self.passes / self.total_repeats if self.total_repeats else 0.0

    def label(self) -> str:
        if self.total_repeats == 1:
            return "PASS" if self.passes == 1 else "FAIL"
        return f"{self.passes}/{self.total_repeats} passed"


@dataclass
class RunReport:
    run_id: str
    timestamp: str
    model: str
    total_cases: int
    total_repeats: int
    summaries: list[CaseSummary]
    all_results: list[CaseResult]
    total_cost_usd: float
    p50_latency_ms: float
    p95_latency_ms: float
    mean_tool_calls: float
    previous_run_id: str | None = None
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        total = sum(s.total_repeats for s in self.summaries)
        passed = sum(s.passes for s in self.summaries)
        return passed / total if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "model": self.model,
            "total_cases": self.total_cases,
            "total_repeats": self.total_repeats,
            "pass_rate": round(self.pass_rate, 4),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "mean_tool_calls": round(self.mean_tool_calls, 2),
            "previous_run_id": self.previous_run_id,
            "regressions": self.regressions,
            "improvements": self.improvements,
            "cases": [
                {
                    "case_id": s.case_id,
                    "label": s.label(),
                    "pass_rate": round(s.pass_rate, 4),
                    "passes": s.passes,
                    "total_repeats": s.total_repeats,
                    "failure_reasons": [
                        r
                        for res in self.all_results
                        if res.case_id == s.case_id
                        for r in res.failure_reasons()
                    ],
                }
                for s in self.summaries
            ],
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))
