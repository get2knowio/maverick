# Implementation Plan: Assumption Review Console

**Branch**: `053-assumption-review-console` | **Date**: 2026-07-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/053-assumption-review-console/spec.md`

## Summary

Expose the assumption-review lifecycle as headless, machine-readable CLI
verbs — list the queue with full provenance, answer, waive, bulk-waive,
reconcile status, land status, run reconcile, land — by adding `--json`
output modes (plus a `review --list` mode and a `land --status` mode) to
the existing commands, all sharing one response envelope with stable error
kinds and strict stdout purity. On top of that surface, ship a packaged
Claude Code skill (`maverick-review`, installed into user projects'
`.claude/skills/` by `maverick init`) that sweeps the queue with the human
one entry at a time via AskUserQuestion, applies each decision immediately
through a verb invocation, triggers a single batched reconcile at sweep
end, reports the frontier state, and offers to land — never touching jj
history itself.

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)
**Primary Dependencies**: Click + Rich (CLI), Pydantic (config/models),
structlog, GitPython (reads), `JjClient` (VCS writes), `BeadClient` (bd
ledger), existing `maverick.assumptions` / `maverick.workflows.reconcile`
APIs; no new third-party dependencies
**Storage**: bd (beads) ledger state via `BeadClient`; run artifacts under
`.maverick/runs/<run-id>/` (land-report.json/md, reconcile.json); packaged
skill asset installed to `<project>/.claude/skills/maverick-review/`
**Testing**: pytest + pytest-asyncio + xdist (`make test`), Click
`CliRunner` for command-level tests, unit + scenario split per repo
convention
**Target Platform**: Linux/macOS developer machines and headless CI (no
TTY required for any verb)
**Project Type**: single project (existing `src/maverick/` package)
**Performance Goals**: `review --list` completes in one bd sweep
(`report_entries`, single subprocess pass); JSON emission adds no
measurable overhead over existing rendering; reconcile/land runtimes
unchanged (dominated by model calls / jj operations)
**Constraints**: stdout carries exactly one JSON document in `--json` mode
(diagnostics → stderr); no interactive prompt reachable in JSON mode;
envelope + error kinds evolve additively only; existing human-mode output
and exit codes byte-for-byte unchanged when `--json` is absent (FR-018)
**Scale/Scope**: ledgers of tens to low hundreds of entries; 4 commands
touched, 1 new serializer module, 1 new JSON-output module, 1 packaged
skill, ~8 documented verb contracts

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Async-First | PASS — all verbs ride existing `@async_command` paths; no new subprocess or blocking I/O; workflow execution unchanged. |
| II. Separation of Concerns | PASS — the skill provides judgment/UX only and calls verbs; all deterministic side effects (ledger writes, reconcile, curation, jj) stay in workflows/actions. No agent gains side effects. |
| III. Dependency Injection | PASS — commands keep receiving config via `ctx.obj`; `entry_to_dict`/envelope helpers are pure functions; no global state added. |
| IV. Fail Gracefully | PASS — `json_error_handler()` maps the `MaverickError` hierarchy to structured envelopes; partial bulk-waive outcomes enumerated, not discarded; land-report persistence failure stays a degradation, never a block. |
| V. Test-First | PASS — every new surface (envelope, serializer, `--list` filters, JSON modes, init install step, skill asset presence) gets tests before implementation; existing-mode regression tests pin human output. |
| VI. Typed Contracts | PASS — `JsonEnvelope` frozen dataclass + `ErrorKind` StrEnum; row projection sourced from typed `AssumptionReportEntry`; reuses versioned `LandReport.to_dict()` / `ReconcileReport.to_dict()`. No new ad-hoc dict blobs on public paths (existing untyped curation-action dicts are consumed, not extended). |
| VII. Simplicity & DRY | PASS — one envelope, one entry serializer shared by listing and land report, one JSON error handler; no parallel commands; reuses dead-but-present `cli/output.py` formatting seam. |
| VIII. Relentless Progress | PASS — skill continues sweep past per-entry failures (already-resolved etc.); reconcile/land failure surfaces actionable structured errors; no silent giving up, and deliberately **no blind retries** per spec FR-017 (human-facing surface, retry is the human's call). |
| IX. Hardening | PASS — already-resolved pre-check validates at the boundary; JSON mode validates flag combinations up front; timeouts/retries unchanged in underlying clients. |
| X. Guardrails | PASS — Guardrail 0/7: commands keep resolving `cwd` at the CLI boundary and passing it down; no `Path.cwd()` added below the CLI layer. Guardrail 3: skill performs no deterministic side effects. Guardrail 5: no new subprocess wrappers. |
| XI. Modularize Early | PASS WITH ACTION — `review.py` (~490 LOC) splits into a `review/` package in this feature (R10); `land.py` gains a helper module rather than inline growth. |
| XII. Ownership | PASS — feature includes fixing the uneven error-handler adoption for the touched commands' JSON paths via the shared handler. |

**Post-Phase-1 re-check**: design artifacts introduce no new violations —
envelope and serializer are single-responsibility modules; skill asset is
data, not code; no new external-system wrappers. Gate holds.

## Project Structure

### Documentation (this feature)

```text
specs/053-assumption-review-console/
├── plan.md              # This file
├── research.md          # Phase 0 output (R1–R10)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── error-envelope.md
│   ├── cli-review-json.md
│   ├── cli-reconcile-json.md
│   ├── cli-land-json.md
│   └── skill-review-console.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by plan)
```

### Source Code (repository root)

```text
src/maverick/
├── assumptions/
│   ├── serialize.py               # NEW: entry_to_dict() canonical row projection (R4)
│   └── land_report.py             # MODIFIED: delegate _entry_to_dict → serialize; additive row fields
├── cli/
│   ├── json_output.py             # NEW: JsonEnvelope, ErrorKind, emit_json(), json_error_handler() (R1, R3)
│   ├── output.py                  # MODIFIED: emit_json transport helper
│   └── commands/
│       ├── review/                # NEW package (split of review.py, R10)
│       │   ├── __init__.py        #   command def + dispatch (re-exports `review`)
│       │   ├── listing.py         #   --list mode: filters, sort, counts (R5)
│       │   ├── entry_actions.py   #   answer/waive/bulk-waive incl. JSON + already-resolved guard (R6)
│       │   └── legacy.py          #   legacy escalation-bead flow
│       ├── reconcile.py           # MODIFIED: --json for run + dry-run (R7)
│       ├── land.py                # MODIFIED: --json, --status dispatch (R8)
│       ├── land_status.py         # NEW: status/report path helper (R8, R10)
│       └── brief.py               # UNCHANGED (existing --format json satisfies FR-003)
├── skills/                        # NEW package-data directory
│   └── review_console/
│       └── SKILL.md               # NEW: maverick-review skill source of truth (R9)
├── init/__init__.py               # MODIFIED: install/refresh skill into .claude/skills/ (R9)
└── cli/commands/uninstall.py      # MODIFIED: remove installed skill

