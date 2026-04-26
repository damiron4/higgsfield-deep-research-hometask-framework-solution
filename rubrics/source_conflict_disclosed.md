# Rubric: Source Conflict Disclosed

## What this rubric checks
Whether the agent acknowledged conflicting or inconsistent information across sources instead of silently presenting one version as definitive.

## How to determine how many sources were fetched
Count the distinct URLs in the agent's citations list. Do not infer source count
from the answer text — an agent can produce a dual-unit answer from a single source
that lists both, or paraphrase multiple values from memory.

## Pass criteria
- The agent notes that multiple sources exist with different values or units.
- The agent reconciles conflicts explicitly (e.g., attributes values to specific sources).
- If the citations list contains only one URL, this assertion passes automatically —
  you cannot disclose a conflict you didn't observe.
- Using the best source and ignoring a clearly inferior one (e.g., an authoritative spec
  vs. a speculative or draft page) is acceptable without explicit disclosure.

## Fail criteria
- The agent fetched two sources with contradictory numbers/facts and presented both
  as true simultaneously without noting the conflict.
- The agent averaged or silently mixed conflicting measurements from different unit systems.
- The agent cited a draft/speculative page as authoritative without qualification.

