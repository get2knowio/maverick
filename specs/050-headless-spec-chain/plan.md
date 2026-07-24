# Implementation Plan: Headless Spec Kit Chain (`maverick spec`)

**Branch**: `050-headless-spec-chain` | **Date**: 2026-07-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/050-headless-spec-chain/spec.md`

## Summary

Add `maverick spec <feature> --from-prd <file>`: a deterministic workflow that runs the
target repository's own Spec Kit chain — specify → clarify → plan → tasks → analyze —
headlessly inside a hidden jj workspace, with each step executed by an airframe
`AgentRuntime` prompting the repo's `/speckit.*` command surface. Clarify never blocks:
adopted answers are filed as assumption-ledger entries (via question interception where
the provider supports it, else Spec Kit's non-interactive convention upgraded into ledger
entries). Analyze findings become standalone remediation beads that `refuel --speckit`
later adopts. Chain state is checkpointed per step for auto-resume; completed-step
artifacts land in the user's `specs/NNN-<feature>/` tree as ordinary markdown.
`maverick init` gains a Spec Kit prerequisite check with an offer to install.

## Technical Context

**Language/Version**: Python 3.11+ (`from __future__ import annotations`)
**Primary Dependencies**: airframe-agents (>=0.9.0rc1,<0.10) for agent execution; Click + Rich (CLI); Pydantic (models/state); structlog; tenacity; jj CLI via `maverick.jj.client.JjClient` (workspace add/forget, colocated); `bd` CLI via `maverick.beads.client.BeadClient`; GitPython (read-only)
**Storage**: Files — chain state under `.maverick/runs/<run-id>/spec-chain.json` (+ `metadata.json` per existing `run_metadata` conventions); artifacts as markdown in `specs/NNN-<feature>/`; ledger entries and remediation findings as bd beads (labels + state keys, per spec 049 conventions)
**Testing**: pytest + pytest-asyncio + xdist (`make test`, `make ci`); airframe runtimes stubbed via injected fakes (same pattern as existing `Agent` tests)
**Target Platform**: Linux/macOS developer CLI (same as all Maverick commands)
**Project Type**: Single project (existing `src/maverick/` package)
**Performance Goals**: N/A latency-wise — chain duration is model-bound (minutes per step); the deterministic overhead (workspace setup, state I/O, landing) must stay negligible (<2s per step)
**Constraints**: Fully headless (no step may block on stdin/interactive input); resumable after halt/interrupt (per-step checkpointing); user's working checkout never modified while steps run; only completed-step artifacts land
**Scale/Scope**: 5 chain steps per run; ≤ ~5 clarify questions per spec; one feature per invocation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle / Guardrail | Status | Notes |
|---|----------------------|--------|-------|
| I | Async-first | PASS | Chain workflow is async end-to-end; subprocess work (jj, bd, artifact sync) goes through `CommandRunner` / existing async clients; no `subprocess.run` on async paths. |
| II | Separation of concerns | PASS | Chain step *content* (spec writing, clarify answers, analysis) is agent judgment via airframe; the workflow owns all deterministic effects — workspace lifecycle, ordering, checkpointing, artifact landing, ledger/bead writes. Agents never commit or write beads. |
| III | Dependency injection | PASS | `SpecChainWorkflow` receives `cwd`, config, `BeadClient`, `JjClient`, and a step-runner (airframe-backed) as injectable deps; tests inject fakes. |
| IV | Fail gracefully, recover aggressively | PASS | Per-step retries via tenacity for transient runtime errors; halt-on-failed-clarify is a *specified* stop (FR-009), not a crash — state is checkpointed and the report names the failed step and resume path. Analyze failure degrades to a warning (FR-012). |
| V | Test-first | PASS | TDD: state/model/parsing units first, then workflow scenarios with stubbed runtimes; contract tests for CLI surface. |
| VI | Type safety & typed contracts | PASS | Chain state, step results, clarify decisions, and analyze findings are frozen dataclasses / Pydantic models (see data-model.md); no `dict[str, Any]` blobs cross boundaries. |
| VII | Simplicity & DRY | PASS | Reuses existing primitives: `JjClient.workspace_add/forget`, `run_metadata`, assumption ledger, `BeadClient`, `CommandRunner`. New code is one workflow package + one thin CLI command + small extensions to existing modules. |
| VIII | Relentless progress | PASS | Checkpoint after every step; auto-resume (FR-020); partial artifacts preserved; analyze findings recorded even when analyze partially fails. |
| IX | Hardening by default | PASS | Every runtime call has explicit timeouts; tenacity for transient errors; specific exception types under a new `SpecChainError` hierarchy branch. |
| X.3 | Deterministic ops not owned by agents | PASS | See II — landing, state, beads, ledger writes all live in the workflow. |
| X.8 | Canonical wrappers | PASS | jj via `JjClient`, beads via `BeadClient`, git reads via GitPython, logging via `maverick.logging`, retries via tenacity. |
| Guardrail 0 (CLAUDE.md single-repo model) / Appendix E | **EXCEPTION — justified** | Spec clarification (2026-07-24) mandates a hidden workspace for the chain. See Complexity Tracking. Constitution/CLAUDE.md amendment is in scope (spec Assumptions). |

**Post-design re-check (after Phase 1)**: PASS — design artifacts introduce no new
violations; the single tracked exception is the hidden workspace, documented below and
carried into the governance-amendment work item.

## Project Structure

### Documentation (this feature)

```text
specs/050-headless-spec-chain/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── cli-spec.md      # `maverick spec` + `maverick init` surface contract
│   ├── chain-state.md   # persisted chain-state contract (resume semantics)
│   └── ledger-and-beads.md  # standalone ledger entries + remediation-bead adoption
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by plan)
```

### Source Code (repository root)

```text
src/maverick/
├── cli/
│   ├── main-registered lazy command: "spec"
│   └── commands/spec.py                 # NEW: thin Click command (arg/option parsing,
│                                        #      preflight, dispatch to workflow, report)
├── workflows/spec_chain/                # NEW: package-per-workflow (Appendix A pattern)
│   ├── __init__.py
│   ├── constants.py                     # step names/order, labels, state keys, timeouts
│   ├── models.py                        # ChainState, StepResult, ClarifyDecision,
│   │                                    # AnalyzeFinding, SpecChainReport (typed contracts)
│   ├── state.py                         # load/save/discover chain state (.maverick/runs/)
│   ├── steps.py                         # per-step prompt builders + step output parsing
│   ├── clarify.py                       # interception + non-interactive upgrade paths
│   ├── landing.py                       # per-step artifact sync workspace → user checkout
│   └── workflow.py                      # SpecChainWorkflow orchestration (async)
├── workspace/                           # NEW (small): hidden jj workspace lifecycle
│   └── spec_chain.py                    # create/reuse/forget via JjClient.workspace_add
├── agents/spec_chain.py                 # NEW: SpecChainAgent (airframe runtime, persona,
│                                        #      structured step-report schema)
├── squadron/                            # SpecChainSquadron (one runtime, role "generate")
├── init/
│   ├── prereqs.py                       # + check_speckit_installed (advisory)
│   └── __init__.py                      # + offer-to-install step (Click confirm)
├── assumptions/ledger.py                # + record_standalone_assumption (no-epic path)
├── beads/client.py                      # + update_parent (adoption primitive, if bd
│                                        #   supports; else dependency-edge fallback)
└── workflows/refuel_speckit/workflow.py # + adopt standalone spec-labeled beads on ingest

