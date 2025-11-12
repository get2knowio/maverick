# Implementation Plan: Maverick CLI for Local Temporal AI Workflow Orchestration

**Branch**: `001-maverick-cli` | **Date**: 2025-11-10 | **Spec**: `/workspaces/maverick/specs/001-maverick-cli/spec.md`
**Input**: Feature specification from `/specs/001-maverick-cli/spec.md`

**Note**: Generated via `/speckit.plan` workflow.

## Summary

Deliver a CLI named `maverick` with two primary commands: `run` to discover `specs/*/tasks.md`, build TaskDescriptors, start the existing multi‑task Temporal workflow locally, and stream progress; and `status` to query workflow progress by ID. The CLI is non‑mutating (no git branch changes), CI‑friendly (`--json` outputs), and emits structured logs plus basic metrics.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Click (CLI), temporalio (Temporal Python SDK client), uv (tooling), Git CLI (runtime), project logging modules (`src/common/logging.py`)
**Storage**: N/A (no new stores; uses Temporal service and repo filesystem)
**Testing**: pytest with 10‑minute timeout wrapper; unit tests for descriptor building and git/temporal adapters; integration tests for happy path
**Target Platform**: Linux devcontainer + local host
**Project Type**: Single repo CLI component under `src/cli/`
**Performance Goals**: Build 100+ TaskDescriptors < 5s; first status within 5s; stream updates p95 ≤ 2s
**Constraints**: Non‑interactive dirty‑tree guard (requires `--allow-dirty`), no branch switching or repo writes, deterministic descriptor ordering
**Scale/Scope**: Up to 200 tasks per run in devcontainer

Unknowns: None (all prior ambiguities resolved in spec Clarifications on 2025‑11‑10)

## Constitution Check

Gate assessment against `.specify/memory/constitution.md`:
- Simplicity First: CLI delegates orchestration to existing workflow; minimal surface — PASS
- Test‑Driven Development: Plan includes unit and integration tests; pytest with timeout — PASS
- UV‑Based Development: Commands run via uv; no pip/poetry — PASS
- Temporal‑First Architecture: CLI uses Temporal client only; no workflow code in CLI — PASS
- Observability & Logging: CLI uses `src/common/logging.py` and emits metrics; no tracing in this phase — PASS
- Determinism Rules: Not applicable to CLI (workflows unaffected) — PASS
- Worker Architecture: Not applicable to this feature — PASS

Result: PASS. Proceed to Phase 0.

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

```text
src/
  activities/
  cli/
  common/
  models/
  utils/
  workers/
  workflows/

tests/
  integration/
  unit/
```

**Structure Decision**: Single project. Existing repo structure retained. CLI code in `src/cli/` with supporting utils in `src/utils/` and models in `src/models/`. Tests in `tests/unit` and `tests/integration`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations; complexity tracking not required for this increment.
