# Contract: `maverick refuel` Spec Kit mode CLI surface

**Feature**: 048-speckit-refuel-ingestion

## Command

```
maverick refuel <NAME> [--speckit] [--dry-run] [--enrich] [existing flags]
```

`NAME` resolution (FR-001, D11):

| Input form | Resolves to |
| --- | --- |
| `048-speckit-refuel-ingestion` | `specs/048-speckit-refuel-ingestion/` (exact dir name) |
| `048` | the unique dir with that `NNN` prefix |
| `speckit-refuel-ingestion` | the unique dir with that exact name suffix |
| classic plan name | `.maverick/plans/<name>/flight-plan.md` (existing behavior) |

## New flags

| Flag | Default | Behavior |
| --- | --- | --- |
| `--speckit` | off | Force ingestion mode. Error if `NAME` doesn't resolve to a Spec Kit-shaped dir. |
| `--dry-run` | off | Full resolve/parse/validate/plan; print complete preview; zero writes (no beads, no state, no run metadata, no chaining). Exit 0. |
| `--enrich` | off | One-shot LLM pass attaching verification commands to new task beads. Failure → warning, ingestion continues. Only step that may touch a model. |

Existing flags on the speckit path: `--session-log` honored; `--auto-commit` honored (commits refuel output via jj snapshot, as classic); `--skip-briefing` ignored with a warning (no briefing exists on this path); `--plans-dir` ignored for speckit resolution; `--list-steps` lists the speckit step names when combined with `--speckit`.

## Mode dispatch

| `NAME` resolves to | `--speckit` | Result |
| --- | --- | --- |
| speckit only | any | speckit ingestion; mode announced: `Using Spec Kit ingestion (specs/048-…)` |
| classic only | absent | classic refuel (unchanged) |
| classic only | present | error E02 |
| both | absent | error E01 (disambiguate) |
| both | present | speckit ingestion |
| neither | any | error E02 |

## Exit codes

| Code | Condition |
| --- | --- |
| 0 (SUCCESS) | Ingestion complete; delta no-op ("no new tasks"); any `--dry-run` that validates |
| 1 (FAILURE) | E01–E07 below; bd not ready (`verify_bd_ready`, unchanged) |

## Error catalog (all on stderr via `err_console`, Rich-formatted, no raw tracebacks)

| ID | Trigger | Message must include |
| --- | --- | --- |
| E01 | Name matches classic AND speckit | Both paths found; rerun with `--speckit` or rename |
| E02 | `--speckit` (or speckit-only name) unresolvable | What was looked for (`specs/<query>*/` with `spec.md` + `tasks.md`) and where |
| E03 | Ambiguous speckit match | All candidate directories listed |
| E04 | Unsupported template version | `unsupported template version <X>, supported: <range>` |
| E05 | Parse error | File path, line number, expected structure, suggested fix |
| E06 | Validation error (duplicate task ID / unknown dep ref / cycle) | Offending task ID(s) and line number(s) |
| E07 | Nothing to ingest (zero open tasks, first run) | Counts of completed/total tasks; no epic is created |

## Output (success)

- Human-readable phase lines per CLI standards (Rich, no emoji, `[green]✓[/]`), one completion line per step with timing.
- Summary block: epic ID, N tasks created, M skipped (completed), K skipped (already ingested), edge count, warnings.
- Delta no-op prints: `No new tasks to ingest for <feature> (epic <id> up to date).`
- Final hint (non-dry-run): `Next: maverick fly --epic <id>` (via existing `find_latest_run` path — FR-016).
- Dry-run prints the same summary prefixed `Dry run — no beads created.` and a per-task table (ID, title, phase, [P], blockers).

## Invariants

- Zero model invocations unless `--enrich` (FR-010).
- No `bd` write before all validation passes (FR-015).
- Dry-run and real run derive output from the same `IngestionPlan` object (SC-005).
