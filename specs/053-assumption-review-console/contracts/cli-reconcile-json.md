# Contract: `maverick reconcile` JSON modes

**Feature**: 053-assumption-review-console
**Envelope**: all documents follow `error-envelope.md`.
Human-mode behavior (no `--json`) and the 051 CLI contract
(`specs/051-reconcile-changed-answers/contracts/cli-reconcile.md`) are
unchanged; this contract only adds the JSON projection.

Both verbs are synchronous: the invocation blocks until the workflow
completes and the document reflects the final state. No job/polling
protocol exists.

## `reconcile --json` — verb `reconcile.run`

### Behavior

- Preconditions checked exactly as today; failures map to envelopes:
  bd missing → `bd-unavailable`; `.jj` missing or jj failure → `vcs`;
  dirty working copy → `dirty-working-copy`; concurrent flying run →
  `concurrent-run`; held lockfile → `locked`.
- Workflow progress events render to **stderr** in JSON mode.
- Zero detected answers is success: `ok: true`, empty `outcomes`,
  exit 0 (mirrors today's "run_state is None" path).

### Result

`ReconcileReport.to_dict()` (unchanged shape from
`workflows/reconcile/models.py`), plus persisted per-answer state detail:

```json
{
  "run_id": "ab12cd34",
  "dry_run": false,
  "started_at": "...", "finished_at": "...",
  "exit_success": false,
  "outcomes": [
    {
      "entry_id": "mav-201",
      "status": "reconciled | skipped | needs_interactive_review",
      "reason": "... | null",
      "stage_reached": "...",
      "target_change_id": "... | null",
      "escalation_bead_id": "... | null",
      "gate_passed": true,
      "no_change_required": false
    }
  ]
}
```

### Exit codes (unchanged semantics)

- `0` — nothing to reconcile, or every outcome `reconciled`.
- `1` — any outcome `skipped` / `needs_interactive_review` (`ok: true` —
  the verb ran; the outcomes carry the news), or any error envelope.

Consumers (the skill) MUST read `outcomes[].status`, not just the exit
code, and MUST surface `needs_interactive_review` entries with their
`reason` / `escalation_bead_id` to the human without retrying (FR-017).

## `reconcile --dry-run --json` — verb `reconcile.dry-run`

### Behavior

Read-only detection preview per the 051 contract: detection, ordering,
target resolution, mutability guard only; zero jj/bd/filesystem writes;
skips lock and concurrency guards. This is the "reconcile status" verb.

### Result

Same report shape as `reconcile.run` with `dry_run: true`; predicted
`outcomes[].status` is only ever `reconciled` or `skipped`.

### Exit codes

- `0` — always, on any completed prediction (per 051 contract).
- `1` — only for error envelopes (`bd-unavailable`, `vcs`, `validation`).
