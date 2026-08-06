# Data Model: Assumption Batch Scheduler

Three model families: **config** (Pydantic, `maverick.config`), **evaluation**
(frozen dataclasses, in-memory only, `assumptions/schedule/models.py`), and
**persisted state** (frozen Pydantic, `assumptions/schedule/state.py`). Plus
one additive change to existing ledger models.

## 1. Existing-model extensions

### `BeadDetails` (`src/maverick/beads/models.py`) — MODIFIED

| Field | Type | Notes |
|---|---|---|
| `created_at` | `str \| None = None` | bd's UTC ISO-8601 creation timestamp (probe-verified `"2026-08-05T22:09:49Z"`); currently dropped by the extras-ignoring model |

### `AssumptionRecord` / `AssumptionReportEntry` (`src/maverick/assumptions/models.py`) — MODIFIED

- `AssumptionRecord.created_at: str | None` — copied from `BeadDetails` in
  `ledger._record_from_details` / `_legacy_record_from_details`.
- `AssumptionReportEntry` exposes it via its `record`; `entry_to_dict`
  (`serialize.py`) adds `created_at` to the canonical row (additive — shared by
  `review --list` and the land report by design; both surfaces gain the field
  simultaneously).

## 2. Configuration models (`src/maverick/config.py`)

### `AssumptionsConfig`

| Field | Type | Default | Constraint |
|---|---|---|---|
| `schedule` | `AssumptionScheduleConfig \| None` | `None` | `None` ⇒ scheduler inert (FR-021) |

Wired as `MaverickConfig.assumptions` (`Field(default_factory=AssumptionsConfig)`).

### `AssumptionScheduleConfig`

| Field | Type | Default | Constraint / meaning |
|---|---|---|---|
| `windows` | `list[str]` | — (required) | ≥1 entry; each `HH:MM` 24-hour local time; validator parses to `time` and rejects duplicates |
| `quiet_hours` | `QuietHoursConfig \| None` | `None` | absent ⇒ no quiet hours |
| `high_overrides_quiet` | `bool` | `True` | FR-004 policy switch |
| `min_batch_size` | `int` | `1` | `ge=1`; FR-005 |
| `max_entry_age_hours` | `int` | `24` | `ge=1`; FR-006 escalation threshold |
| `renotify_backoff_hours` | `list[float]` | `[4, 8, 16, 24]` | non-empty, each `> 0`, non-decreasing; last value repeats indefinitely (FR-007) |
| `auto_waive_low` | `AutoWaivePolicyConfig \| None` | `None` | absent ⇒ never auto-waive (FR-015) |

### `QuietHoursConfig`

| Field | Type | Constraint |
|---|---|---|
| `start` | `str` | `HH:MM` local |
| `end` | `str` | `HH:MM` local; may be < `start` (range spans midnight); `start == end` rejected |

### `AutoWaivePolicyConfig`

| Field | Type | Default | Constraint |
|---|---|---|---|
| `enabled` | `bool` | `False` | explicit opt-in |
| `after_hours` | `int` | `168` (7 days) | `ge=1` |
| `rationale` | `str` | — (required when `enabled`) | recorded on the ledger entry |

**Endpoint config**: existing `NotificationConfig` (`notifications:` block —
`enabled`, `server`, `topic`) is reused unchanged. Enforcement of
"schedule present ⇒ notifications usable" happens in the notify command
(actionable `validation` error), not in the config validator (which only
warns, preserving existing behavior for other consumers).

## 3. Evaluation models (frozen dataclasses, never persisted)

### `WindowOccurrence`

| Field | Type | Notes |
|---|---|---|
| `date` | `date` | local calendar date |
| `window` | `str` | `"HH:MM"` as configured |
| `due_at` | `datetime` | aware local; quiet-hours-shifted when applicable (R8); DST-fold-aware (R6) |

Identity key: `(date, window)` — at most one decision per occurrence, ever.

### `DeliveryDecision`

| Field | Type | Notes |
|---|---|---|
| `kind` | `DecisionKind` | `WINDOW_BATCH \| INTERRUPT \| ESCALATION \| RENOTIFY` |
| `entry_ids` | `tuple[str, ...]` | covered bead ids (open at evaluation time — FR-014 structural) |
| `summary` | `BatchSummary` | counts by severity (incl. low), owning specs, oldest-entry age |
| `occurrence` | `WindowOccurrence \| None` | set for `WINDOW_BATCH` only |
| `rule` | `str` | human-readable rule citation for audit (e.g. `"window 09:00 due"`) |

### `SkipDecision`

| Field | Type | Notes |
|---|---|---|
| `reason` | `SkipReason` | `MIN_BATCH_SIZE \| QUIET_HOURS \| ALREADY_DELIVERED \| NOT_YET_DUE \| LOW_NEVER_PROACTIVE \| EMPTY_BATCH` |
| `occurrence` | `WindowOccurrence \| None` | when window-scoped |
| `entry_ids` | `tuple[str, ...]` | affected entries |
| `rule` | `str` | audit citation |

### `AutoWaiveDecision`

| Field | Type |
|---|---|
| `entry_id` | `str` |
| `reason_text` | `str` (full recorded rationale) |

### `BatchSummary`

