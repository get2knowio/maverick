# Data Model: Learned Assumption Resolution

Entities, fields, validation, and state transitions. Storage locations per
research.md R1/R4.

## DecisionRecord (runway, `decisions.jsonl`)

Frozen Pydantic model in `runway/models.py`, `to_dict()`/`from_dict()` like its
siblings. One line per terminal human resolution; append-only.

| Field | Type | Notes |
|---|---|---|
| `source_entry_id` | `str` | Assumption bead id the decision resolved — the decision's stable identity (R3) |
| `question` | `str` | Original question text (from the entry's `## Question` section) |
| `normalized_question` | `str` | `matching.normalize_question(question)` — precomputed for matching |
| `adopted_answer` | `str` | What the agent had adopted |
| `resolution_type` | `Literal["answered", "waived"]` | |
| `resolution` | `str` | Answer text, or waive reason |
| `severity` | `str` | `low` / `medium` / `high` (entry's severity at resolution) |
| `owner_spec` | `str` | Owning spec of the resolved entry |
| `resolved_by` | `str` | Git user name (same source as `waived_by` today) |
| `resolved_at` | `str` | UTC ISO-8601 |

**Collapse rule** (read side): group by `source_entry_id`, latest `resolved_at`
wins as the authoritative version; earlier lines remain as history (FR-003).
**Admission rule**: written only by the human review surfaces (R6) — never by
scheduler auto-waives or auto-resolution (FR-005).

## MatchFeedbackRecord (runway, `match-feedback.jsonl`)

Frozen Pydantic model; append-only. One line per accept/reject event.

| Field | Type | Notes |
|---|---|---|
| `normalized_question` | `str` | Of the entry that carried the suggestion |
| `source_entry_id` | `str` | Decision identity the suggestion came from — pairing key = (`normalized_question`, `source_entry_id`) |
| `outcome` | `Literal["accepted", "rejected"]` | |
| `recorded_at` | `str` | UTC ISO-8601 |

**Fold rule**: per pairing, `penalty = REJECTION_PENALTY * max(0, rejections - acceptances)`;
`effective_confidence = base_score - penalty` (R2). One net rejection suppresses any
pairing: max base 1.0 − 0.30 < 0.75 (FR-015).

## Suggestion (bd state key `assumption_suggestion`, JSON value)

Frozen dataclass in `assumptions/models.py`, serialized as compact JSON into one bd
state key (atomic single-key write — R4). Parsed into
`AssumptionReportEntry.suggestion`.

| Field | JSON key | Type | Notes |
|---|---|---|---|
| `resolution` | `resolution` | `str` | Suggested answer text or waive reason |
| `resolution_type` | `resolution_type` | `"answered" \| "waived"` | |
| `source_entry_id` | `source_entry_id` | `str` | Provenance: which prior entry |
| `source_spec` | `source_spec` | `str` | Provenance: which spec |
| `resolved_at` | `resolved_at` | `str` | Provenance: when resolved |
| `confidence` | `confidence` | `float` | Effective confidence at computation time, [0,1] |
| `computed_at` | `computed_at` | `str` | UTC ISO-8601 |

**Lifecycle**: written once at recording (or back-filled on first listing without
one); never silently replaced (clarify Q5). Unparseable value ⇒ treated as absent,
never overwritten (R11).

**Wire format note**: the "JSON key" column above is the field/`entry_to_dict`
projection shape only — the shape `review --list --json`/the land report
actually emit (`contracts/entry-row-suggestion.md`), unchanged. The bd-persisted
value under `assumption_suggestion` uses **abbreviated internal keys** (`r`,
`rt`, `sid`, `ss`, `ra`, `c`, `ca`) and compact JSON separators instead, purely
to fit bd's state-value length budget — see research.md R4's addendum. A
suggestion whose encoded JSON would risk truncation is never persisted at all
(treated as no match) rather than stored corrupted.

## New ledger state keys (`assumptions/models.py`)

| Constant | Key | Value |
|---|---|---|
| `KEY_SUGGESTION` | `assumption_suggestion` | JSON object above |
| `KEY_AUTO_RESOLVED` | `assumption_auto_resolved` | `"true"` when the auto-resolve policy waived the entry |

## AssumptionReportEntry (extended, `assumptions/models.py`)

New fields: `suggestion: Suggestion | None = None`,
`auto_resolved: bool = False` (derived from `KEY_AUTO_RESOLVED`). Populated by
`report_entry_from_details`; legacy entries always `None`/`False`.

## Config (`config.py`)

```yaml
assumptions:
  resolution:            # absent ⇒ auto-resolution inert; suggestions always on
    auto_resolve_low:
      enabled: true      # default false; double opt-in
      confidence_threshold: 0.92   # ge 0.75 (== PRESENTATION_THRESHOLD), le 1.0
```

`AutoResolvePolicyConfig(enabled: bool = False, confidence_threshold: float =
Field(default=0.9, ge=0.75, le=1.0))`;
`AssumptionResolutionConfig(auto_resolve_low: AutoResolvePolicyConfig | None = None)`;
`AssumptionsConfig.resolution: AssumptionResolutionConfig | None = None`.
Violating bounds fails config load (FR-016).

## Matching constants (`assumptions/matching.py`)

| Constant | Value | Meaning |
|---|---|---|
| `PRESENTATION_THRESHOLD` | `0.75` | Minimum effective confidence to attach/present a suggestion (built-in, fixed) |
| `REJECTION_PENALTY` | `0.30` | Per net rejection deduction on a pairing (0.30 > 1.0 − 0.75, so one net rejection suppresses even an exact match) |

## State transitions

```
Entry recorded ──evaluate corpus──▶ no candidate ≥ 0.75 ──▶ no suggestion (back-fill may retry on listing)
                                  └▶ best candidate ≥ 0.75 ──▶ KEY_SUGGESTION written
                                       └▶ low severity AND policy enabled AND conf ≥ threshold
                                            ──▶ ledger.waive(waived_by="maverick-resolver")
                                                + KEY_AUTO_RESOLVED="true"        [entry: open → waived]

Human resolves entry with suggestion:
  resolution matches suggestion (type + normalized text) ──▶ feedback: accepted
  anything else ──▶ feedback: rejected  (lowers pairing's future effective confidence)

Human answers an auto-resolved (waived) entry:
  ALREADY_RESOLVED pre-check bypassed for auto_resolved=true (FR-020)
  ──▶ ledger.answer(...) [waived → answered, reconcile re-armed via existing pending status]
  + feedback: rejected (for the pairing that auto-resolved it)
  + decision record written (human-initiated)
```

## Invariants

1. A machine-written resolution (scheduler auto-waive, auto-resolve) never produces
   a `DecisionRecord` (FR-005) — enforced by capture living only in the human CLI
   surfaces (R6).
2. `evaluate_suggestion` never returns a candidate whose `source_entry_id` equals
   the entry being evaluated (self-match, R12).
3. Exactly one suggestion per entry; ties broken by (confidence desc,
   `resolved_at` desc, `source_entry_id` asc) — fully deterministic (FR-010).
4. Auto-resolution requires: severity == low (legacy ⇒ medium ⇒ ineligible),
   policy enabled, effective confidence ≥ configured threshold ≥ 0.75 (FR-016/017).
5. The land gate's `classify()` and `frontier()` are byte-identical to today —
   auto-resolved entries are ordinary waived entries to them (FR-013/019).
