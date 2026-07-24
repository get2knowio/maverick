# Implementation Plan: Transactional Reconcile of Changed Human Answers

**Branch**: `051-reconcile-changed-answers` | **Date**: 2026-07-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/051-reconcile-changed-answers/spec.md`

## Summary

`maverick reconcile` retroactively applies changed human answers from the
assumption ledger back into jj history. For each changed answer (deterministically
detected: normalized `assumption_answer` state ≠ `## Adopted Answer` in the entry
description), processed earliest-in-stack first: the workflow snapshots the jj
operation log, has a reconciler agent produce the correction delta in a new child
of the ledger-stamped change, folds it in via `jj squash --into` (or `jj absorb`
for multi-target entries), lets jj auto-rebase descendants, walks resulting
conflicts with a round-budgeted resolution loop (default 3), runs a
semantic-dependents pass comparing the correction diff against each descendant's
diff, and re-runs the gate suite (`run_independent_gate`). Any failure restores
the pre-answer operation via `jj op restore` and marks the entry
`needs-interactive-review`; success marks it `reconciled`. Only changes outside
jj's `immutable()` revset are ever touched. The command batches all pending
changed answers per invocation and supports `--dry-run`.

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)
**Primary Dependencies**: jj ≥ 0.43 (via `JjClient` — `squash --into`, `absorb`, `op restore`, `immutable()`/`conflicts()` revsets), bd CLI (via `BeadClient`), airframe agent runtime (`runtime_for_agent`), Click + Rich, Pydantic, structlog, tenacity
**Storage**: bd bead state keys (ledger reconcile status), `.maverick/runs/<run-id>/reconcile.json` (resumable run state, atomic writes), jj operation log (restore points)
**Testing**: pytest + pytest-asyncio + xdist; unit tests with mocked `CommandRunner`/`BeadClient`/stub agents; integration tests against real colocated jj repos (CI installs jj — see commit e51d228)
**Target Platform**: Linux/macOS developer checkout (single-repo CWD model, Guardrail 0)
**Project Type**: single project — extends existing `src/maverick/` packages
**Performance Goals**: detection + dry-run are zero-model-call and complete in seconds; per-answer wall time is dominated by agent calls and the gate suite (minutes, matching fly's per-bead profile)
**Constraints**: agents never run jj/bd side effects (Guardrail X.3); all history mutations through `JjClient`/`library/actions/jj.py`; no bd writes between restore-point capture and terminal status (bd is outside the jj op log); explicit `cwd` threading everywhere (Guardrail 7)
**Scale/Scope**: sweeps of 1–20 changed answers per run; stacks of up to ~50 mutable descendant changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Async-first | PASS | Workflow + agents fully async; subprocesses via `CommandRunner` (never `subprocess.run`) |
| II | Separation of concerns | PASS | Agents produce judgment only (correction edits, conflict resolutions, semantic findings); workflow owns squash/rebase/rollback/gates/ledger writes (FR-020) |
| III | Dependency injection | PASS | `ReconcileConfig`, `BeadClient`, `JjClient`, squadron injected; no globals |
| IV | Fail gracefully, recover aggressively | PASS | Per-answer rollback + continue-with-next (FR-009/FR-010); op-log restore is the recovery primitive |
| V | Test-first | PASS | Unit + integration tests planned per module; TDD ordering in tasks |
| VI | Type safety & typed contracts | PASS | Frozen dataclasses for outcomes, Pydantic payloads registered in `SUPERVISOR_TOOL_PAYLOAD_MODELS`, no `dict[str, Any]` action returns |
| VII | Simplicity & DRY | PASS | Reuses `run_independent_gate`, `stamp_change_id` linkage, `create_human_bead`-style escalation, spec-chain state pattern; no new wrappers for existing systems |
| VIII | Relentless progress | PASS | Checkpointed run state; interrupted runs restore then resume (FR-016); one answer's failure never blocks the rest |
| IX | Hardening by default | PASS | All jj/bd calls through existing timeout/retry layers; specific exception types (`JjError` hierarchy, `AssumptionLedgerError`) |
| X | Architectural guardrails | PASS | Guardrail 0 (runs in cwd, no workspace), X.3 (deterministic ops in workflow), X.8 (canonical wrappers only) |
| XI | Modularize early | PASS | New package `workflows/reconcile/` split into detection/correction/conflicts/semantic/state/workflow modules |
| XII | Ownership & follow-through | PASS | — |

**Post-design re-check (after Phase 1)**: PASS — no violations introduced; Complexity Tracking empty.

## Project Structure

### Documentation (this feature)

```text
specs/051-reconcile-changed-answers/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── cli-reconcile.md      # Command surface, exit codes, output contract
│   ├── ledger-state.md       # New bd state keys + reconcile lifecycle
│   └── payloads.md           # New structured-output payload schemas
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by plan)
```

### Source Code (repository root)

```text
src/maverick/
├── cli/commands/reconcile.py        # NEW: Click command (--dry-run), exit codes, Rich summary table
├── main.py                          # +"reconcile" in _LAZY_COMMANDS and commands_needing_git_gh
├── config.py                        # +ReconcileConfig (resolution_rounds=3, semantic_rounds=3) on MaverickConfig
├── payloads.py                      # +SubmitCorrectionPayload, SubmitConflictResolutionPayload,
│                                    #  +SubmitSemanticDependentsPayload (registered in SUPERVISOR_TOOL_PAYLOAD_MODELS)
├── agents/
│   ├── reconciler.py                # NEW: ReconcilerAgent (provider_tier="implement",
│   │                                #      persona "maverick.reconciler"): correct(), resolve_conflicts()
│   ├── semantic_reviewer.py         # NEW: SemanticDependentsAgent (provider_tier="review",
│   │                                #      persona "maverick.semantic-reviewer"): analyze()
│   └── system_prompts/
│       ├── maverick.reconciler.md          # NEW persona
│       └── maverick.semantic-reviewer.md   # NEW persona
├── squadron/reconcile.py            # NEW: ReconcileSquadron (reconciler + semantic agents)
├── assumptions/
│   ├── models.py                    # +KEY_RECONCILE_STATUS/_AT/_ANSWER/_CHANGE_ID constants,
│   │                                #  +RECONCILE_* status values
│   └── ledger.py                    # +answered_unreconciled_entries(), +mark_reconciled(),
│                                    #  +mark_needs_interactive_review(); answer() clears reconcile status
├── library/actions/jj.py            # +jj_new_child, +jj_squash_into, +jj_list_conflicts,
│                                    #  +jj_check_mutability (thin wrappers over existing JjClient methods)
└── workflows/reconcile/             # NEW package
    ├── __init__.py
    ├── models.py                    # ChangedAnswer, AnswerOutcome, ReconcileReport (frozen dataclasses)
    ├── state.py                     # ReconcileRunState → .maverick/runs/<id>/reconcile.json (atomic, resumable)
    ├── detection.py                 # changed-answer detection + stack ordering (revset-based)
    ├── correction.py                # child → agent delta → squash-into/absorb application
    ├── conflicts.py                 # round-budgeted conflict resolution loop
    ├── semantic.py                  # semantic-dependents pass (diff comparison fan-out)
    └── workflow.py                  # ReconcileWorkflow: transaction boundaries, gates, ledger terminal writes

tests/
├── unit/
│   ├── cli/test_reconcile_command.py
│   ├── workflows/reconcile/{test_detection,test_correction,test_conflicts,test_semantic,test_state,test_workflow}.py
│   ├── assumptions/test_ledger_reconcile.py
│   └── jj/test_client.py            # extended: new action wrappers / revset helpers
└── integration/workflows/test_reconcile_jj.py   # real jj repo: squash-into, auto-rebase, op restore round-trip
```

**Structure Decision**: Single-project layout extending existing packages.
Reconcile follows the spec-chain precedent of a sequential async workflow
package (`workflows/reconcile/`) rather than a Burr graph: the control flow is a
simple nested loop (answers → stages) with explicit transaction boundaries, and
Burr's state-machine indirection would add complexity without buying resumability
we don't already get from `state.py` + the jj op log (see research.md R10).

## Complexity Tracking

No constitution violations — table intentionally empty.
