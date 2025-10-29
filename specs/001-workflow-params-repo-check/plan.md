# Implementation Plan: Parameterized Workflow with Repo Verification

**Branch**: `001-workflow-params-repo-check` | **Date**: 2025-10-29 | **Spec**: `/workspaces/maverick/specs/001-workflow-params-repo-check/spec.md`
**Input**: Feature specification from `/workspaces/maverick/specs/001-workflow-params-repo-check/spec.md`

**Note**: This plan follows the Specify plan workflow and repository constitution.

## Summary

- Build an MVP Temporal workflow that accepts named parameters (starting with `github_repo_url`) and makes them available to all steps.
- Add a pre-flight verification activity that checks the GitHub repository exists.
- Follow gh CLI behavior: perform verification only when `gh` is installed and authenticated; otherwise fail fast with clear guidance to authenticate before proceeding.
- Design parameter handling to scale to multiple parameters, with consistent, typed access by key across steps.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: Temporal Python SDK, gh CLI (runtime tool), uv (dependency manager)  
**Storage**: N/A (no persistence required for MVP)  
**Testing**: pytest with Temporal testing utilities; contract tests for activity behavior  
**Target Platform**: Linux server (local dev via Temporal dev server/Docker)  
**Project Type**: Single project, Temporal workflow + activities  
**Performance Goals**: Repo verification p95 ≤ 5s (FR-007)  
**Constraints**: Deterministic workflows (no non-deterministic syscalls); network I/O only in activities; typed models with `Literal` statuses; structured logs/metrics  
**Scale/Scope**: MVP single parameter now; architecture supports N+ parameters later

Parameter Handling (now → future):
- Accept a `dict[str, Any]` of parameters at workflow start; MVP requires `github_repo_url`.
- Provide a typed accessor utility in activities/steps to fetch declared keys and raise clear errors for missing keys.
- Keep parameter keys stable and documented to enable adding new parameters without breaking steps.

GitHub Verification Approach:
- Activity uses `gh` CLI to validate repo existence, but only after confirming `gh auth status` is authenticated; if not authenticated, return a clear failure and guidance to run `gh auth login`.
- Validate and normalize URL/SSH formats to an `owner/repo` slug before calling `gh`.
- On transient errors (timeouts/rate limits), retry once with backoff, then fail with actionable message.

## Constitution Check

GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.

- Simplicity First: Single workflow + one verification activity; no extra layers added.
- Determinism: Workflow reads parameters and orchestrates; all network/gh calls live in activities; time via `workflow.now()` only.
- Type Safety: Use dataclasses and `Literal["pass","fail"]` for check status; specify `result_type` for activity returns.
- Observability: Structured logs for start, normalized repo, auth status, verification result, retry path.
- Python/uv Standards: Python 3.11, uv-managed deps; containerizable worker.

Status: PASS — No violations identified for MVP.

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
├── workflows/          # Temporal workflow definitions (deterministic)
├── activities/         # External I/O (gh verification)
├── models/             # Dataclasses (Parameters, VerificationResult)
├── workers/            # Worker process entrypoints
└── utils/              # Param accessors, URL normalization

tests/
├── unit/               # Activity + utils tests
├── integration/        # Workflow execution paths
└── contract/           # Contract tests for repo verification behavior
```

**Structure Decision**: Single project aligned with constitution’s Temporal layout; network I/O isolated to activities; deterministic workflow orchestration.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |

