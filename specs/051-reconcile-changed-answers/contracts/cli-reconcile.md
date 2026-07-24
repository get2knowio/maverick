# Contract: `maverick reconcile` CLI

Module: `src/maverick/cli/commands/reconcile.py`, registered in
`main.py` `_LAZY_COMMANDS` (`"reconcile"`) and `commands_needing_git_gh`.

## Invocation

```
maverick reconcile [--dry-run]
```

| Option | Type | Default | Behavior |
|---|---|---|---|
| `--dry-run` | flag | off | Detection, stack ordering, target resolution, and mutability checks only. Zero jj/bd/filesystem mutations. |

`cwd = Path.cwd().resolve()` at the CLI boundary; threaded explicitly to every
layer (Guardrail 7). Decorators: `@async_command`, body wrapped in
`cli_error_handler()`; `verify_bd_ready(cwd)` preflight.

## Preconditions (refuse-to-start, FR-014)

Checked in order; each failure prints `[red]✗[/]` + remediation and exits
`FAILURE(1)`:

1. `bd` available and `.beads/` initialized (`verify_bd_ready`).
2. `.jj/` present (colocated repo — `maverick init` hint otherwise).
3. Working copy clean: `diff_stat(revision="@")` reports zero files.
4. No concurrent run: no live reconcile lockfile
   (`.maverick/runs/reconcile.lock`, pid-stamped, stale entries reclaimed) and
   no fly run metadata in status `flying`.

Exception: an interrupted prior reconcile run does **not** block — it is
recovered first (restore in-flight answer's op snapshot, mark it
needs-interactive-review), then the batch proceeds (FR-016).

## Output contract

Rich console only (`maverick.cli.console`), no emoji, human-readable phase
names. Sequence:

1. `Detecting changed answers...` then either
   `[green]✓[/] No changed answers — nothing to reconcile.` (exit 0) or a
   summary line `N changed answer(s) from the last review sweep`.
2. Per answer, completion lines with timing per stage group, e.g.
   `[green]✓[/] bd-123 Correction folded into qxyzabc (12.4s)`
   `[green]✓[/] bd-123 Gate suite passed (94.2s)` — or
   `[red]✗[/] bd-123 rolled back: conflict budget exhausted (3 rounds)`.
3. Final summary table (columns: `ID`, `Severity`, `Target`, `Status`,
   `Reason`); status values exactly `reconciled`, `skipped`,
   `needs interactive review` (FR-019: one terminal status per answer).
4. When any answer is non-reconciled: hint line
   `Run: maverick review <id>  (re-answer to re-arm reconcile)`.

`--dry-run` prints the same table with status column `would reconcile` /
`would skip (<reason>)` and a `Dry run — no changes made.` footer.

## Exit codes (`ExitCode`)

| Condition | Code |
|---|---|
| All processed answers `reconciled`, or nothing to do | `SUCCESS (0)` |
| Any answer `skipped` or `needs interactive review` | `FAILURE (1)` |
| Precondition failure | `FAILURE (1)` |
| `--dry-run` with valid preconditions | `SUCCESS (0)` regardless of predicted statuses |
| Ctrl-C | `INTERRUPTED (130)` (graceful: current answer rolled back via op restore on next invocation if the restore couldn't run) |

## Side effects (non-dry-run)

- jj: per answer — op snapshot, child change, squash/absorb fold, descendant
  auto-rebase, conflict-resolution folds, semantic-fix folds; on failure — op
  restore. Never touches any revision matched by `immutable()`.
- bd: terminal-only writes (after jj outcome is settled): reconcile state keys
  per data-model §1; escalation beads per data-model §6.
- Filesystem: `.maverick/runs/<run-id>/reconcile.json` checkpoints;
  lockfile lifecycle.
- Final working copy: fresh empty change on the resulting head.
