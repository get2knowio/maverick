# Quickstart: Validating the Assumption Ledger

Runnable scenarios proving the feature end-to-end. Shapes and semantics:
[data-model.md](data-model.md), [contracts/](contracts/).

## Prerequisites

- Repo initialized: `maverick init` (jj colocated + bd store present).
- A speckit feature ingested: `maverick refuel <feature> --speckit` so an epic
  with `speckit_feature` state exists.
- For agent-path scenarios: OpenCode auth configured. Deterministic scenarios
  (2–6) need no model access.

## Fast checks (no model calls)

```bash
make test-fast          # unit tests incl. maverick.assumptions, payloads
make lint typecheck     # ruff + mypy strict
```

New test areas: `tests/unit/assumptions/` (ledger, report, severity coercion,
dedup), `tests/unit/workflows/fly_beads/` (record_assumptions, commit
stamping), `tests/unit/cli/` (land gate, review answer/waive, brief section),
`tests/unit/workflows/refuel_speckit/` (`_chain_epic` wiring), and
`tests/integration/test_assumption_ledger_flow.py`.

## Scenario 1 — Record + stamp (US1)

1. Run `maverick fly --epic <id>` on a bead whose prompt/fixture yields an
   implementation payload containing one `assumptions` entry (integration
   tests stub the agent; live runs rely on the updated prompts).
2. After the bead commits, verify the entry:

   ```bash
   bd list --parent <epic-id> --flat --json | jq '.[] | select(.title | startswith("Assumption:"))'
   bd show <assumption-id> --json
   ```

   Expect: labels include `assumption`; state has `assumption_severity`,
   `assumption_status=open`, `assumption_owner_spec=<feature-dir-name>`,
   `assumption_change_ids` containing a jj change ID that
   `jj log -r <change-id>` resolves; `bd dep list <assumption-id> --json`
   shows a `discovered-from` edge to the source bead (US1-S1/S2/S3).
3. Kill a run before commit (or use the abandon path in tests): entry exists
   with no `assumption_change_ids` — unstamped (US1-S4).

## Scenario 2 — Severity policy: low is advisory (US2-S1)

Create a low-severity entry (unit/CLI fixture or a stubbed run), then:

```bash
bd ready --json            # entry absent (deferred)
maverick land --dry-run    # gate passes; entry listed nowhere as blocking
maverick brief             # entry counted under its spec (open, L column)
```

## Scenario 3 — Medium blocks land until answered/waived (US2-S2, US2-S4)

1. With one open medium entry: `maverick land` → exits non-zero, table names
   the entry + owning spec + `maverick review <id>` hint. Confirm no bypass
   flag exists: `maverick land --help` offers none.
2. `maverick review <id>` → answer flow → `bd show` shows
   `assumption_status=answered`, bead closed.
3. `maverick land --dry-run` → gate passes.
4. Repeat with a second entry using the waive flow (reason required); state
   records `assumption_waived_by/at/reason` (US2-S4).

## Scenario 4 — High blocks the next spec's epic (US2-S3, FR-007)

1. Spec A epic exists with an open high entry; refuel spec B
   (`maverick refuel <spec-b> --speckit`).
2. `bd dep list <spec-b-epic> --json` → `blocks` edge from the assumption
   entry (wired at chain time or recording time, whichever came second).
3. `bd ready --json` → no spec-B beads appear.
4. Resolve the entry via `maverick review` → spec-B work appears in
   `bd ready` with no manual dependency surgery (SC-006, edge-case
   "answered mid-run").
5. High entry on the **last** spec (no spec B): behaves as Scenario 3 only
   (US2-S5).

## Scenario 5 — Human queue (US3)

```bash
bd ready --json                 # medium/high entries appear, assignee=human
maverick brief --human          # entries listed with source-bead context
maverick review <id>            # full context: question/answer/alternatives/
                                # severity/spec/stamps/discovered-from
```

Agent-side check: `select_next_bead` still skips these beads (existing unit
tests must stay green).

## Scenario 6 — Per-spec counts incl. zero (US4)

With spec A (entries) and spec B (none) both refueled:

```bash
maverick brief                  # Assumptions table: A with counts, B all-zero
maverick brief --format json    # assumption_counts array, both specs present
```

Legacy escalation beads (pre-feature `assumption-review` beads without the
`assumption` label) appear in the `Legacy` column and cause no errors
(FR-013).

## Full gate before push

```bash
make ci
```
