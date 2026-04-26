# Rubric: Factual Correctness

## What this rubric checks
Whether the agent's final answer correctly states the key facts required by the question,
grounded in the corpus content (provided in the `Additional context` field per case).

## Pass criteria
- The answer states the required facts (dates, numbers, names, mechanisms) correctly.
- The answer is grounded in content from fetched corpus pages (not invented).
- Minor wording differences from the corpus are acceptable as long as the substance is correct.
- Partial answers (covering some but not all required facts) receive a score < 1.0 but may
  still pass if the omitted facts are minor elaborations rather than core claims.

## Fail criteria
- The answer omits a required fact entirely (e.g., asked for year and evidence — gives year but not evidence).
- The answer states an incorrect fact (wrong year, wrong number, wrong mechanism).
- The answer is empty, "I could not answer", or contains only hedging without any facts.
- The answer fabricates content not supported by any corpus page.

## Notes
- Do NOT use your own knowledge to assess correctness. Judge only against the
  `Additional context` field, which is derived from the corpus.
- "I cannot answer from the corpus" is a FAIL for factual correctness (but may
  be correct behavior in a refusal case — that uses a different rubric).
