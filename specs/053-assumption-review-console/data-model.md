# Data Model: Assumption Review Console

**Feature**: 053-assumption-review-console | **Date**: 2026-07-25

This feature is contract-heavy and model-light: it projects existing typed
models over a new JSON surface and adds two small new types. Existing
models are reused unmodified unless noted.

## Reused existing models (read side)

| Model | Location | Role here |
|---|---|---|
| `AssumptionRecord` | `assumptions/models.py:139` | Core entry state (bead_id, question, adopted_answer, alternatives, severity, status, owner_spec, source_bead, change_ids, is_legacy) |
| `AssumptionReportEntry` | `assumptions/models.py:196` | Rich read view (record + final_answer, waiver fields, reconcile fields, `pending_reconcile`, derived `bucket`, `affected_change_ids`, `blocks_landing`) — the single source for listing rows and land-report rows |
| `LandFrontier` | `assumptions/models.py:257` | Gate evaluation (`open_entries`, `pending_reconcile_entries`, `is_empty`) |
| `LandVerification` | `assumptions/models.py:180` | `verified \| conditionally-verified \| blocked` |
| `LandReport` / `SpecReportSection` | `assumptions/land_report.py` | Versioned report document (`to_dict()` = schema_version 1, contract 052) |
| `ReconcileReport` / `AnswerOutcome` | `workflows/reconcile/models.py` | Reconcile run result (`to_dict()`; outcome status `reconciled \| skipped \| needs_interactive_review`) |
| `ReconcileRunState` / `AnswerState` | `workflows/reconcile/state.py` | Persisted per-run state (pydantic, `model_dump(mode="json")`) |
| `BulkWaiveResult` | `assumptions/models.py:297` | `waived: tuple[AssumptionRecord,...]`, `failed: dict[str, str]` |
| `Severity` | `assumptions/models.py` | `low \| medium \| high` |

## New types

### `ErrorKind` (StrEnum) — `maverick/cli/json_output.py`

Stable machine-branchable failure taxonomy. Additive evolution only;
values are part of the public contract (see
`contracts/error-envelope.md`).

```
validation | not-found | already-resolved | bd-unavailable
| dirty-working-copy | concurrent-run | locked | frontier-blocked
| confirmation-required | curation-failed | vcs | internal
```

### `JsonEnvelope` (frozen dataclass) — `maverick/cli/json_output.py`

The one shape every `--json` document takes.

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `int` | Constant `1` for this feature; additive bumps only |
| `verb` | `str` | Stable dotted id: `review.list`, `review.answer`, `review.waive`, `review.bulk-waive`, `reconcile.run`, `reconcile.dry-run`, `land.status`, `land.run` |
| `ok` | `bool` | `true` = verb executed and produced `result`; `false` = refused/failed with `error` |
| `result` | `dict \| None` | Present iff `ok` |
| `error` | `JsonError \| None` | Present iff not `ok` |

`JsonError` (frozen dataclass): `kind: ErrorKind`, `message: str`,
`details: dict` (default empty; verb-specific structured context, e.g.
the full land report under `frontier-blocked`).

Constructors: `JsonEnvelope.success(verb, result)` /
`JsonEnvelope.failure(verb, kind, message, details=...)`; `to_dict()`
omits the absent branch entirely (never `"result": null`).

**Validation rules**: `ok XOR error`; `verb` must be in the registry;
serialization is the only output path (`emit_json` writes exactly one
document to stdout).

### `entry_to_dict(entry: AssumptionReportEntry) -> dict[str, object]` — `maverick/assumptions/serialize.py`

Not a new model — the canonical row projection, extracted from
`land_report._entry_to_dict` and extended additively. Both `review --list`
and the land report emit this shape (land report nests it under spec
sections; the listing is flat).

| Key | Source |
|---|---|
| `bead_id`, `question`, `adopted_answer`, `alternatives[]`, `severity`, `severity_defaulted`, `is_legacy`, `source_bead` | `entry.record` |
| `owner_spec` | `entry.record.owner_spec` (**new in row**, needed by flat listing) |
| `status` | `entry.record.status` (`open \| answered \| waived`) |
| `bucket` | derived (`resolved \| waived \| open`) (**new in row**) |
| `blocks_landing` | derived (`bucket == open or pending_reconcile`) (**new in row**) |
| `final_answer`, `waiver{by,at,reason} \| null` | waive/answer fields |
| `reconcile{status,reconciled_answer,change_id,reason}` | reconcile lifecycle fields |
| `pending_reconcile` | 051 predicate |
| `affected_change_ids[]` | ledger stamps + reconcile change id, deduped |
| `annotations[]` | derived display hints (unchanged) |

### Skill asset — `src/maverick/skills/review_console/SKILL.md`

Package data, not code. Identity: frontmatter `name: maverick-review`.
Installed to `<project>/.claude/skills/maverick-review/SKILL.md` by
`maverick init` (always overwritten — Maverick-owned, versions with the
wheel); removed by `maverick uninstall`. Behavior contract in
`contracts/skill-review-console.md`.

## Conceptual entities (no code artifact)

### Decision (skill-level)

One human resolution of one presented entry. States:
`confirm-adopted | choose-alternative | free-form-answer | waive(reason)
| skip | bulk-waive(spec, severities, reason)`. Every non-skip decision
maps to exactly one verb invocation, applied immediately (FR-011).

### Sweep (skill-level)

Ordered pass over the listing document (`owner_spec` group → severity
high→low → ledger order). Lifecycle: `list → [decide]* → (reconcile once
| skip) → frontier report → (land offer → land | end)`. Interruption-safe
because no state is held: restarting re-lists and only open entries
reappear (FR-012).

## State transitions touched

Entry status (existing, unchanged semantics — this feature only adds
surfaces that trigger them):

```
open --answer(text)--> answered [reconcile_status=pending]
open --waive(reason)--> waived
answered --reconcile--> reconcile_status ∈ {reconciled, needs-interactive-review}
answered --re-answer--> answered [reconcile status cleared, re-armed]  (051 FR-017)
```

New boundary guard (R6): the verbs pre-check current status before any
ledger write. `answer` accepts `open` or `answered` targets (re-answer
supersedes and re-arms reconcile, 051 FR-017); `waive` accepts `open`
only. Any other target state → `already-resolved` error envelope with the
current row in `error.details.entry`, no ledger write.
