# Contract: Persisted chain state & resume

**File**: `.maverick/runs/<run-id>/spec-chain.json` (Pydantic `ChainState`,
`schema_version: 1`), beside a standard `metadata.json` written via
`runway.run_metadata` helpers. Treated as a public interface (Guardrail X.4): fields
are additive-only within schema_version 1.

## Write discipline

- Atomic writes only (temp file + `rename`), after **every** transition:
  step start, step success, landing success, halt, completion.
- Checkpoint ordering: workspace artifact write → landing sync → `landed=true` →
  checkpoint. Resume logic trusts only `landed` steps' artifacts.

## Resume resolution (`maverick spec <feature>`)

1. Scan `.maverick/runs/*/spec-chain.json` (newest `updated_at` first).
2. First state with `feature == FEATURE` and `status in {"halted", "running"}` → resume.
   (`"running"` covers crash/kill: staleness is assumed, not probed — single-user CLI.)
3. Resume behavior: recreate/reuse workspace; verify landed artifacts exist in the user
   checkout (missing → re-run that step); continue from the first step whose status is
   not `succeeded`. PRD digest mismatch → proceed with warning (spec artifacts already
   derive from the old PRD; specify is not re-run unless it never succeeded).
4. No matching resumable state → fresh run (new run-id, workspace recreated).

## Guarantees (traceability)

- FR-016/SC-007: user's `specs/` tree only ever receives complete, atomically-synced
  step artifact sets (landing contract above).
- FR-020: halted/interrupted chains resume from the first non-succeeded step with zero
  regeneration of landed steps.
- FR-009: `steps[CLARIFY].status == "failed"` ⇒ `status == "halted"` and
  plan/tasks/analyze remain `pending`/`skipped` — enforced in `workflow.py`, visible in
  persisted state for post-mortem.
