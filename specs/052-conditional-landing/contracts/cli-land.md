# Contract: `maverick land` (frontier gate + verification state + report)

Extends the existing command (`src/maverick/cli/commands/land.py`). Existing
options are unchanged: `--no-curate`, `--dry-run`, `--yes`, `--base`,
`--heuristic-only`, `--eject`, `--finalize`, `--no-consolidate`, `--branch`.
**No new bypass flag exists or may be added** (guarded by
`test_help_exposes_no_bypass_flag`).

## Gate behavior

| Repo state (repo-wide frontier) | Outcome | Exit code |
|---|---|---|
| ≥1 open entry (any severity, incl. open legacy) | BLOCKED: no curation, push hint suppressed, blocked table + report shown | non-zero |
| ≥1 answered entry pending reconciliation (non-terminal) | BLOCKED: same as above; those rows hint `maverick reconcile` | non-zero |
| Frontier empty, ≥1 waived entry | Lands; classified `conditionally-verified` | zero |
| Frontier empty, all entries answered (or none) | Lands; classified `verified` | zero |

`--dry-run`: evaluates gate + classification, renders the full report,
performs zero jj/git/bd mutations — the only writes are the report artifacts
under `.maverick/runs/<run-id>/` (deliberate: FR-008 requires the audit trail
on every evaluation); exits non-zero at the end iff the gate blocked. The
exit code must hold on **all** curation paths: the current agent-curation
dry-run early-exit (`SystemExit(SUCCESS)` in `_agent_curate`) pre-empts the
gate's non-zero exit today (pre-existing bug) and is fixed by this feature.

bd unavailable / ledger query failure: gate degrades open with a
`[yellow]Warning:[/yellow]` (existing behavior) and the report notes the
degradation; classification is omitted in that case (no false "verified").

## Output

1. **Blocked**: red panel "Blocking Assumptions (N)" — columns ID / Severity /
   Spec / Question / Action (`maverick review <id>` or `maverick reconcile`)
   — followed by the grouped report and a non-zero exit.
2. **Landed**: classification line —
   `[green]✓ Verified[/]` or
   `[yellow]✓ Conditionally verified on unresolved assumptions (N waived)[/]`
   — followed by the grouped report summary and the mode hint.
3. **Mode hints** now reference the PR body artifact, e.g. `--finalize`:
   `gh pr create --base <base> --body-file .maverick/runs/<run-id>/land-report.md`.
   (Land still does not push or create PRs itself — unchanged slice boundary.)

## Report rendering (terminal)

Grouped by owning spec; within each spec three buckets — Resolved, Waived,
Open — with per-entry: question, adopted answer, final answer (when given),
severity, affected change IDs (incl. reconciliation correction), waiver
who/when/why, and annotations (`legacy`, `reconcile: needs-interactive-review`,
`reconcile: skipped`, `pending reconcile`). Zero-entry evaluation prints
"No assumptions adopted."

## Persistence

Every evaluation (all modes, incl. blocked and `--dry-run`) writes
`.maverick/runs/<run-id>/land-report.json` and `land-report.md` atomically
and prints the path. Persistence failure → warning, never a gate failure.
