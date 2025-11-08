# Implementation Plan: PR CI Automation

**Branch**: `001-pr-ci-automation` | **Date**: 2025-11-08 | **Spec**: `specs/001-pr-ci-automation/spec.md`
**Input**: Feature specification from `/specs/001-pr-ci-automation/spec.md`

## Summary

Automate the creation, monitoring, and merging of AI-authored pull requests by implementing a Temporal activity that standardizes on the authenticated `gh` CLI. The activity must reuse existing PRs, poll CI status with bounded retries, merge on success, and return structured evidence for failures or timeouts so downstream remediation phases can respond deterministically.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: Temporal Python SDK, GitHub CLI (`gh`), uv toolchain  
**Storage**: N/A (stateful data returned via Temporal workflow payloads)  
**Testing**: pytest with Temporal workflow/activity fixtures, ruff linting  
**Target Platform**: Linux Temporal worker container  
**Project Type**: Temporal workflow automation service  
**Performance Goals**: Detect terminal CI status within two polling intervals (≤2 minutes) once GitHub marks runs complete; merge eligible PRs ≤5 minutes after green CI  
**Constraints**: Deterministic workflow orchestration, exclusive use of `gh` CLI, bounded polling timeout (default 45 minutes), exponential backoff within retry budget  
**Scale/Scope**: Single-repository automation supporting dozens of concurrent workflow attempts per worker

## Constitution Check (Pre-Design)

- **Simplicity First**: PASS — single Temporal activity with supportive helpers; no new services introduced.
- **Test-Driven Development**: PASS — plan mandates new unit and integration tests before implementation.
- **UV-Based Development**: PASS — all commands run through `uv` and existing pyproject tooling.
- **Temporal-First Architecture**: PASS — activity encapsulates side effects; workflows remain deterministic.
- **Observability & Monitoring**: PASS — structured logging and metrics captured via existing logging utilities.
- **Documentation Standards**: PASS — plan outputs remain within `specs/001-pr-ci-automation/`.

**Gate Status**: ✅ Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/001-pr-ci-automation/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── pr-ci-automation.openapi.yaml
```

### Source Code (repository root)

```text
src/
├── activities/
│   ├── __init__.py
│   └── pr_ci_automation.py        # new activity module
├── workflows/
│   ├── __init__.py
│   └── phase_automation.py        # orchestrator invokes new activity
├── workers/
│   └── main.py                    # register activity + polling configuration
├── utils/
│   ├── logging.py
│   └── phase_results_store.py
└── models/
    └── phase_automation.py        # extend with new request/result dataclasses

tests/
├── integration/
│   └── test_pr_ci_automation_workflow.py   # new coverage for workflow path
└── unit/
    └── test_pr_ci_automation_activity.py   # new coverage for activity logic
```

**Structure Decision**: Extend existing Temporal automation layout by adding a dedicated activity module, updating workflow orchestration, and introducing focused unit/integration tests that mirror source directories.

## Implementation Phases

### Phase 0 – Research (Complete)
- Captured CLI usage, retry strategy, and matrix build handling in `research.md`.
- No outstanding clarifications remain.

### Phase 1 – Design & Contracts (Complete)
- Documented data structures in `data-model.md`.
- Defined Temporal activity contract in `contracts/pr-ci-automation.openapi.yaml`.
- Authored operator quickstart in `quickstart.md`.
- Updated GitHub Copilot agent context via `.specify/scripts/bash/update-agent-context.sh copilot`.

### Phase 2 – Implementation & Validation (Planned)
1. Scaffold `src/activities/pr_ci_automation.py` with deterministic polling loop, `gh` command wrappers, and exponential backoff utility.
2. Extend `src/models/phase_automation.py` with request/result dataclasses, including SLA timing fields, aligning to the documented data model.
3. Implement remote branch resolution, base-branch alignment guards, and per-poll metrics emission in `src/activities/pr_ci_automation.py` before wiring orchestration.
4. Persist idempotent metadata and SLA metric snapshots using existing utilities in `src/utils/phase_results_store.py`.
5. Wire activity into `src/workflows/phase_automation.py` and ensure workers register it.
6. Add unit tests for command parsing, retry behavior, base-branch mismatch handling, SLA metrics, and payload shaping.
7. Add integration tests that stub `gh` CLI responses (success, failure, timeout, base-branch mismatch) and validate workflow outputs.
8. Run `uv run pytest` and `uv run ruff check .`; address findings.

## Constitution Check (Post-Design)

- Design artifacts uphold all constitutional principles; no violations introduced.
- Observability commitments (structured logging, retry telemetry) remain intact.

**Gate Status**: ✅ Ready for Phase 2 execution.

## Complexity Tracking

No constitutional violations require tracking at this time.
