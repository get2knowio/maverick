# Contract: `maverick land` JSON modes

**Feature**: 053-assumption-review-console
**Envelope**: all documents follow `error-envelope.md`.
Human-mode behavior (no `--json`) and the 052 contracts
(`specs/052-conditional-landing/contracts/cli-land.md`,
`land-report-schema.md`) are unchanged. The `report` object embedded
below is exactly `LandReport.to_dict()` (schema_version 1, additive-only
per 052); this feature adds `owner_spec`, `status`, `bucket`, and
`blocks_landing` keys to its entry rows (additive, legal under 052).

## `land --status [--json]` — verb `land.status`

Read-only frontier/landability query. Evaluates the assumption gate,
builds **and persists** the land report (`.maverick/runs/<run-id>/
land-report.{json,md}` — persistence failure degrades to a stderr
warning and `"degraded_persistence": true`, never a failure), and stops.
No curation, no consolidation, no manifest display, no history mutation.

- `--status` is mutually exclusive with `--dry-run`, `--eject`,
  `--finalize`, `--no-curate`, `--heuristic-only`, `--yes`. `--base` and
  `--branch` are accepted but ignored in `--status` mode (`--base` has a
  default and is therefore always present; the gate evaluation does not
  use it).

### Result

```json
{
  "degraded": false,
  "frontier_clear": false,
  "verification": "verified | conditionally-verified | blocked | null",
  "blocking": {
    "open": ["mav-101", "mav-102"],
    "pending_reconcile": ["mav-201"]
  },
  "report": { LandReport },
  "report_paths": {"json": ".maverick/runs/<id>/land-report.json",
                   "md": ".maverick/runs/<id>/land-report.md"} 
}
```

- **`degraded: true` means the ledger could not be read at all** (bd
  unavailable, or the query failed). The gate degrades *open* on that
  path, so it materializes zero entries and `frontier_clear` is
  trivially `true` — a degraded document is therefore
  indistinguishable from a genuinely verified one on `frontier_clear`
  alone. **Consumers MUST treat `frontier_clear && !degraded` as the
  landable condition.** Distinct from `degraded_persistence`, which
  only says the report artifact couldn't be *written*.
- `verification` is `null` exactly when `degraded` is `true` —
  mirrors 052's omitted-verification semantics; `degraded` inside
  `report` carries the same signal nested.
- `blocking` lists are empty when `frontier_clear` is true.

### Exit codes

- `0` — always, on any completed evaluation (blocked is an **answer**,
  not a failure, for a status query).
- `1` — only for error envelopes (`internal`, `vcs`).

## `land [--json] [--yes] [--dry-run] [--no-curate|--heuristic-only] [--eject|--finalize] [--base <rev>] [--branch <name>]` — verb `land.run`

### Behavior

- **Gate refusal**: frontier non-empty → `ok: false`, `kind:
  frontier-blocked`, `error.details.report` = full report document,
  exit 1. Same gate as human mode; `--json` introduces no bypass
  (FR-007). Exception: with `--dry-run`, the full preview still runs and
  the document reports the block; exit is deferred to the end (052
  behavior preserved).
- **Consent**: the agent-curation approval prompt never fires in JSON
  mode. Reaching it without `--yes` → `confirmation-required` envelope,
  exit 1, before any plan execution. `--yes`, `--no-curate`,
  `--heuristic-only`, and `--dry-run` paths need no prompt. Consent is
  the caller's job (the skill asks the human first).
- Progress and curation narration go to stderr.
- "Nothing to land" is success: `ok: true`, `"landed": false`,
  `"reason": "nothing-to-land"`. It carries the **same key set** as
  every other `land.run` success document (so a consumer reading
  `verification` / `report` / `curation` never `KeyError`s), with
  `"report": null` — the gate is not evaluated on this path, since
  there is no landing to gate.

### Result

```json
{
  "landed": true,
  "mode": "approve | eject | finalize | dry-run",
  "verification": "verified | conditionally-verified | null",
  "degraded": false,
  "curation": {
    "strategy": "none | heuristic | agent",
    "executed_count": 3,
    "total_count": 3
  },
  "report": { LandReport },
  "report_paths": { "json": "...", "md": "..." },
  "hint": "mode-specific next-step text | null"
}
```

- `degraded` carries the same meaning as in `land.status` above: the
  ledger could not be read, so `verification` is `null` and the gate
  passed vacuously rather than on a clean frontier.
- `curation.executed_count` / `total_count` are curation-operation
  counts on the `agent` strategy and squash counts on `heuristic`.
  The heuristic strategy additionally carries `absorb_ran` (bool) and
  `squashed_count` (int): `jj absorb` rewrites history without
  squashing anything, so `squashed_count: 0` alone cannot distinguish
  "absorb folded N fixups" from "nothing to do".

### Exit codes

- `0` — landed (or dry-run preview with clear frontier; or
  nothing-to-land).
- `1` — `frontier-blocked`, `confirmation-required`, `curation-failed`,
  or any other error envelope; dry-run with blocked frontier (deferred,
  052 semantics).
