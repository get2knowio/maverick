# Research: Assumption Batch Scheduler

All Technical Context unknowns resolved. Each decision below was verified
against the codebase (file references) or by direct probe.

## R1 — Entry age basis: bd `created_at`, verified by probe

**Decision**: Compute entry age from bd's own `created_at` timestamp. Add
`created_at: str | None = None` to `BeadDetails` (`src/maverick/beads/models.py`),
thread it through `AssumptionRecord` / `AssumptionReportEntry`
(`src/maverick/assumptions/models.py`) and `entry_to_dict`
(`src/maverick/assumptions/serialize.py`).

**Rationale**: A live probe (`bd create` + `bd show --json` in a throwaway
repo) confirmed bd emits `"created_at": "2026-08-05T22:09:49Z"` (UTC ISO-8601)
on both `list` and `show`. `BeadDetails` is a Pydantic model that currently
ignores extras, so the field is being dropped today — adding it is a one-line,
backward-compatible change. Using bd's timestamp makes age deterministic from
the ledger itself (SC-004: reconstructible from ledger + config + state) and
means age starts at recording time, not at first scheduler sighting.

**Fallback**: An entry whose `created_at` is missing (malformed bead) falls
back to the scheduler's persisted `first_seen` timestamp for that entry
(recorded on first evaluation). It is never dropped from evaluation (FR-016).

**Alternatives considered**: (a) Scheduler-side first-seen only — simpler, but
age would start at first evaluation rather than recording, understating age for
entries recorded while cron was down; kept only as fallback. (b) Parsing jj/git
history for recording time — violates Guardrail 8's spirit (re-deriving what a
structured artifact already carries).

## R2 — Command surface: `maverick notify [--dry-run] [--json]`

**Decision**: New top-level command `maverick notify`; JSON verbs `notify.run`
and `notify.dry-run` (mirroring `reconcile.run` / `reconcile.dry-run`).
Registered via `_LAZY_COMMANDS` in `src/maverick/main.py`; implemented in
`src/maverick/cli/commands/notify.py` with `@async_command`.

**Rationale**: The spec deferred naming to planning. `notify` states exactly
what the command does (evaluate + deliver anything due) and collides with
nothing (`review`, `brief`, `reconcile`, `land` taken). `--dry-run` evaluates
and reports every decision with zero deliveries, zero state writes, and zero
bd writes — same convention as `reconcile --dry-run`.

**Alternatives considered**: `maverick schedule` (reads as *configuring* a
schedule, not evaluating one); `maverick assumptions deliver` (no existing
command-group precedent; every surface is a flat top-level command);
`maverick brief --deliver` (overloads a read-only reporting command with
side effects).

## R3 — Config surface: new `assumptions.schedule` block + existing `notifications` block

**Decision**: Add `AssumptionsConfig(BaseModel)` with field
`schedule: AssumptionScheduleConfig | None = None`, wired as
`MaverickConfig.assumptions` (`src/maverick/config.py`). The ntfy endpoint
comes from the **existing** `NotificationConfig` (`notifications:` block:
`enabled`, `server` (default `https://ntfy.sh`), `topic`) — already present at
`config.py:59` and currently unused by any delivery code.

Schedule fields (full schema in `contracts/config-schema.md`):
`windows: list[str]` (HH:MM local, ≥1 required), `quiet_hours: {start, end} | None`,
`high_overrides_quiet: bool = True`, `min_batch_size: int = 1 (ge=1)`,
`max_entry_age_hours: int = 24 (ge=1)`,
`renotify_backoff_hours: list[float] = [4, 8, 16, 24]` (last value repeats),
`auto_waive_low: {enabled: bool = False, after_hours: int, rationale: str} | None`.

**Rationale**: The spec mandates "an assumptions schedule block"; reusing
`NotificationConfig` for the endpoint avoids a second ntfy config surface
(Principle VII — no duplication). Numeric defaults were the one item clarify
deferred to planning; values chosen: `min_batch_size=1` (no surprise skipping
unless opted into), `max_entry_age_hours=24` (one full day before the batching
rules are overridden), backoff `4→8→16→24h` (bounded, roughly-daily steady
state — "spaced increasingly far apart" per FR-007).

**Validation semantics (FR-009/FR-021)**: `schedule` absent → command is inert
(exit 0, "not configured"). `schedule` present but `notifications.enabled` is
false or `topic` unset → actionable `validation` error (the existing
`NotificationConfig` validator only warns; the notify command enforces).
Malformed schedule values (bad HH:MM, empty windows) → Pydantic
`ValidationError` at config load, consistent with every other block.

**Alternatives considered**: ntfy settings nested inside the schedule block —
rejected as duplicate surface; a built-in default schedule — rejected by
clarification Q1 (strictly opt-in).