pyproject.toml                     # MODIFIED: include src/maverick/skills/**/*.md in wheel

tests/
├── unit/
│   ├── assumptions/test_serialize.py          # NEW
│   ├── cli/test_json_output.py                # NEW: envelope, error-kind mapping, stdout purity
│   ├── cli/commands/test_review_listing.py    # NEW: filters, ordering, counts, JSON doc
│   ├── cli/commands/test_review_json.py       # NEW: answer/waive/bulk-waive JSON + guards
│   ├── cli/commands/test_reconcile_json.py    # NEW
│   ├── cli/commands/test_land_json.py         # NEW: --status, gate refusal envelope, --yes
│   └── init/test_skill_install.py             # NEW: init installs/refreshes, uninstall removes
└── integration/
    └── cli/test_json_verbs_scenario.py        # NEW: seeded ledger → list → answer/waive →
                                               #      reconcile dry-run → land --status end-to-end
```

**Structure Decision**: Single-project layout, all inside the existing
`src/maverick/` package. New code is two focused modules
(`assumptions/serialize.py`, `cli/json_output.py`), one command-package
split (`cli/commands/review/`), one helper (`land_status.py`), and one
package-data asset (`skills/review_console/SKILL.md`). The skill is data
shipped in the wheel and installed by `maverick init`; no runtime imports
it.

## Complexity Tracking

No constitution violations require justification. The one structural
change beyond strict feature need — splitting `review.py` into a package —
is mandated by Principle XI's refactor trigger, uses the
backwards-compatible re-export pattern, and is scoped inside this feature.
