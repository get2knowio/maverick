# Implementation Plan: Multi-Task Orchestration Workflow

**Branch**: `001-multi-task-orchestration` | **Date**: 2025-11-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-multi-task-orchestration/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement a Temporal workflow that orchestrates sequential processing of multiple task files through all phases (initialize, implement, review/fix, PR/CI/merge). The workflow will support interactive approval gates between phases, maintain progress state for resumability after worker restarts, and implement fail-fast behavior when tasks fail after retry limits. All task results are stored in Temporal workflow state (no external storage). The orchestration workflow calls existing phase workflows as child workflows using pure workflow composition.

## Technical Context

**Language/Version**: Python 3.11 (existing project standard)
**Primary Dependencies**: Temporal Python SDK (existing), uv for dependency management (existing)
**Storage**: N/A (all state stored in Temporal workflow state as per FR-017, FR-019)
**Testing**: pytest with Temporal testing utilities (existing standard)
**Target Platform**: Linux server (containerized worker processes)
**Project Type**: Single project (existing Temporal-based automation system)
**Performance Goals**: Process 10-task batch in under 4 hours (SC-005); assuming ~20 minutes per task including all phases and potential retries
**Constraints**: 
- Temporal event history size limits (must accommodate all task results and child workflow executions without exceeding limits)
- Sequential processing only (no parallel execution to avoid branch conflicts)
- Worker restart tolerance (must support resume without re-executing completed work)
**Scale/Scope**: 
- Target: 5-10 tasks per workflow execution (typical batch size)
- Maximum: 20 tasks per workflow execution (recommended limit per research.md to avoid Temporal event history size limits)
- Each task contains 2-6 phases (variable, discovered at runtime)
- Child workflow invocation overhead per phase
- Signal handling latency for interactive mode

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Simplicity First ✅
- **Compliance**: Feature starts with simplest approach - sequential task processing with basic signal-based control
- **Justification**: No premature complexity added; parallel processing explicitly out of scope
- **Evaluation**: PASS - follows YAGNI principle

### II. Test-Driven Development ✅
- **Compliance**: Testing requirements defined in spec (SC-001 through SC-010)
- **Plan**: Unit tests for activities, integration tests for workflow execution paths, contract tests for child workflow interactions
- **Coverage**: 90% minimum for workflow-critical paths per constitution standard
- **Evaluation**: PASS - TDD approach required and planned

### III. UV-Based Development ✅
- **Compliance**: All dependency management and execution via uv (existing project standard)
- **Evaluation**: PASS - no deviation from standard

### IV. Temporal-First Architecture ✅
- **Compliance**: 
  - Activities: Task file parsing activity (FR-026) - pure function ✅
  - Workflows: Orchestration workflow calls existing phase workflows as child workflows (FR-006, FR-007) ✅
  - Determinism: Must use `workflow.now()` for timing, `workflow.logger` for logging ✅
  - Type Safety: Must specify `result_type` for dataclass returns, use Literal types (not Enums) ✅
  - Worker: Single consolidated worker hosts all workflows ✅
  - State Management: All results stored in Temporal workflow state (FR-017, FR-019) ✅
- **Phase 1 Verification Complete**: 
  - `AutomatePhaseTasksWorkflow` uses `AutomatePhaseTasksParams` dataclass (proper serialization) ✅
  - Returns `PhaseAutomationSummary` dataclass (proper deserialization with `result_type`) ✅
  - All workflows follow `@workflow.defn` decorator with explicit names ✅
  - Data models (data-model.md) use frozen dataclasses with `__post_init__` validation ✅
  - All status fields use `Literal` types, not Enums ✅
- **Evaluation**: PASS - all requirements satisfied, existing workflows fully compatible

