# Quickstart: validating conditional landing + mid-flight answering

Prerequisites: `uv sync`; `bd` and `jj` on PATH; a Maverick-initialized repo
(`maverick init` — colocated `.jj/`). For fast, deterministic checks use the
test suite; the manual scenarios mirror the integration tests in
`tests/integration/test_assumption_ledger_flow.py`.

## Automated validation

```bash
make test-fast          # unit: gate, classification, report, bulk waive, mid-flight
make test-integration   # end-to-end with real bd + jj
make ci                 # pre-push gate (lint + typecheck + format + tests)
```

Key suites: `tests/unit/assumptions/test_ledger_frontier.py`,
`tests/unit/assumptions/test_land_report.py`,
`tests/unit/cli/test_land_command.py::TestAssumptionGate` (extended),
`tests/unit/cli/test_review_command.py` (bulk waive),
`tests/unit/workflows/fly_beads/test_mid_flight.py`,
`tests/unit/workflows/reconcile/test_workflow.py` (guard exclusion).

## Scenario 1 — strict gate + verification states (US1)

In a scratch repo with three ledger entries (one per severity, e.g. seeded
via the integration-test helpers or a real `maverick fly` run):

```bash
maverick land --dry-run        # expect: Blocking Assumptions (3), exit != 0
maverick review <low-id>  --waive "accepted for MVP"
maverick review <med-id>  --answer "use UTC everywhere"
maverick review <high-id> --answer "keep the v2 schema"
maverick land --dry-run        # expect: ✓ Conditionally verified (1 waived), exit 0
```

Checks: no bypass flag in `maverick land --help`; with only the low entry
open, land still blocks (strict gate); report path
`.maverick/runs/<id>/land-report.json` printed and both artifacts exist.

## Scenario 2 — provenance report (US2)

After Scenario 1, change one answered entry's answer
(`maverick review <med-id> --answer "actually, local time"`), then:

```bash
maverick land --dry-run        # expect: BLOCKED — pending reconciliation row
                               # hinting `maverick reconcile`
maverick reconcile
maverick land --dry-run        # expect: conditionally-verified again
cat .maverick/runs/<latest>/land-report.md
```

Checks (against `contracts/land-report-schema.md`): the reconciled entry's
`affected_change_ids` includes both the original stamp and the reconcile
correction change id; the waived row carries who/when/why; buckets and
totals match; `--finalize` hint references `--body-file …/land-report.md`.

## Scenario 3 — bulk waive (US1/FR-016)

Seed several low-severity entries under one spec, then:

```bash
maverick review --spec <spec-name> --waive "noise accepted this slice"
maverick review --spec <spec-name> --waive "again"   # expect: nothing to waive, exit 0
maverick brief                                       # waived counts moved
```

Checks: each entry individually carries the shared reason + waiver metadata;
medium/high entries were untouched (default severity filter is low).

## Scenario 4 — mid-flight answering (US3)

Needs a run long enough to intervene in (2+ beads, e.g. the sample project):

```bash
maverick fly &                                   # or a second terminal
# while a later bead is implementing:
maverick review <earlier-entry-id> --answer "changed answer"
```

Expected: at the next bead boundary the progress stream shows a reconcile
pass (detected=1); the drain loop keeps implementing subsequent beads; after
the run, `bd show <entry-id>` shows `assumption_reconcile_status=reconciled`
and `maverick land --dry-run` does not list the entry. With
`reconcile.mid_flight: false` in `maverick.yaml`, the same sequence performs
no mid-flight pass and `maverick reconcile` afterwards picks the answer up.

Failure-path check (unit-level, `test_mid_flight.py`): a pass raising
`WorkflowError` yields a warning event and the loop continues; graceful-stop
skips the pass and leaves the answer detectable.

## Expected outcomes summary

- SC-001: land never proceeds with an open entry (any severity) — Scenarios 1, 3.
- SC-002/SC-003: report completeness + PR-body availability — Scenario 2.
- SC-004/SC-005: answers reconciled before run completion, zero extra
  commands, no drain stall — Scenario 4.
- SC-006: exactly-once application — Scenario 4 then `maverick reconcile`
  (reports nothing to do).
