# Quickstart: validating the assumption batch scheduler

Runnable scenarios proving the feature end-to-end. Schemas and shapes live in
[data-model.md](data-model.md) and [contracts/](contracts/) — this guide only
runs them.

## Prerequisites

- `uv sync` completed; `bd` on PATH; repo initialized (`maverick init` /
  `bd init` done — `.beads/` exists).
- An ntfy topic you can watch: open `https://ntfy.sh/<your-topic>` in a
  browser tab (or the ntfy app).

## Setup

Add to `maverick.yaml`:

```yaml
notifications:
  enabled: true
  topic: <your-topic>

assumptions:
  schedule:
    windows: ["09:00", "17:00"]
    quiet_hours: {start: "22:00", end: "07:00"}
    min_batch_size: 1
```

Seed at least one open assumption entry (any spec's fly run records them; for
a synthetic one, create a bead carrying the `assumption` label and the ledger
state keys — see `tests/integration/test_notify_flow.py` for the exact shape).

## Scenario 1 — unconfigured no-op (FR-021)

With the `assumptions.schedule` block **removed**:

```bash
maverick notify --json
```

Expect: exit 0, `ok: true`, `result.configured: false`,
`result.skipped: "not-configured"`, no state file created.

## Scenario 2 — dry run shows every decision (SC-004)

With config restored:

```bash
maverick notify --dry-run --json | python3 -m json.tool
```

Expect: exit 0; every open entry appears in `deliveries` (as *would deliver*),
`skips` (with a `reason` + `rule`), or `auto_waives`; `.maverick/notify/`
untouched; zero pushes received.

## Scenario 3 — window batch delivery + idempotence (US1, US3)

Run after a configured window time has passed (or set a `windows` value a
minute in the future and wait):

```bash
maverick notify --json   # 1st: delivers
maverick notify --json   # 2nd: skips
```

Expect: exactly **one** push on your topic — counts by severity, owning specs,
oldest age, and a runnable `maverick review` line; no entry contents. Second
run exits 0 with `skips: [{"reason": "already-delivered", ...}]` and no push.
Verify the audit trail:

```bash
python3 -m json.tool .maverick/notify/state.json
```

Expect: a `window_decisions` key `"<today>/<window>"` with
`outcome: "delivered"`, a matching `deliveries` record, and `rule` strings
explaining each decision.

## Scenario 4 — high-severity interrupt (US2)

Record a high-severity entry (or edit a seeded bead's severity state key to
`high`), then run `maverick notify` outside any window. Expect: an `urgent`
push immediately, `entry_tracking.<id>.interrupt_delivered_at` set, and no
second push on re-run. During quiet hours, expect delivery iff
`high_overrides_quiet` is true.

## Scenario 5 — delivery failure stays due (FR-012)

Point `notifications.server` at an unreachable address, run `maverick notify
--json` with a due batch. Expect: exit 1, `error.kind: "delivery-failed"`,
state file unchanged for that decision. Restore the server, re-run: the same
batch delivers.

## Scenario 6 — concurrent runs (FR-013)

```bash
maverick notify --json & maverick notify --json; wait
```

Expect: one run evaluates; the other exits 0 with
`result.skipped: "concurrent-evaluation"`; at most one push.

## Automated validation

```bash
make test-fast    # unit: evaluation (windows/quiet/DST/escalation), state, deliverer, CLI envelope
make test         # + integration: end-to-end notify flow with mocked bd + MockTransport ntfy
make ci           # pre-push gate
```

Time-dependent behavior needs no waiting in tests: `evaluate()` takes `now`
directly, and integration tests inject fixed local datetimes (including DST
boundary dates) — see `tests/unit/assumptions/schedule/`.
