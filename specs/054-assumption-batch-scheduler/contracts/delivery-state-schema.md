# Contract: persisted delivery state

**Location**: `<cwd>/.maverick/notify/state.json` + `<cwd>/.maverick/notify/lock`
(cwd resolved once at the CLI boundary — Guardrail 7). Cross-run feature state,
deliberately *not* under `.maverick/runs/<run-id>/` (idempotence spans
invocations). Per-machine, never committed, never shared between clones (spec
Assumptions).

## `state.json` schema (`schema_version: 1`)

```json
{
  "schema_version": 1,
  "updated_at": "2026-08-05T13:00:12Z",
  "window_decisions": {
    "2026-08-05/09:00": {
      "outcome": "delivered",
      "decided_at": "2026-08-05T13:00:12Z",
      "entry_ids": ["mav-abc", "mav-def"],
      "rule": "window 09:00 due"
    },
    "2026-08-04/17:00": {
      "outcome": "skipped-min-batch",
      "decided_at": "2026-08-04T21:00:03Z",
      "entry_ids": ["mav-abc"],
      "rule": "1 < min_batch_size 2; rolled to next window"
    }
  },
  "entry_tracking": {
    "mav-hi1": {
      "first_seen": "2026-08-05T03:10:00Z",
      "severity": "high",
      "interrupt_delivered_at": "2026-08-05T03:10:05Z",
      "escalation_delivered_at": null,
      "renotify_count": 0,
      "next_renotify_at": null,
      "terminal": null
    }
  },
  "deliveries": [
    {
      "kind": "interrupt",
      "delivered_at": "2026-08-05T03:10:05Z",
      "trigger": "high severity recorded; high_overrides_quiet=true",
      "entry_ids": ["mav-hi1"],
      "summary": {"counts": {"high": 1, "medium": 0, "low": 0},
                   "owner_specs": ["054-assumption-batch-scheduler"],
                   "oldest_age_hours": 0.1,
                   "review_invocation": "maverick review --list --status open"}
    }
  ]
}
```

Field semantics: see `data-model.md` §4. All persisted timestamps are UTC
ISO-8601 (house convention); local-time reasoning happens only inside
evaluation with the injected `now`.

## Invariants

1. **Occurrence idempotence (FR-010)**: a `window_decisions` key, once present,
   is never re-decided. Keys are `"YYYY-MM-DD/HH:MM"` (local date + configured
   window) — date-based identity makes DST fall-back double-delivery
   structurally impossible.
2. **Write-after-success (FR-012)**: `delivered_at` timestamps,
   `window_decisions` entries with `outcome: "delivered"`, and `deliveries`
   records are written only after the ntfy POST succeeded. A failed delivery
   leaves state exactly as if the decision were never made — it re-arms on the
   next run. Skip decisions (`skipped-min-batch`, `empty`) are recorded
   immediately (no effect to fail).
3. **Single writer (FR-013)**: all reads/writes happen under the pid lockfile.
   Stale locks (dead pid, malformed file) are reclaimed; live locks cause a
   benign skip (contract in `cli-notify-json.md`).
4. **Atomicity**: every save is a whole-file `atomic_write_json`
   (`maverick.utils.atomic`) via `asyncio.to_thread`; readers never observe a
   torn file.
5. **Nothing leaves silently (FR-016)**: an `entry_tracking` row may only be
   pruned after `terminal` is set (`resolved-by-human` observed, or
   `auto-waived` performed by the scheduler with its rationale in `detail`).
6. **Retention (FR-023)**: prune runs at end of successful evaluation. An
   `entry_tracking` row is prunable when `terminal.at` ≤ now − 90 days. A
   `deliveries` record and a `window_decisions` key are prunable when **every**
   entry id they reference is prunable by that rule. Records referencing any
   open entry are never pruned. A record referencing **no** entry ids (an
   empty-batch window decision) satisfies that rule vacuously but has no entry
   to date it, so it is dated by its own `decided_at`/`delivered_at` against
   the same 90-day horizon — the "why was nothing delivered at 09:00" audit
   trail survives the full review horizon, and does not accumulate forever.
7. **Unknown schema**: `schema_version` ≠ 1 → refuse to evaluate with a clear
   error (never silently rewrite a newer schema); missing/corrupt file → treat
   as empty state with a structured warning (delivery history is lost but
   behavior stays safe: worst case is one re-delivery, never a missed entry).

## Auditability (SC-004)

For any notification (or skipped window), the tuple
(ledger `created_at`/severity/status, `assumptions.schedule` config,
`state.json` `rule` + timestamps) reconstructs the decision without reading
any other source. `--dry-run --json` over the same inputs reproduces the
decision set without mutating anything.
