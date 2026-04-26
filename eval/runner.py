"""Async parallel runner.

- Runs test cases concurrently up to a configurable semaphore cap.
- Retries on transient errors (429, 5xx, network timeouts).
- Never retries on assertion failures.
- Supports --repeats N for flakiness detection.
- Saves each trace to traces/{run_id}.json before scoring.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from eval.models import CaseResult, TestCase
from eval.scorer import score_trace

_TRACES_DIR = Path(__file__).parent.parent / "traces"
_TRACES_DIR.mkdir(exist_ok=True)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 5))
BASE_BACKOFF = float(os.getenv("BASE_BACKOFF", 3.0))  # seconds

def _is_retryable(exc: Exception) -> bool:
    """Return True for transient API errors that warrant a retry."""
    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS:
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)):
        return True
    return False


def _run_agent_sync(question: str, model: str) -> dict[str, Any]:
    """Run the agent synchronously (called from a thread pool)."""
    from agent import run_agent  # project-level import

    result = run_agent(question, model=model)
    return result.to_dict()


async def _run_with_retry(question: str, model: str, loop: asyncio.AbstractEventLoop) -> dict[str, Any]:
    for attempt in range(MAX_RETRIES + 1):
        try:
            trace = await loop.run_in_executor(None, _run_agent_sync, question, model)
            # The agent may catch its own API errors and return stopped_reason=error
            # instead of raising. Any error trace is retryable — it produced no answer.
            if attempt < MAX_RETRIES and trace.get("stopped_reason") == "error":
                wait = BASE_BACKOFF * (2 ** attempt)
                print(f"  [RETRY {attempt+1}/{MAX_RETRIES}] agent error: {str(trace.get('error',''))[:80]} — retrying in {wait:.0f}s")
                await asyncio.sleep(wait)
                continue
            return trace
        except Exception as exc:
            if attempt < MAX_RETRIES and _is_retryable(exc):
                wait = BASE_BACKOFF * (2 ** attempt)
                print(f"  [RETRY {attempt+1}/{MAX_RETRIES}] {type(exc).__name__} — retrying in {wait:.0f}s")
                await asyncio.sleep(wait)
                continue
            raise


async def _run_one(
    case: TestCase,
    repeat_index: int,
    semaphore: asyncio.Semaphore,
    model: str,
    loop: asyncio.AbstractEventLoop,
) -> CaseResult:
    async with semaphore:
        try:
            trace = await _run_with_retry(case.input, model, loop)
        except Exception as exc:
            # Fatal error for this case — build a minimal trace and mark failed.
            trace = {
                "run_id": str(uuid.uuid4()),
                "question": case.input,
                "model": model,
                "messages": [],
                "final_answer": None,
                "citations": [],
                "stopped_reason": "error",
                "total_tokens": {"input": 0, "output": 0},
                "cost_usd": 0.0,
                "wall_time_ms": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }

        # Persist trace to disk before scoring so re-scoring always works.
        trace_path = _TRACES_DIR / f"{trace['run_id']}.json"
        trace_path.write_text(json.dumps(trace, indent=2))

        result = score_trace(trace, case, trace_path, repeat_index=repeat_index)
        return result


async def run_suite(
    cases: list[TestCase],
    repeats: int = 1,
    concurrency: int = 5,
    model: str = "claude-haiku-4-5",
) -> list[CaseResult]:
    semaphore = asyncio.Semaphore(concurrency)
    loop = asyncio.get_event_loop()

    tasks = [
        _run_one(case, repeat_index, semaphore, model, loop)
        for case in cases
        for repeat_index in range(repeats)
    ]

    results: list[CaseResult] = []
    for coro in asyncio.as_completed(tasks):
        result = await coro
        status = "PASS" if result.passed else "FAIL"
        repeat_tag = f" (repeat {result.repeat_index + 1})" if repeats > 1 else ""
        print(f"  [{status}] {result.case_id}{repeat_tag}")
        if not result.passed:
            for reason in result.failure_reasons():
                print(f"         {reason}")
        results.append(result)

    return results