tests/
├── unit/
│   ├── workflows/spec_chain/            # state, models, steps, clarify, landing units
│   ├── workspace/                       # hidden-workspace lifecycle (jj stubbed)
│   ├── assumptions/                     # standalone-entry ledger path
│   └── cli/                             # spec command contract, init speckit check
└── integration/
    └── spec_chain/                      # full chain against stubbed runtimes + tmp repo
```

**Structure Decision**: Single project; new code follows the constitution's Appendix A
package-per-workflow split (`workflows/spec_chain/` with `models.py`, `constants.py`,
`workflow.py` plus chain-specific `state.py`/`steps.py`/`clarify.py`/`landing.py`).
Extensions to `init`, `assumptions`, `beads`, and `refuel_speckit` are made in place in
their owning modules — no parallel wrappers (Guardrail X.8).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Hidden jj workspace for chain execution (exception to CLAUDE.md Guardrail 0 single-repo CWD model) | Clarified requirement (Session 2026-07-24): chain steps mutate `specs/`, `.specify/feature.json`, and agent scratch state over multi-minute model calls; the user's checkout must stay untouched until each step's artifacts are complete (FR-014, FR-016, SC-007). | Running in the user's checkout (current contract) exposes half-written spec artifacts and `.specify` state churn to the user mid-run and makes atomic "only completed artifacts land" impossible without ad-hoc staging. The historic reason workspaces were retired — bd's `embeddeddolt/` not traveling into `jj workspace add` — does not apply: the chain never runs bd inside the workspace (ledger + remediation beads are written by the workflow in the user's checkout). Governance docs (CLAUDE.md Guardrail 0, constitution Appendix E) are amended as part of this feature to record the scoped exception. |
| New `workspace/spec_chain.py` module despite prior `WorkspaceManager` retirement | The retired `WorkspaceManager` (clone-based) no longer exists; the chain needs a minimal, purpose-scoped lifecycle helper over `JjClient.workspace_add/forget`. | Resurrecting a general-purpose WorkspaceManager would rebuild the abstraction that was deliberately deleted; inlining jj calls in the workflow would violate DRY once resume + cleanup both need them. The helper is ~1 file, spec-chain-only, and composes the existing canonical `JjClient`. |
