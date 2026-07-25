# Data Model: Conditional Landing on the Assumption Frontier

All new types are frozen dataclasses or StrEnums following the existing
`assumptions/models.py` idiom. bd remains the source of truth — nothing below
introduces new bd state keys; the new types are read-side materializations
plus one persisted artifact.

## Existing model (unchanged, for reference)

- `AssumptionRecord` (`assumptions/models.py:138`) — bead_id, question,
  adopted_answer, alternatives, severity, severity_defaulted, status,
  owner_spec, source_bead, change_ids, is_legacy. Does **not** carry answer /
  waiver / reconcile state (those are bd state keys only).
- bd state keys — `KEY_ANSWER`, `KEY_WAIVED_BY/AT/REASON`,
  `KEY_RECONCILE_STATUS`, `KEY_RECONCILED_AT`, `KEY_RECONCILED_ANSWER`,
  `KEY_RECONCILE_CHANGE_ID`, `KEY_RECONCILE_REASON`, `KEY_CHANGE_IDS`.
- Status vocabularies — `STATUS_OPEN/ANSWERED/WAIVED`;
  `RECONCILE_STATUS_RECONCILED/NEEDS_REVIEW/PENDING`,
  `TERMINAL_RECONCILE_STATUSES`.

## New: `AssumptionReportEntry` (assumptions/models.py)

Frozen, slots. The full read-side view of one ledger entry — everything the
report and frontier need in one place.

| Field | Type | Source |
|---|---|---|
| `record` | `AssumptionRecord` | existing readers (`_record_from_details` / `_legacy_record_from_details`) |
| `final_answer` | `str \| None` | `KEY_ANSWER` |
| `waived_by` | `str \| None` | `KEY_WAIVED_BY` |
| `waived_at` | `str \| None` | `KEY_WAIVED_AT` (ISO-8601) |
| `waive_reason` | `str \| None` | `KEY_WAIVED_REASON` |
| `reconcile_status` | `str \| None` | `KEY_RECONCILE_STATUS` |
| `reconciled_answer` | `str \| None` | `KEY_RECONCILED_ANSWER` |
| `reconcile_change_id` | `str \| None` | `KEY_RECONCILE_CHANGE_ID` |
| `reconcile_reason` | `str \| None` | `KEY_RECONCILE_REASON` |
| `pending_reconcile` | `bool` | computed: entry appears in `answered_unreconciled_entries()` |

Derived properties:

- `bucket` → `"resolved" | "waived" | "open"`:
  `STATUS_WAIVED` → waived; `STATUS_ANSWERED` → resolved; else open.
  (Legacy open entries → open.)
- `affected_change_ids` → `record.change_ids` + `reconcile_change_id`
  (when set), deduplicated, order-preserving.
- `blocks_landing` → `bucket == "open" or pending_reconcile` (any severity —
  strict gate per Clarifications 2026-07-24).

Validation: constructed only by `ledger.report_entries()`; no user input.

## New: `LandVerification` (assumptions/models.py)

```
class LandVerification(StrEnum):
    VERIFIED = "verified"
    CONDITIONALLY_VERIFIED = "conditionally-verified"
    BLOCKED = "blocked"
```

Classification function (pure, `land_report.py`):

```
any(e.blocks_landing for e in entries)        -> BLOCKED
elif any(e.bucket == "waived" for e in entries) -> CONDITIONALLY_VERIFIED
else                                           -> VERIFIED   # incl. zero entries
```

### State transitions (entry-level, driving the classification)

```
open ──answer()──► answered ──(answer changes)──► pending_reconcile
  │                   │                                │
  │                   │                        reconcile: success
  │                   │                                ├──► reconciled (terminal, resolved)
  │                   │                        reconcile: exhausted/immutable
  │                   │                                └──► needs-interactive-review /
  │                   │                                     skipped (terminal, resolved*,
  │                   │                                     annotated in report)
  └──waive()──► waived (blocks nothing; forces CONDITIONALLY_VERIFIED)

re-answer via `maverick review` clears terminal reconcile state → pending again
(existing 051 FR-017 behavior, unchanged)
```

`resolved*`: terminal-marked entries count as resolved for gating (FR-006)
but their rows carry the terminal annotation.

## New: `LandFrontier` (assumptions/models.py)

Frozen, slots. The gate's decision input.

| Field | Type | Notes |
|---|---|---|
| `open_entries` | `tuple[AssumptionReportEntry, ...]` | any severity, incl. legacy |
| `pending_reconcile_entries` | `tuple[AssumptionReportEntry, ...]` | 051 predicate matches |
| `is_empty` | property | both tuples empty ⇒ land may proceed |

## New: `LandReport` (assumptions/land_report.py)

Frozen, slots, with `to_dict()` (stable public contract — see
`contracts/land-report-schema.md`).

| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | 8-hex, minted per land evaluation |
| `created_at` | `str` | ISO-8601 UTC |
| `verification` | `LandVerification` | |
| `dry_run` | `bool` | |
| `specs` | `tuple[SpecReportSection, ...]` | grouped by `owner_spec`, sorted |

`SpecReportSection`: `owner_spec: str`, `entries:
tuple[AssumptionReportEntry, ...]` (each serialized with bucket, provenance
fields, affected_change_ids, annotations), plus per-bucket counts.

Persistence: `.maverick/runs/<run_id>/land-report.json` (atomic) and
`land-report.md` (markdown rendering of the same data). Write failures
degrade to a warning.

## New: `MidFlightOutcome` (workflows/fly_beads/mid_flight.py)

Frozen, slots — the Burr action's typed result (also logged as an event).

| Field | Type | Notes |
|---|---|---|
| `detected` | `int` | answers matching detection at this boundary |
| `processed` | `int` | reconciled successfully this pass |
| `escalated` | `int` | terminal-marked / triage-bead outcomes |
| `skipped_reason` | `str \| None` | `"disabled"`, `"graceful-stop"`, `"none-detected"`, or None when a pass ran |
| `error` | `str \| None` | non-None when the pass failed as a whole (drain continued) |

## Changed: `ReconcileConfig` (config.py)

`+ mid_flight: bool = True` — kill-switch for the mid-flight trigger
(`maverick.yaml` → `reconcile.mid_flight`). No other fields change; round
budgets are inherited by mid-flight passes unchanged.

## Changed: `ReconcileWorkflow` inputs (workflows/reconcile/workflow.py)

`inputs` gains optional `active_fly_run_id: str | None`. When set,
`_find_flying_run(cwd, exclude_run_id=active_fly_run_id)` ignores that run's
`"flying"` metadata. All other guards (clean working copy, lockfile,
interrupted-run recovery) unchanged.

## Relationships

```
bd beads (ledger entries) ──report_entries()──► AssumptionReportEntry*
AssumptionReportEntry* ──frontier()──► LandFrontier ──► gate decision
AssumptionReportEntry* ──classify()──► LandVerification
AssumptionReportEntry* + LandVerification ──build_report()──► LandReport
LandReport ──persist()──► .maverick/runs/<id>/land-report.{json,md}
answered_unreconciled_entries() ──(fly boundary)──► ReconcileWorkflow(active_fly_run_id)
                                                        └──► MidFlightOutcome
```
