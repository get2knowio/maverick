# Contract: Agent Payload Additions

Consumers: OpenCode structured-output tool (schema synthesized from Pydantic),
fly_beads actions reading step results.

## AssumptionPayload

New model in `maverick.payloads`. JSON shape the model is prompted to emit:

```json
{
  "question": "Should the retry limit apply per bead or per run?",
  "adopted_answer": "Per bead — matches existing MAX_REVIEW_ROUNDS scoping.",
  "alternatives": ["Per run with a global counter", "Configurable in maverick.yaml"],
  "severity": "medium"
}
```

Rules:

- `question` and `adopted_answer`: required, non-empty strings.
- `alternatives`: optional list of strings, default `[]`.
- `severity`: one of `"low" | "medium" | "high"`. Any other value (or absence)
  is coerced to `"medium"` by the model validator, which also sets a
  `severity_defaulted: bool` field on the validated payload (excluded from the
  schema shown to the model); `record_assumption` reads that flag to persist
  `assumption_severity_defaulted=true`. The payload NEVER fails validation
  because of severity (FR-011). This is the same rule the ledger re-applies
  for direct (non-payload) callers — see `ledger-api.md` "Severity rule".

## Extended submit payloads

`SubmitImplementationPayload`, `SubmitReviewPayload`, `SubmitFixResultPayload`
each gain:

```json
{ "assumptions": [ AssumptionPayload, ... ] }
```

- Optional; default `[]`. Existing agent prompts that never mention
  assumptions keep validating unchanged (backward compatible).
- Registry keys in `SUPERVISOR_TOOL_PAYLOAD_MODELS` are unchanged
  (`submit_implementation`, `submit_review`, `submit_fix_result`).
- Stability: additive-only change; existing fields and their semantics are
  untouched (Constitution Guardrail 4 — payloads are public interfaces).

## Prompt contract (agents/)

Implementer, reviewer, and fixer prompt builders instruct the model: when you
adopt an assumption to keep working, report it in `assumptions` with the
question, your adopted answer, the alternatives you considered, and a severity
reflecting the blast radius of being wrong (`low` = cosmetic/local, `medium` =
owning spec's correctness, `high` = decisions later specs will build on).
Recording is additive — it never replaces implementing/reviewing work.