## R4 — Delivery state: `.maverick/notify/state.json` + pid lockfile, mirroring reconcile

**Decision**: Persist all delivery state in one file,
`<cwd>/.maverick/notify/state.json`: frozen Pydantic models with
`schema_version: 1`, written via `asyncio.to_thread(atomic_write_json, ...)`
(`src/maverick/utils/atomic.py`). Concurrency guard is a pid-stamped advisory
lockfile `<cwd>/.maverick/notify/lock` with stale-lock reclaim, copied from the
house pattern in `src/maverick/workflows/reconcile/state.py`
(`acquire_lock`/`release_lock`/`_pid_is_alive`).

**Rationale**: Delivery state is *cross-run* (idempotence spans invocations),
so `.maverick/runs/<run-id>/` is the wrong home — a stable feature directory
matches `.maverick/runway/`'s precedent. One file keeps load/evaluate/save
atomic and trivially auditable; the reconcile state module is the proven
implementation of exactly this shape (no `fcntl`/`filelock` exists anywhere in
the codebase — the pid-file pattern is the house answer to FR-013).

**Retention (FR-023)**: pruning runs at the end of each successful evaluation:
delivery records and entry-tracking rows are removed only when every covered
entry is terminal (answered/waived/closed) *and* 90 days have elapsed since the
latest terminal transition the scheduler observed. Never prunes records
covering open entries.

**Alternatives considered**: JSONL append-only log (`runway/store.py` shape) —
better for unbounded audit but splits idempotence state from audit records and
needs compaction anyway once FR-023 pruning applies; SQLite — over-engineered
for tens of records and a new storage dependency (Principle VII).

## R5 — ntfy delivery: httpx + tenacity, one canonical wrapper

**Decision**: `assumptions/schedule/deliver.py` owns all ntfy I/O:
`httpx.AsyncClient` POST to `{server}/{topic}`, 10-second explicit timeout,
`tenacity.AsyncRetrying` (3 attempts, `wait_exponential`, retrying on
`httpx.TransportError` and 5xx). Payload contract in
`contracts/ntfy-payload.md`: `Title`/`Priority`/`Tags` headers + plain-text
summons body; priority `urgent` for high-severity interrupts and escalations,
`default` for window batches.

**Rationale**: `httpx` is already a declared dependency (currently unused —
this is its first consumer; verified no HTTP client pattern exists in `src/` to
conflict with). tenacity is constitutionally mandated for retries (Appendix B).
Guardrail 5: this module is the single canonical ntfy wrapper; no other module
may construct ntfy requests. Note: the old unimplemented spec 006 proposed
aiohttp with degrade-to-success semantics — deliberately **not** followed here,
because FR-012 requires failures to be loud and to leave the batch due.

**Alternatives considered**: aiohttp (also a dep) — httpx has the cleaner
async API and sync test transport (`httpx.MockTransport`) for unit tests;
shelling out to `curl` — violates async-first and canonical-wrapper rules.

## R6 — Pure evaluation with an injected clock (first clock seam in the codebase)

**Decision**: `evaluate.py` exposes a pure function:
`evaluate(entries, schedule, state, now) -> EvaluationOutcome` where `now` is a
timezone-aware **local** datetime supplied by the CLI boundary
(`datetime.now().astimezone()`). The outcome enumerates every decision —
deliveries due (interrupt / window batch / escalation), skips
(`min-batch-size`, `quiet-hours`, `already-delivered`, `not-yet-due`,
`low-never-proactive`), and the state mutations to apply — each tagged with the
rule that decided it (feeds SC-004 auditability and the `--json` result).
Effects (ntfy, bd auto-waive, state save) happen in the command layer strictly
after evaluation.

**Rationale**: The codebase has no clock abstraction (verified: zero hits for
injected clocks; tests patch `datetime.now` per module). Windows/quiet-hours/
DST/backoff logic is untestable without a seam, and an explicit `now` parameter
is the smallest one (Principle III), avoiding a freezegun-style test
dependency.

**Window occurrence semantics (FR-020)**: each configured window time yields at
most one *occurrence* per local calendar date, keyed `(date, "HH:MM")`. An
occurrence is **due** when `now` ≥ its wall-clock datetime (quiet-hours-shifted
if applicable) and no decision for that key exists in state. Windows are
deadlines-to-deliver-after, not instants: a machine asleep at 09:00 delivers at
the next evaluation. DST spring-forward (nonexistent wall time) resolves to the
first valid instant after the gap via fold-aware `zoneinfo` arithmetic;
fall-back (repeated hour) cannot double-deliver because the occurrence key is
date-based, not instant-based.

**Alternatives considered**: a `Clock` protocol class — more surface than
needed for one consumer; module-level `datetime.now()` with test patching —
the exact untestable pattern this feature cannot afford.

