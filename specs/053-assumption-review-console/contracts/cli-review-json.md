# Contract: `maverick review` JSON modes

**Feature**: 053-assumption-review-console
**Envelope**: all documents follow `error-envelope.md`.
Human-mode behavior (no `--json`) is byte-for-byte unchanged (FR-018).

## `review --list [--json]` — verb `review.list`

List assumption-ledger entries with full provenance.

### Invocation

```
maverick review --list [--status open|answered|waived]... [--spec <owner>]...
                [--severity low|medium|high]... [--json]
```

- `--status`, `--spec`, `--severity` are repeatable; within one option
  values OR, across options AND.
- Default when no `--status` given: `open` only — the sweep population.
- `--list` is mutually exclusive with `BEAD_ID` and with all decision
  flags (`--answer`, `--waive`, `--approve`, `--reject`, `--defer`).
- Without `--json`, renders a human table (new, minimal; reuses the same
  data).

### Result

```json
{
  "entries": [ {row} ],
  "counts": {
    "total": 7,
    "by_status": {"open": 5, "answered": 1, "waived": 1},
    "by_severity": {"low": 3, "medium": 3, "high": 1},
    "pending_reconcile": 1
  }
}
```

- `entries` ordering is the canonical sweep order: `owner_spec`
  (ascending), then severity high→low, then stable ledger order. Clients
  MUST NOT re-sort for presentation.
- Row shape: the canonical entry row (see `data-model.md`
  `entry_to_dict`): `bead_id, question, adopted_answer, alternatives[],
  severity, severity_defaulted, status, bucket, blocks_landing,
  owner_spec, source_bead, is_legacy, final_answer, waiver|null,
  reconcile{...}, pending_reconcile, affected_change_ids[],
  annotations[]`. Identical to the land-report row shape.
- `counts` reflects the **filtered** selection.

### Exit codes

- `0` — listed (including zero entries: `ok: true`, empty `entries`).
- `1` — `bd-unavailable` or query failure.

## `review <BEAD_ID> --answer <text> [--json]` — verb `review.answer`

### Behavior

- JSON mode requires `--answer` (or `--waive`); no flag →
  `validation` error. Prompting never occurs in JSON mode.
- Empty/whitespace answer → `validation` (rejected before any write).
- Pre-check: entry's current status must be `open` (or `answered` for a
  re-answer, which is legal per 051 FR-017 and re-arms reconcile).
  A `waived` or otherwise closed target → `already-resolved` with the
  current row in `error.details.entry`.
- Unknown bead id → `not-found`.
- The "not flagged for human review" interactive confirm becomes a
  `validation` error in JSON mode.
- Legacy escalation beads accept `--approve` / `--reject <guidance>` /
  `--defer` instead; result then reports the legacy action taken and any
  correction bead created.

### Result

```json
{"entry": {row}, "action": "answered"}
```

`entry` is the post-write row (status `answered`, `reconcile.status`
`"pending"`).

**Degraded projection**: the row comes from a re-read issued *after* the
ledger write committed. If that read fails, the write still happened, so
the verb reports success with `"entry": null` and `"degraded": true`
rather than a failure envelope — reporting `ok: false` here would tell
the caller a recorded decision was not recorded. `degraded` is absent
when the projection succeeded.

### Exit codes: `0` recorded; `1` any error envelope.

## `review <BEAD_ID> --waive <reason> [--json]` — verb `review.waive`

Same guards as `review.answer` (open target required; `already-resolved`
otherwise). `waived_by` resolves from git user name (fallback
`"unknown"`), unchanged. The same degraded-projection rule applies.

### Result

```json
{"entry": {row}, "action": "waived"}
```

### Exit codes: `0` recorded; `1` any error envelope.

## `review --spec <owner> --waive <reason> [--severity ...]... [--json]` — verb `review.bulk-waive`

### Behavior

- Existing semantics unchanged: severity filter defaults to `low` when
  omitted; selects open entries owned by `<owner>` matching the filter;
  waives each; per-entry failures collected.
- Zero matching entries is success (idempotent), `ok: true` with empty
  `waived`.

### Result

```json
{
  "owner_spec": "049-assumption-ledger",
  "severities": ["low"],
  "waived": [ {row} ],
  "failed": {"mav-123": "reason string"},
  "unprojected": ["mav-456"]
}
```

- `unprojected` (present only when non-empty) lists entries that **were
  waived successfully** but whose post-write row could not be re-read.
  They are neither `waived` rows nor `failed` — treating them as failures
  would misreport a completed waive. Same degraded-projection rule as
  `review.answer` above, applied per entry so one unreadable row never
  discards the others.

### Exit codes

- `0` — all selected entries waived (or none matched).
- `1` — one or more per-entry failures (`ok: true`, `failed` non-empty —
  the verb ran; outcomes say what failed), or an error envelope
  (`not-found` for unknown spec, `bd-unavailable`, `validation`).
  `unprojected` alone does **not** affect the exit code — those waives
  succeeded.
