# Contract: Ledger reconcile state & queries

Module: `src/maverick/assumptions/` (`models.py`, `ledger.py`). These are
public interfaces per Guardrail X.4 — stable across versions.

## New state keys (bd `set-state`)

See data-model §1 for the full table. Contract points:

- Keys are additive; absence means "never entered reconcile". No migration of
  existing entries.
- `assumption_reconcile_status` has exactly two values:
  `"reconciled"` and `"needs-interactive-review"`.
- `ledger.answer()` MUST clear `assumption_reconcile_status` (set to empty)
  whenever a human records an answer — this is the only re-arm path (FR-017).
- `mark_reconciled` / `mark_needs_interactive_review` never raise on per-entry
  bd failure (log + report, matching `stamp_change_id` semantics) — the repo
  outcome is already settled when they run.

## New query: `answered_unreconciled_entries(client) -> list[AssumptionRecord]`

Detection predicate (all must hold; research R1):

1. Bead carries `ASSUMPTION_LABEL` (legacy escalation beads excluded).
2. `assumption_status == "answered"`.
3. `assumption_reconcile_status` unset/empty
   (needs-interactive-review entries are excluded until re-armed).
4. `normalize(assumption_answer) != normalize(adopted_answer)` where
   `normalize(t) = " ".join(t.split()).casefold()`.
5. Not previously applied for this same answer:
   `normalize(assumption_answer) != normalize(assumption_reconciled_answer)`
   (idempotence, SC-008).

MUST query beads regardless of bd status (`answer()` closes beads — an
open-only query returns nothing). Returns records ordered by entry id; stack
ordering is the workflow's job (jj position, not ledger data).

## New mutators

```python
def mark_reconciled(client, *, entry_id, applied_answer, change_id) -> bool
def mark_needs_interactive_review(client, *, entry_id, reason) -> bool
```

Both: set the keys from data-model §1, return success bool, never raise.
`mark_reconciled` stamps `assumption_reconciled_at` (UTC ISO) and stores the
**normalized** applied answer.

## Escalation bead creation

`create_reconcile_escalation(client, *, entry, remaining, kind) -> str | None`
(kind: `"conflicts" | "semantic"`): creates the bead per data-model §6, wires
`discovered-from` edge entry ← bead, returns new bead id. Called only
post-rollback (research R8 ordering).

## Interaction with existing surfaces (must not regress)

- `open_blocking_entries` (land gate): unaffected — reconcile operates on
  closed/answered entries which that query never returns.
- `per_spec_counts` (brief): unchanged buckets; reconcile status is not
  counted in this feature (future enhancement, out of scope).
- `select_next_bead` agent-skip filter: escalation beads carry
  `needs-human-review` label → still skipped. Ledger entries unchanged.
- `maverick review` on an escalation bead: existing legacy flow handles it;
  re-answering the original entry via `maverick review <entry-id> --answer`
  re-arms detection.