## R7 — Concurrency: lock contention is a benign skip (exit 0), unlike reconcile

**Decision**: When `acquire_lock` fails against a live holder, `maverick
notify` exits `SUCCESS` — human mode prints a single notice; JSON mode emits
`ok: true` with `result.skipped: "concurrent-evaluation"` and no decisions.
FR-013 is satisfied because the losing invocation performs no evaluation at
all.

**Rationale**: Overlapping cron fires are *expected operation* for this
command, not a fault — a non-zero exit would page people from cron mail for
normal behavior. This deliberately diverges from `reconcile --json`, which maps
a held lock to error kind `locked` (there, a second invocation is a human
mistake). The divergence is documented in `contracts/cli-notify-json.md`.

**Alternatives considered**: reuse `locked` error semantics — wrong ergonomics
for a cron-first command; lock-free last-writer-wins state — cannot guarantee
FR-013's at-most-once delivery.

## R8 — Quiet hours interaction: quiet wins, occurrences shift, policy gates high

**Decision**: A window occurrence falling inside quiet hours shifts its due
time to quiet-hours end (same occurrence key — still one decision, no double
delivery). High-severity interrupts and escalation re-notifications are gated
by `high_overrides_quiet`: `true` (default) delivers during quiet hours;
`false` holds them until the first evaluation after quiet end. Quiet ranges may
span midnight (`22:00–07:00`); containment is computed on local wall-clock
time.

**Rationale**: Directly implements clarified US1/US2 acceptance scenarios and
the "window inside quiet hours" edge case with a single mechanism (due-time
shifting) instead of special cases.

## R9 — Severity tiers, legacy entries, and stale-batch exclusion

**Decision**: Delivery tiers per FR-002: high → interrupt at next permissible
evaluation; medium → window batches; low → never proactive but counted in
batch summaries (clarification Q5). Legacy entries (bd-open
`assumption-review`/`needs-human-review` beads without the `assumption` label)
already surface from `report_entries` with synthesized `severity=MEDIUM`,
`severity_defaulted=True`, `is_legacy=True` — FR-019 requires **no new
mapping code**, only a test pinning the behavior. Resolution-between-
accumulation-and-delivery (FR-014) is structural: the batch is computed from
open entries re-read at evaluation time, so resolved entries can never appear;
an occurrence whose batch is empty records a decision with zero deliveries.

## R10 — Auto-waive rides the existing ledger mutation path

**Decision**: Opt-in auto-waive (FR-015) calls the existing
`assumptions.ledger.waive(client, bead_id=..., reason=..., waived_by="maverick-scheduler")`
with reason
`"auto-waived by schedule policy after {after_hours}h: {configured rationale}"`.
No ledger schema change: `waived_by` is free-form, flows through
`entry_to_dict`'s `waiver` object into `review --list` and the land report, so
auto-waived entries are already distinguishable (the land gate's
conditionally-verified classification applies unchanged). Auto-waive executes
in the effects phase, after evaluation, and is recorded in delivery state as a
terminal outcome (FR-016); `--dry-run` reports would-waive decisions without
touching bd.

**Alternatives considered**: a dedicated `assumption_auto_waived` state key —
more ledger surface for information `waived_by` already carries.

## R11 — JSON envelope: one additive error kind, `delivery-failed`

**Decision**: Add `ErrorKind.DELIVERY_FAILED = "delivery-failed"` to
`src/maverick/cli/json_output.py` (registry is additive-only by contract) for
exhausted ntfy delivery retries. Mapping: unconfigured schedule → `ok: true`
no-op (FR-021, *not* an error); schedule present but notifications
disabled/topic missing → `validation`; bd unavailable → `bd-unavailable`
(translated explicitly — `BeadClient.verify_available()` returns `False`, it
does not raise); ledger read failure → `validation` via existing
`AssumptionLedgerError` mapping; delivery exhausted → `delivery-failed`, exit
`FAILURE`, batch remains due.

## R12 — Evaluation cost at cron frequency: acceptable, with a cheap guard

**Decision**: Accept `report_entries()`'s cost profile (1 `bd query` + 2
subprocesses per candidate bead) at recommended cron frequencies (1–5 min).
Add one cheap guard: when the schedule yields no due-or-potentially-due work
(inside quiet hours with `high_overrides_quiet=false` and no undecided past
occurrence), the command exits before touching bd at all.

**Rationale**: Realistic ledgers are tens of beads; ~2N subprocesses every few
minutes is noise. Caching ledger reads in delivery state would create a second
source of truth and violate the reconstructibility story (SC-004) for marginal
savings. Re-evaluate only if field usage shows multi-hundred-entry ledgers.
