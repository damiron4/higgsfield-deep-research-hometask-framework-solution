# Rubric: Ambiguity Disclosed

## What this rubric checks
Whether the agent acknowledged ambiguity when a question could refer to multiple
distinct corpus entries, rather than silently picking one.

## Pass criteria (ANY one of these is sufficient to pass)
- The agent's answer covers multiple relevant entities by name — even without an
  explicit statement like "your question was ambiguous".
- The agent asks the user for clarification about which entity they mean.
- The agent explicitly says something like "there are several X, here is an overview."

**Key rule:** If the answer substantively addresses more than one matching entity,
that IS disclosing ambiguity — award a pass even if the agent never says
"your question was ambiguous."

## Fail criteria
- The agent picks exactly one entity and gives no information about the others,
  with no mention that alternatives exist.
- The agent's answer is entirely about one entity and the others are completely absent.