### V. Observability and Monitoring ✅
- **Compliance**: 
  - Structured logging at task/phase boundaries (FR-035, FR-036, FR-037) ✅
  - Workflow uses `workflow.logger` exclusively ✅
  - Progress query exposed for external monitoring (Notes section) ✅
  - JSON serialization with SafeJSONEncoder for any activity logging ✅
  - Metrics and tracing: Deferred to post-MVP; logging provides sufficient observability for initial release; metrics collection (task success rates, phase durations) and distributed tracing integration can be added in future iterations without architectural changes
- **Evaluation**: PASS - comprehensive logging planned for MVP; metrics/tracing roadmapped for post-MVP

### VI. Documentation Standards ✅
- **Compliance**: This plan is ephemeral spec in `specs/` directory, will not be referenced from durable docs
- **Evaluation**: PASS - proper separation maintained

### Overall Assessment: ✅ PASS (Re-evaluated Post-Phase 1)
- All constitution principles satisfied
- Phase 0 verification completed: existing phase workflow interfaces fully compatible
- Phase 1 design review completed: all data models follow constitution standards
- No violations requiring complexity justification
- Ready to proceed to Phase 2 (task breakdown)

## Phase Parameter Mapping

The orchestration workflow invokes `AutomatePhaseTasksWorkflow` as a child workflow for each discovered phase. The mapping from task file content to child workflow parameters is as follows:

**Common Parameters (all phases)**:
- `task_file_path`: String - Absolute path to the task markdown file
- `phase_name`: String - Name of the phase being executed (e.g., "initialize", "implement", "review_fix", "pr_ci_merge")

**Phase-Specific Parameters**:
- Phase discovery activity parses the task file to extract phase definitions
- Each phase section in the task file may contain metadata (e.g., branch name, reviewers, CI configuration)
- `AutomatePhaseTasksWorkflow` receives phase name and task file path, then internally determines phase-specific behavior
- No additional parameters required at orchestration level; phase workflows handle their own configuration extraction

**Example Child Workflow Call**:
```python
result = await workflow.execute_child_workflow(
    "AutomatePhaseTasksWorkflow",
    AutomatePhaseTasksParams(
        task_file_path=task_file_path,
        phase_name=phase_name
    ),
    execution_timeout=timedelta(minutes=30),
    retry_policy=RetryPolicy(
        maximum_attempts=retry_limit,
        initial_interval=timedelta(seconds=1),
        maximum_interval=timedelta(seconds=60),
        backoff_coefficient=2.0,
        non_retryable_error_types=["ValidationError"]
    ),
    result_type=PhaseAutomationSummary
)
```

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
│   ├── phase_tasks_parser.py        # Parse task files to discover phases (NEW)
│   └── [existing activities]
├── workflows/
│   ├── multi_task_orchestration.py  # Main orchestration workflow (NEW)
│   ├── phase_automation.py          # Existing phase workflows (REFERENCE)
│   └── [existing workflows]
├── models/
│   ├── orchestration.py             # OrchestrationInput, TaskResult, etc. (NEW)
│   └── [existing models]
├── workers/
│   └── main.py                      # Register new workflow (MODIFY)
└── cli/
    └── orchestrate.py               # CLI entry point (NEW)

tests/
├── unit/
│   ├── test_phase_tasks_parser.py   # Unit tests for parser activity (NEW)
│   └── test_orchestration_models.py # Model validation tests (NEW)
├── integration/
│   └── test_multi_task_orchestration.py  # Workflow execution tests (NEW)
└── fixtures/
    └── multi_task_orchestration/    # Sample task files for testing (NEW)
        ├── task_2_phases.md
        ├── task_4_phases.md
        └── task_6_phases.md
```

**Structure Decision**: Single project structure (existing Temporal-based system). New orchestration workflow added alongside existing phase workflows. All new code follows established patterns:
- Activities in `src/activities/` (pure functions)
- Workflows in `src/workflows/` (orchestration logic)
- Models in `src/models/` (data structures)
- Tests mirror source structure
- CLI follows existing pattern in `src/cli/`

## Complexity Tracking

No constitution violations requiring justification. All principles satisfied with one verification item to complete in Phase 0 (existing phase workflow interfaces compatibility).
