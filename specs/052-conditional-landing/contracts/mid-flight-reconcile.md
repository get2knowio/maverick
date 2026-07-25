# Contract: mid-flight reconcile (fly ↔ reconcile integration)

## Burr graph change (`workflows/fly_beads/burr_graph.py`)

New action `reconcile_answers`, spliced so every bead boundary and the
loop-exit path pass through it:

```
record_outcome ──► reconcile_answers ──► select_next_bead
abandon_bead   ──► reconcile_answers ──► select_next_bead
(loop exit) select_next_bead ──► reconcile_answers_final ──► aggregate_review
```

(The final pass may be the same action re-entered with a state flag rather
than a second action — implementation's choice; the contract is: one
detection+processing opportunity after the last bead completes and before the
run is declared complete.)

## Action contract (`workflows/fly_beads/mid_flight.py`)

`async def run_mid_flight_pass(*, cwd, config, fly_run_id, event_sink) -> MidFlightOutcome`

Preconditions (checked in order; each short-circuits to a skipped outcome):

1. `config.reconcile.mid_flight` is False → `skipped_reason="disabled"`.
2. Graceful stop requested → `skipped_reason="graceful-stop"` (answers remain
   detectable by later runs — FR-014).
3. `answered_unreconciled_entries(client)` empty → `skipped_reason="none-detected"`.
   (bd query failure counts as empty + warning event; never raises.)

Processing (only when detection non-empty):

- Invokes `ReconcileWorkflow` in-process:
  `inputs = {"run_id": <fresh 8-hex>, "cwd": str(cwd), "dry_run": False,
  "active_fly_run_id": fly_run_id}`.
- Forwards the child workflow's `ProgressEvent`s into fly's event queue
  (visible in the run's progress stream under a reconcile grouping).
- The pass inherits reconcile's own per-answer transaction model, mutability
  guard, round budgets, and escalation unchanged — no mid-flight-specific
  relaxations.

Postconditions:

- Working copy is back on an empty `@` child (reconcile's final landing step)
  — `select_next_bead` proceeds normally.
- Any exception (`WorkflowError`, `MaverickError`) is caught → warning event
  + `MidFlightOutcome(error=…)`; the drain loop continues (FR-013). The
  action **never** raises into the Burr application.
- Detection is re-run at every subsequent boundary, so answers arriving
  during a pass are handled next boundary (FR-014) and idempotence guards
  prevent re-application (FR-015).

## `ReconcileWorkflow` input change (`workflows/reconcile/workflow.py`)

| Input | Type | Default | Semantics |
|---|---|---|---|
| `active_fly_run_id` | `str \| None` | `None` | When set, the concurrent-fly guard ignores the run directory whose metadata `run_id` matches; any *other* run with `status == "flying"` still raises `WorkflowError`. |

Unchanged guards: clean-working-copy (`@` diff must be empty — guaranteed at
bead boundaries by `commit()`'s fresh-child postcondition), reconcile
lockfile (mutual exclusion vs. concurrent standalone reconcile),
interrupted-run recovery, dry-run mode.

## Readiness release (FR-012) — no new interface

`ledger.answer()`/`waive()` close the entry bead → bd releases `blocks`
edges → `select_next_bead`'s existing `bd_select` re-query picks up newly
ready beads at the next cycle. Scope caveat: `fly --epic <id>` only drains
that epic; cross-spec pickup within one run applies to global / `--watch`
runs.

## Events (fly progress stream)

- Pass start (detected count), per-answer outcomes (forwarded reconcile
  events), pass end (`MidFlightOutcome` summary), warning on failure — all
  via the existing `ProgressEvent` types; no new event classes unless a
  one-line summary event proves necessary during implementation.
