# Implementation Plan: Containerized Validation with Docker Compose

**Branch**: `001-docker-compose-runner` | **Date**: 2025-10-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-docker-compose-runner/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Add a new Temporal workflow step that accepts a Docker Compose file path, parses it into a YAML structure, and passes it to activities that create a containerized environment before running existing validation steps. All validations will execute inside the target container using `docker compose exec`. The workflow will use unique project names per run (derived from workflow/run IDs), require health checks for target services, clean up successful runs automatically, and retain failed environments indefinitely for troubleshooting. Technical approach involves PyYAML for parsing, Docker Compose V2 for orchestration, temporary file management for compose configurations, and health check polling before validation execution.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: Temporal Python SDK, PyYAML (for YAML parsing), uv (dependency management)  
**Storage**: Temporary filesystem (for Docker Compose YAML files)  
**Testing**: pytest with Temporal testing utilities  
**Target Platform**: Linux containers (dev container environment, Docker-in-Docker support)  
**Project Type**: Single project (Temporal-first architecture)  
**Performance Goals**: Environment startup + validation completion within 5 minutes for 95% of runs; startup failure detection within 60 seconds  
**Constraints**: Maximum 1 MB YAML file size; Docker Compose V2 required; health checks mandatory for target service; unique project names per workflow run  
**Scale/Scope**: Single workflow modification; 2-3 new activities; shared data models; integration with existing ReadinessWorkflow

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Simplicity First ✅
**Status**: PASS  
**Justification**: Starting with simplest approach - direct Docker Compose V2 integration without abstraction layers. Temporary file management uses Python stdlib `tempfile`. No custom orchestration logic beyond what Compose provides. Complexity limited to: parsing YAML (PyYAML), executing shell commands (subprocess), polling health checks (simple loop with timeout).

### II. Test-Driven Development ✅
**Status**: PASS  
**Justification**: Will follow Red-Green-Refactor for all new activities. Unit tests for YAML parsing, validation, and file management. Integration tests for Docker Compose lifecycle. Mock-based tests for health check polling to avoid Docker dependency in fast tests.

### III. UV-Based Development ✅
**Status**: PASS  
**Justification**: PyYAML will be added via `uv add pyyaml`. All tests run via `uv run pytest`. No additional package managers introduced.

### IV. Temporal-First Architecture ✅
**Status**: PASS  
**Justification**: 
- New activities will be pure functions (compose_up, check_health, compose_down, run_validation_in_container)
- ReadinessWorkflow will orchestrate with proper activity timeouts
- All activities will use `result_type` for dataclass returns
- Workflow will use `workflow.logger` exclusively (no module imports)
- Workflow will use `workflow.info().workflow_id` and `workflow.info().run_id` for project naming (deterministic)
- Worker consolidation maintained (register new activities in existing worker)

### V. Observability and Monitoring ✅
**Status**: PASS  
**Justification**:
- Activities will use structured logging via `src/utils/logging.py`
- Workflow will use `workflow.logger` with workflow_id/run_id context
- All Docker Compose commands will capture stdout/stderr for diagnostics
- Health check polling will log status transitions
- Cleanup operations will log success/failure

### VI. Documentation Standards ✅
**Status**: PASS  
**Justification**: All planning artifacts in ephemeral `specs/001-docker-compose-runner/`. Will update durable AGENTS.md via agent context script. README remains user-focused without spec references.

**Overall Assessment**: No constitutional violations. All principles satisfied with standard approaches.

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
├── activities/
│   ├── __init__.py
│   ├── copilot_help.py
│   ├── gh_status.py
│   ├── param_echo.py
│   ├── repo_verification.py
│   └── compose.py              # NEW: Docker Compose lifecycle management
├── cli/
│   ├── __init__.py
│   └── readiness.py           # MODIFIED: Add --compose-file parameter
├── common/
│   ├── __init__.py
│   └── logging.py
├── models/
│   ├── __init__.py
│   ├── parameters.py          # MODIFIED: Add compose_config field
│   ├── prereq.py
│   ├── verification_result.py
│   ├── workflow_state.py
│   └── compose.py             # NEW: Docker Compose data models
├── utils/
│   ├── __init__.py
│   ├── logging.py
│   ├── param_accessor.py
│   └── url_normalization.py
├── workers/
│   ├── __init__.py
│   └── main.py                # MODIFIED: Register new compose activities
└── workflows/
    ├── __init__.py
    └── readiness.py           # MODIFIED: Add compose setup/teardown steps

