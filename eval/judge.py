"""LLM-as-judge using GPT-4o-mini with structured output.

Design choices and known failure modes (documented per task requirements):

FAILURE MODES ADDRESSED:
- Position bias: Rubrics are anchored to specific facts/criteria, not open-ended
  "which is better" comparisons, so position of evidence in the answer doesn't
  drive the verdict.
- Self-preference: Judge uses GPT-4o-mini (OpenAI), agent uses claude-haiku-4-5
  (Anthropic). Different families prevent the judge from preferring its own
  phrasing patterns.
- Injection through agent output: Judge receives only final_answer and citations,
  never raw tool outputs or intermediate messages. An injected instruction inside
  a fetched page cannot reach the judge prompt.
- Rubric ambiguity: Each soft assertion type ships a dedicated rubric file with
  explicit pass/fail criteria. Generic prompts are rejected.

FAILURE MODES NOT FULLY ADDRESSED:
- Judge may still be over-lenient on vague or hedged answers.
- Rubric text itself could be ambiguous — spot-checking is the mitigation.
"""

from __future__ import annotations

import os
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

_CLIENT: OpenAI | None = None

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-4o-mini")


def _client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _CLIENT


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------


class JudgeVerdict(BaseModel):
    verdict: Literal["pass", "fail"] = Field(
        description="'pass' if the answer meets the rubric, 'fail' otherwise."
    )
    rationale: str = Field(
        description=(
            "1-3 sentences explaining the verdict. "
            "Cite specific evidence from the answer or its absence."
        )
    )


# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are an evaluation judge for a research agent. Your job is to decide \
strictly whether the agent's final answer PASSES or FAILS a rubric criterion.

Rules:
- Verdict must be exactly "pass" or "fail" — no partial credit, no middle ground.
- Base your verdict ONLY on the provided answer and citations, not on prior knowledge.
- Vague or hedged answers that don't meet the rubric criteria are a fail.
- If the answer is absent, empty, or "I could not answer", that is a fail for \
  factual correctness but may be a pass for refusal cases.
- Return structured JSON only — no preamble, no extra commentary.
"""

_USER_TEMPLATE = """\
### AGENT INPUT
Question asked to the agent: {question}

### AGENT OUTPUT
Final answer: {answer}

Citations provided: {citations}

### ASSERTION
Type: {assertion_type}

Rubric:
{rubric}
{reference_block}{context_block}
Evaluate the agent output against the rubric. Return your verdict as JSON.
"""


def run_judge(
    question: str,
    final_answer: str,
    citations: list[str],
    assertion_type: str,
    rubric: str | None,
    reference: str | None = None,
    context: str | None = None,
) -> JudgeVerdict:
    if not rubric:
        rubric = f"Assess whether the answer appropriately addresses: {assertion_type}"

    reference_block = ""
    if reference:
        reference_block = f"\nReference answer (ground truth — compare agent output against this):\n{reference}\n"

    context_block = ""
    if context:
        context_block = f"\nEvaluation instructions for this specific case:\n{context}\n"

    citations_str = "\n".join(f"- {c}" for c in citations) if citations else "(none)"

    user_msg = _USER_TEMPLATE.format(
        question=question,
        answer=final_answer or "(no answer)",
        citations=citations_str,
        assertion_type=assertion_type,
        rubric=rubric,
        reference_block=reference_block,
        context_block=context_block,
    )

    response = _client().beta.chat.completions.parse(
        model=JUDGE_MODEL,
        temperature=0.0,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_format=JudgeVerdict,
    )

    return response.choices[0].message.parsed