| Field | Type | Notes |
|---|---|---|
| `counts` | `dict[Severity, int]` | includes `LOW` as informational (clarification Q5) |
| `owner_specs` | `tuple[str, ...]` | sorted |
| `oldest_age_hours` | `float` | from `created_at` basis (R1) |
| `review_invocation` | `str` | e.g. `"maverick review --list --status open"` |

### `EvaluationOutcome`

| Field | Type |
|---|---|
| `deliveries` | `tuple[DeliveryDecision, ...]` |
| `skips` | `tuple[SkipDecision, ...]` |
| `auto_waives` | `tuple[AutoWaiveDecision, ...]` |
| `state_after` | `DeliveryState` — the candidate state assuming every decision's effect succeeds; the effects layer removes each failed decision's mutations before saving (per-decision write-after-success, contracts/delivery-state-schema.md invariant 2) |

## 4. Persisted state (`.maverick/notify/state.json`)

Top-level `DeliveryState` (frozen Pydantic):

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `int = 1` | |
| `updated_at` | `str` | UTC ISO-8601 |
| `window_decisions` | `dict[str, WindowDecisionRecord]` | key `"YYYY-MM-DD/HH:MM"` — the idempotence ledger for occurrences (FR-010) |
| `entry_tracking` | `dict[str, EntryTrackingRecord]` | key = bead id |
| `deliveries` | `list[DeliveryRecord]` | append-only audit trail (FR-011) |

### `WindowDecisionRecord`

| Field | Type | Notes |
|---|---|---|
| `outcome` | `str` | `"delivered" \| "skipped-min-batch" \| "empty"` |
| `decided_at` | `str` | UTC ISO-8601 |
| `entry_ids` | `list[str]` | |
| `rule` | `str` | audit citation |

### `EntryTrackingRecord`

| Field | Type | Notes |
|---|---|---|
| `first_seen` | `str` | fallback age basis (R1) |
| `severity` | `str` | as evaluated (legacy ⇒ `"medium"`) |
| `interrupt_delivered_at` | `str \| None` | high-tier first delivery (FR-002) |
| `escalation_delivered_at` | `str \| None` | max-age escalation delivery (FR-006) |
| `renotify_count` | `int = 0` | index into backoff ladder (FR-007) |
| `next_renotify_at` | `str \| None` | precomputed next backoff instant |
| `terminal` | `TerminalOutcome \| None` | set when scheduler observes/creates terminal state (FR-016) |

### `TerminalOutcome`

| Field | Type | Notes |
|---|---|---|
| `kind` | `str` | `"resolved-by-human" \| "auto-waived"` |
| `at` | `str` | UTC ISO-8601 — starts the FR-023 90-day retention clock |
| `detail` | `str \| None` | auto-waive rationale |

### `DeliveryRecord`

| Field | Type | Notes |
|---|---|---|
| `kind` | `str` | `"window-batch" \| "interrupt" \| "escalation" \| "renotify"` |
| `delivered_at` | `str` | UTC ISO-8601 (only written after ntfy success — FR-012) |
| `trigger` | `str` | occurrence key or rule citation |
| `entry_ids` | `list[str]` | |
| `summary` | `dict` | serialized `BatchSummary` |

### State transitions (per entry)

```
(untracked) ──first evaluation──► tracked{first_seen}
tracked ──high tier, permissible──► interrupt_delivered_at set
tracked ──age > max_entry_age (med/high)──► escalation_delivered_at set
escalated(high) ──backoff elapses──► renotify_count += 1, next_renotify_at advanced
escalated(medium) ──(no further deliveries)
tracked ──human answers/waives (observed)──► terminal{resolved-by-human}
tracked(low) ──auto-waive policy fires──► terminal{auto-waived} (+ bd waive)
terminal + 90 days, all covered records terminal──► pruned (FR-023)
```

**Write discipline**: state is saved once per run via
`atomic_write_json`, only after effects complete; a delivery that failed is
excluded from `state_after` before saving (its occurrence stays undecided /
its tracking timestamps stay unset), so failed deliveries remain due (FR-012).

### Lockfile

`<cwd>/.maverick/notify/lock` — pid-stamped advisory lock with stale-pid
reclaim, byte-for-byte the pattern of `workflows/reconcile/state.py`.
Contention ⇒ benign skip (R7).

## 5. Validation rules traceability

| Rule | Model enforcement |
|---|---|
| FR-003 config block | `AssumptionScheduleConfig` + validators |
| FR-005 min batch | `evaluate()` + `SkipReason.MIN_BATCH_SIZE` |
| FR-006/007 escalation | `EntryTrackingRecord` timestamps + backoff ladder |
| FR-008 summons content | `BatchSummary` (no entry-content fields exist to leak) |
| FR-010 idempotence | `window_decisions` occurrence keys; tracking timestamps |
| FR-011 audit | `deliveries` append-only + `rule` citations everywhere |
| FR-012 failure ≠ delivered | write-after-success discipline |
| FR-013 concurrency | lockfile |
| FR-015 auto-waive opt-in | `AutoWaivePolicyConfig.enabled=False` default |
| FR-016 nothing silent | `TerminalOutcome` required to leave tracking |
| FR-023 retention | prune predicate on `TerminalOutcome.at` + 90 days |
