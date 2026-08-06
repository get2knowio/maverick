# Contract: `maverick notify` CLI + JSON envelope

## Command surface

```
maverick notify [--dry-run] [--json]
```

- `--dry-run` — evaluate and report every decision; zero ntfy calls, zero bd
  writes, zero state writes.
- `--json` — emit the shared `JsonEnvelope` (`src/maverick/cli/json_output.py`)
  on stdout; all narration goes to `err_console`.

Registered lazily in `main.py` `_LAZY_COMMANDS` as `"notify"`. Not added to
`commands_needing_git_gh` (no VCS interaction) nor `commands_needing_config`
gates; config is loaded in-command like `reconcile`.

## Verbs

| Invocation | `verb` |
|---|---|
| `maverick notify --json` | `notify.run` |
| `maverick notify --dry-run --json` | `notify.dry-run` |

`schema_version` is always `1`.

## Success result shape (`ok: true`)

```json
{
  "schema_version": 1,
  "verb": "notify.run",
  "ok": true,
  "result": {
    "configured": true,
    "skipped": null,
    "evaluated_at": "2026-08-05T09:00:12-04:00",
    "deliveries": [
      {
        "kind": "window-batch",
        "trigger": "2026-08-05/09:00",
        "entry_ids": ["mav-abc", "mav-def"],
        "summary": {
          "counts": {"high": 0, "medium": 2, "low": 3},
          "owner_specs": ["054-assumption-batch-scheduler"],
          "oldest_age_hours": 11.5,
          "review_invocation": "maverick review --list --status open"
        },
        "rule": "window 09:00 due"
      }
    ],
    "skips": [
      {"reason": "low-never-proactive", "entry_ids": ["mav-low1"], "occurrence": null,
       "rule": "low severity accumulates silently"}
    ],
    "auto_waives": [],
    "dry_run": false
  },
  "error": null
}
```

Contract points:

- `evaluated_at` is the injected local `now` (aware, machine-local offset) —
  deliberately different from persisted state, where all timestamps are UTC
  ISO-8601 (contracts/delivery-state-schema.md).
- `configured: false` + `skipped: "not-configured"` + empty arrays when no
  `assumptions.schedule` block exists — **exit 0, `ok: true`** (FR-021:
  inert is an answer, not a failure).
- `skipped: "concurrent-evaluation"` when the lockfile is held by a live pid —
  **exit 0, `ok: true`**, no evaluation performed. This deliberately diverges
  from `reconcile`'s `locked` error kind: overlapping cron fires are normal
  operation for this command (research R7).
- Every delivery and every skip carries `rule` — the human-readable citation of
  the deciding rule (SC-004 auditability surfaces here and in persisted state).
- `--dry-run` returns the identical shape with `dry_run: true`; `deliveries`
  then means *would deliver*.
- In dry-run, `auto_waives` lists would-waive entries; in real runs it lists
  entries actually waived (with their recorded rationale text).

## Error mapping (`ok: false`)

| Condition | `error.kind` | Exit |
|---|---|---|
| Schedule configured but `notifications.enabled` false or `topic` unset | `validation` (message names the exact missing key) | 1 |
| Malformed `maverick.yaml` / schedule values | `validation` | 1 |
| bd missing / not initialized (`bd_ready_reason` non-None, or `verify_available()` False — translated explicitly, it does not raise) | `bd-unavailable` | 1 |
| Ledger read failure (`AssumptionLedgerError`) | `validation` (existing `json_error_handler` mapping) | 1 |
| ntfy delivery retries exhausted | `delivery-failed` (**new additive `ErrorKind`**) with `error.details.failed_deliveries` listing the undelivered decisions; partial successes are recorded in state before exit | 1 |
| Unexpected exception | `internal` | 1 |

`KeyboardInterrupt` follows house behavior: nothing emitted, exit 130.

## Exit codes

| Outcome | Exit |
|---|---|
| Evaluated (with or without deliveries), unconfigured no-op, or benign lock skip | 0 (`SUCCESS`) |
| Any `ok: false` envelope | 1 (`FAILURE`) |
| Interrupted | 130 |

## Human-mode output (no `--json`)

Follows Appendix C conventions — Rich console, no emoji, human-readable
phrasing:

- Unconfigured: single line
  `Assumption delivery is not configured (no assumptions.schedule block in maverick.yaml).`
- Deliveries: one completion line per delivery with timing-free summary, e.g.
  `[green]✓[/] Delivered window batch (2 medium, 3 low; oldest 11.5h) for 09:00 window`
- Skips are summarized only at verbose level; a quiet no-op run prints
  `Nothing due.`
- Delivery failure: `[red]✗[/] Delivery failed: <reason>` +
  `[yellow]Warning:[/yellow]`-style guidance, exit 1.

## Idempotence contract (FR-010/FR-013)

Two consecutive invocations with unchanged ledger state and the same window
occurrence produce: first → `deliveries` non-empty; second →
`skips: [{"reason": "already-delivered", ...}]` and zero ntfy calls. Concurrent
invocations: exactly one evaluates; the other reports the benign lock skip.
