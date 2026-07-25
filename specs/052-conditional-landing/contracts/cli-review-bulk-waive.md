# Contract: `maverick review` bulk waive

Extends `src/maverick/cli/commands/review.py`. Single-entry behavior
(`maverick review <bead-id> [--answer TEXT | --waive REASON]`) is unchanged.

## New invocation shape

```
maverick review --spec <spec-name> --waive "<reason>" [--severity low|medium|high]...
```

- `BEAD_ID` becomes optional. Exactly one of `BEAD_ID` or `--spec` must be
  given; both or neither → usage error, non-zero exit.
- `--spec <name>` — owning spec selector; matches `owner_spec` attribution
  (exact value as shown by `maverick brief` / the land report).
- `--severity` — repeatable filter; **default: `low` only**. `--severity
  medium` additionally includes open legacy entries (they are treated as
  medium everywhere else).
- `--spec` requires `--waive <reason>`; `--spec` with `--answer` (or with the
  legacy `--approve/--reject/--defer` flags) → usage error. Bulk *answering*
  is intentionally unsupported — answers are per-question by nature.

## Semantics

- Selects **open** ledger entries only (never answered/waived ones) owned by
  the spec and matching the severity filter.
- Waives each via the existing single-entry path: full waiver metadata
  (who = git user name, when = now UTC, why = shared reason) recorded on
  **each** entry; each bead closed, releasing any `blocks` edges.
- Zero matches → prints "No open <severities> assumptions for <spec>." and
  exits **zero** (idempotent).
- Partial failure → waives what it can, prints per-entry failures, exits
  non-zero.

## Output

```
✓ Waived 4 low-severity assumptions for 052-conditional-landing:
  ma-0012  Question…
  ma-0015  Question…
  …
Reason: accepted for MVP (waived by Paul O'Fallon)
```

Bulk-waived entries are indistinguishable from individually waived ones in
the ledger, the land report, and `maverick brief` counts.
