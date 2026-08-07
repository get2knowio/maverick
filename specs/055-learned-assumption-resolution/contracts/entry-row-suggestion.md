# Contract: Entry-Row Projection and CLI Surface Changes

## `entry_to_dict` additions (additive; shared by every surface)

Two new keys on the canonical row (`src/maverick/assumptions/serialize.py`):

```json
{
  "...existing keys...": "unchanged",
  "suggestion": {
    "resolution": "Yes — AsyncRetrying, 3 attempts",
    "resolution_type": "answered",
    "source_entry_id": "mv-142",
    "source_spec": "052-conditional-landing",
    "resolved_at": "2026-08-06T14:03:22+00:00",
    "confidence": 0.87,
    "computed_at": "2026-08-07T10:11:12+00:00"
  },
  "auto_resolved": false
}
```

- `suggestion` is `null` when the entry has no stored suggestion (below threshold,
  store unavailable, or unparseable stored value).
- `auto_resolved` is `true` only when the auto-resolve policy waived the entry
  (`assumption_auto_resolved="true"`); its `waiver.by` is `"maverick-resolver"`.
- Because the land report aliases the same function, `land-report.json` spec
  sections pick both keys up unchanged. Additive ⇒ `schema_version` stays `1`.
  Land surfaces project **stored** suggestions only — back-fill runs exclusively in
  `review --list` (by design, clarify Q5); an entry never listed since its
  suggestion became computable may show `suggestion: null` in a land report.
- `_annotations` gains `"auto-resolved"` when `auto_resolved` is true, so human
  tables and markdown reports show the distinction (FR-018).

## `maverick review --list [--json]`

- Before building rows, the command back-fills suggestions for entries that have
  none stored (research R5/clarify Q5): load corpus once, evaluate, persist
  `assumption_suggestion` per hit. Stored suggestions are never replaced. Store
  unavailable ⇒ silent skip (debug log), listing proceeds.
- JSON payload shape unchanged otherwise (`verb: review.list`,
  `{"entries": [...], "counts": {...}}`); rows carry the new keys.
- Human table: entries with a suggestion show a `suggested` marker; no new columns
  beyond that (bare-terminal fallback stays lean).

## `maverick review <id> --answer/--waive [--json]`

- Success payloads (`review.answer` / `review.waive`) carry the updated row
  (including `suggestion`) as today via `_project_after_write`.
- **Pre-check change (FR-020)**: a waived entry with `auto_resolved=true` is
  re-answerable — the `ALREADY_RESOLVED` refusal applies only to human-waived
  entries. Re-answering an auto-resolved entry follows the normal answer path
  (reconcile re-arm included) and records a rejection for the auto-resolving
  pairing.
- After a successful write the command records the decision and any feedback
  (see decision-records contract) outside the JSON error handler, fail-soft.

## `maverick review --spec <name> --waive <reason> [--json]`

- Unchanged verb shape (`review.bulk-waive`); per waived entry it writes a decision
  record and, where a suggestion was stored, a feedback record (accepted iff the
  bulk reason matches the suggested waive reason under normalization; otherwise
  rejected).

## Error kinds

No new error kinds. Suggestion/decision machinery failures are warnings by
contract (FR-004/FR-021) and never map into the JSON error envelope.
