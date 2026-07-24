# Quickstart: Validating `maverick reconcile`

Runnable scenarios proving the feature end-to-end. Contracts:
[cli-reconcile.md](contracts/cli-reconcile.md),
[ledger-state.md](contracts/ledger-state.md); shapes in
[data-model.md](data-model.md).

## Prerequisites

- `uv sync` completed; `make check` green on the branch.
- `jj` ≥ 0.43 and `bd` on PATH.
- A colocated test repo (integration fixtures build one; for manual runs use
  a scratch clone of `sample-maverick-project` with `maverick init`).
- Agent runtime bindings configured in `maverick.yaml` (`agents.implement`,
  `agents.review`) for the non-dry-run scenarios.

## Automated validation

```bash
make test-fast                 # unit suites incl. workflows/reconcile, assumptions, cli
make test-integration          # real-jj scenarios: fold, auto-rebase, op-restore round-trip
make ci                        # pre-push gate
```

Key suites: `tests/unit/workflows/reconcile/`,
`tests/unit/assumptions/test_ledger_reconcile.py`,
`tests/unit/cli/test_reconcile_command.py`,
`tests/integration/workflows/test_reconcile_jj.py`.

## Scenario 1 — Clean retroactive application (US1, SC-001)

Setup (fixture or manual): a stack `base ← A ← B ← C` of unpushed changes
where `A` is stamped on an answered ledger entry whose human answer differs
from the adopted answer; `B`/`C` don't touch the corrected lines.

```bash
maverick reconcile --dry-run    # expect: 1 answer, "would reconcile", exit 0, no mutations
maverick reconcile
```

Expected: exit 0; summary shows `reconciled`; `jj diff -r <A>` contains the
corrected code; `jj log` shows no fixup change at the tip; descendants `B`,`C`
present and conflict-free; entry state has
`assumption_reconcile_status=reconciled` + change id; gate suite reported
passing. Re-run `maverick reconcile` → "nothing to reconcile", exit 0, zero
history mutations (SC-008).

## Scenario 2 — Rollback on failure (US2, SC-002)

Same setup, but sabotage the gate (e.g. `validation.test_cmd` pointing at a
failing test seeded by the correction).

Expected: exit 1; status `needs interactive review` with gate reason;
`jj op log` shows a restore; `jj log`/`jj diff` byte-identical to pre-run
state on affected files; entry re-armed only after
`maverick review <id> --answer "..."`, after which reconcile picks it up
again.

## Scenario 3 — Conflict resolution within budget (US3)

Setup: descendant `B` edits the same lines the correction changes.

Expected: reconcile resolves the conflict in favor of the new answer within
`reconcile.resolution_rounds`; `jj log -r 'conflicts()'` empty afterwards;
exit 0.

Budget exhaustion variant: set `reconcile: {resolution_rounds: 1}` in
`maverick.yaml` with a multi-file conflict the single round can't clear.
Expected: rollback (Scenario 2 checks), one new escalation bead
(`escalation_type=reconcile_exhaustion`) containing question/old/new answers
and remaining conflicts; exit 1 (SC-004).

## Scenario 4 — Semantic dependents (US4, SC-007)

Setup: descendant `C` hard-codes a value derived from the old assumption in a
file the correction doesn't touch; descendant `B` is unrelated.

Expected: `C`'s diff after reconcile contains the corrected derived value;
`B` byte-identical; gates pass; exit 0.

## Scenario 5 — Batch, order, immutability (US5, SC-003, SC-005)

Setup: two changed answers at different stack depths, plus a third whose
stamped change is behind an `immutable()` boundary (e.g. push its ancestor to
a remote bookmark, or set `revset-aliases."immutable_heads()"` in the repo's
jj config to cover it).

Expected: single invocation processes both mutable answers earliest-first
(observable in per-answer output ordering); the immutable one reports
`needs interactive review` with an immutability reason and its history is
untouched; exit 1 (because one answer was not reconciled); the two applied
answers remain applied.

## Scenario 6 — Refuse-to-start guards (FR-014)

- Dirty working copy (`echo x >> file` without committing) → exit 1, clean-
  working-copy message, zero mutations.
- Stale lockfile with dead pid → reclaimed, run proceeds.
- Simulated interrupted run (fixture writes a `running` reconcile.json with a
  mid-stage answer + valid op id) → next invocation restores that op first,
  marks the answer `needs interactive review`, processes the rest (FR-016).