tests/
├── conftest.py
├── integration/
│   ├── test_readiness_workflow.py  # MODIFIED: Add compose scenarios
│   └── test_compose_lifecycle.py   # NEW: Full lifecycle integration tests
└── unit/
    ├── test_copilot_help.py
    ├── test_gh_status.py
    ├── test_remediation_messages.py
    ├── test_compose_activities.py   # NEW: Unit tests for compose activities
    └── test_compose_models.py       # NEW: Unit tests for data validation
```

**Structure Decision**: Maintains single-project layout per constitution. New code follows existing patterns: activities in `src/activities/`, models in `src/models/`, workflow modifications in `src/workflows/`. No additional projects or architectural layers needed.

## Complexity Tracking

No constitutional violations. All complexity justified by requirements and follows simplicity-first principle.

---

## Planning Phase Completion Summary

### Artifacts Generated

All Phase 0 (Research) and Phase 1 (Design & Contracts) artifacts have been successfully generated:

✅ **Phase 0 - Research** (`research.md`):
- Resolved parameter format strategy (parsed dict in workflow params)
- Selected PyYAML for parsing with `safe_load`
- Defined target service selection policy (single→auto, multiple→"app", else→explicit)
- Established temporary directory management pattern (`tempfile.mkdtemp`)
- Designed health check polling strategy (exponential backoff with `docker compose ps --format json`)
- Specified error extraction approach (last 50 lines of stderr with `errors='replace'`)
- Defined cleanup patterns (separate activity with "graceful" and "preserve" modes)

✅ **Phase 1 - Design & Contracts**:
- **data-model.md**: Complete data models with validation rules
  - `ComposeConfig`: Workflow parameter with size limits and timeout settings
  - `ComposeEnvironment`: Running environment state with unique project naming
  - `ComposeUpResult`: Startup result with categorized errors
  - `ComposeCleanupParams`: Cleanup mode specification
  - `ValidateInContainerParams`: Container execution parameters
  - Target service resolution algorithm documented
  - All invariants specified
- **contracts/openapi.yaml**: Activity and workflow interfaces
  - `compose_up_activity`: Start environment with health checks
  - `compose_down_activity`: Cleanup with mode support
  - `validate_in_container_activity`: Run commands in target service
  - Modified ReadinessWorkflow contract with optional compose support
  - CLI interface specification
- **quickstart.md**: Developer guide with examples
  - Setup instructions with prerequisites
  - CLI and programmatic usage examples
  - Configuration options and service selection logic
  - Troubleshooting guide for common issues
  - Best practices for performance and reliability

✅ **Agent Context Updated**:
- Added Python 3.11 + Temporal Python SDK to active technologies
- Added PyYAML for YAML parsing
- Added temporary filesystem for compose files
- Updated `.github/copilot-instructions.md` via update-agent-context.sh

### Constitution Compliance

All constitutional principles satisfied:
- ✅ **Simplicity First**: Direct Docker Compose integration without abstraction layers
- ✅ **Test-Driven Development**: Unit and integration test strategy defined
- ✅ **UV-Based Development**: PyYAML added via uv, all scripts use uv
- ✅ **Temporal-First**: Activities pure, workflow orchestrates, worker consolidation maintained
- ✅ **Observability**: Structured logging and workflow.logger usage specified
- ✅ **Documentation Standards**: All artifacts in ephemeral specs/ directory

### Key Technical Decisions

1. **Parameter Passing**: Parse YAML in CLI, pass dict structure to workflow (not file paths)
2. **Docker Version**: Docker Compose V2 (`docker compose` plugin, not legacy v1)
3. **Size Limit**: 1 MB maximum for YAML content
4. **Health Checks**: Required for target service; fail early if missing
5. **Project Naming**: Unique per run using `maverick-<workflow_id>-<run_id>`
6. **Cleanup Policy**: Graceful on success, preserve indefinitely on failure
7. **Timeouts**: 300s startup default, 60s validation default (both configurable)
8. **Error Handling**: Tolerant decoding (`errors='replace'`), last 50 lines extraction

### Next Steps

**Phase 2** (Task Breakdown) is the next phase but is NOT part of this `/speckit.plan` command.

To proceed with implementation:
1. Run `/speckit.tasks` to generate tasks.md with TDD-based task breakdown
2. Implement activities in `src/activities/compose.py`
3. Add data models in `src/models/compose.py`
4. Modify ReadinessWorkflow in `src/workflows/readiness.py`
5. Update CLI in `src/cli/readiness.py`
6. Register activities in `src/workers/main.py`
7. Write tests following TDD principles

**Branch**: `001-docker-compose-runner`  
**Planning Complete**: 2025-10-30  
**Ready for**: Task generation (`/speckit.tasks`)

