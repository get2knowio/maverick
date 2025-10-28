# Implementation Plan: CLI Prerequisite Check

**Branch**: `001-cli-prereq-check` | **Date**: 2025-10-28 | **Spec**: /workspaces/maverick/specs/001-cli-prereq-check/spec.md
**Input**: Feature specification from `/specs/001-cli-prereq-check/spec.md`

## Summary

Provide a simple readiness check as a Temporal workflow that verifies two prerequisites:
1) GitHub CLI is installed and authenticated; 2) Standalone Copilot CLI (`copilot help`) is available.
The workflow orchestrates activity checks, returns a pass/fail summary, and prints actionable human‑readable
guidance on failures. Non‑interactive by default; no environment mutations.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Temporal Python SDK; uv for dependency management; pytest (tests)
**Storage**: N/A
**Testing**: pytest with temporal testing utilities; unit for activities; integration for workflow
**Target Platform**: Linux server (devcontainer), CI
**Project Type**: single
**Performance Goals**: Readiness check completes < 30s locally
**Constraints**: Non‑interactive; human‑readable only; no environment changes
**Scale/Scope**: Single workflow, 2 activities (gh status, copilot availability)
## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Simplicity First: Single workflow with two activities; no extra layers → PASS
- TDD (Non‑negotiable): Temporal tests planned before implementation → PASS
- UV‑Based Development: All scripts via uv in pyproject.toml → PASS (planned)
- Temporal‑First Architecture: Activities for checks; workflow orchestrates only → PASS
- Observability: Structured logging in activities and workflow → PASS

Re-check after Phase 1 design: No changes causing violations identified. → PASS

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
src/
├── activities/
│   ├── gh_status.py
│   └── copilot_help.py
├── workflows/
│   └── readiness.py
├── workers/
│   └── readiness_worker.py
└── cli/
  └── readiness.py

tests/
├── unit/
│   ├── test_gh_status.py
│   └── test_copilot_help.py
└── integration/
  └── test_readiness_workflow.py
```
**Structure Decision**: Single project. Temporal‑oriented layout separating Activities, Workflows, Workers, and CLI.

## Phase 0: Outline & Research

Research tasks derived from Technical Context and domain best practices:

- Research Temporal Python testing patterns for deterministic workflow tests.
- Research reliable strategies for checking `gh auth status` (parsing/exit codes).
- Research detection of standalone `copilot` binary across PATH safely.
- Best practices for uv scripting and pyproject.toml script entries.

Create research.md consolidating decisions with rationale and alternatives.

## Phase 1: Design & Contracts

Artifacts to produce:

- data-model.md: Entities for per‑tool check result and overall summary.
- contracts/openapi.yaml: Minimal POST /readiness-check contract mapping workflow I/O.
- quickstart.md: uv instructions to run the workflow locally (Temporal dev server).
- Agent context: update via `.specify/scripts/bash/update-agent-context.sh copilot`.

Re‑evaluate Constitution Check after design; ensure no violations.

## Complexity Tracking

No violations anticipated; feature remains minimal per Simplicity First.
> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
