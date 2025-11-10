# Research: Multi-Task Orchestration Workflow

**Date**: 2025-11-09  
**Feature**: Multi-Task Orchestration Workflow  
**Branch**: `001-multi-task-orchestration`

## Overview

This document captures research findings for implementing a Temporal workflow that orchestrates sequential processing of multiple task files through all phases. Research focused on resolving unknowns from Technical Context and verifying Constitution Check conditions.

## Research Tasks

### 1. Maximum Task Count per Workflow (Event History Limits)

**Question**: What is the maximum number of tasks per workflow considering Temporal event history limits?

**Decision**: Recommend maximum of 20 tasks per workflow execution with monitoring for event count approaching limits.

**Rationale**:
- Temporal event history has a default limit of ~50,000 events before requiring `continue-as-new`
- Each child workflow invocation generates multiple events:
  - ChildWorkflowExecutionStarted
  - ChildWorkflowExecutionCompleted (or Failed)
  - Activity events within child workflows
- For orchestration workflow specifically:
  - Task parsing activity: ~4-6 events per task
  - Child workflow per phase: ~8-12 events (depends on child workflow complexity)
  - Signal handling: ~2 events per signal
  - Progress state updates: minimal overhead (stored in workflow variables)
- Estimated events per task: ~50-100 events (assuming 4 phases per task average)
- With 20 tasks: ~1,000-2,000 events (well under limit with 95% headroom)
- With 50 tasks: ~2,500-5,000 events (still safe, 90% headroom)

**Implementation Guidance**:
- Document recommended limit of 20 tasks in workflow docstring
- Add workflow query to expose current event count estimate
- Log warning if task count exceeds 20 at workflow start
- For larger batches (50+ tasks), implement `continue-as-new` pattern to split into multiple workflow executions
- Add observability metrics for event count trends

**Alternatives Considered**:
- Hard limit enforcement: Rejected - prevents legitimate use cases where fewer events are generated
- Dynamic continue-as-new: Rejected for MVP - adds complexity without clear immediate need
- External state storage: Rejected - contradicts FR-017 requirement to store all state in workflow

---

### 2. Existing Phase Workflow Interfaces

**Question**: How do existing phase workflows handle parameters? Need to verify compatibility with child workflow invocation pattern.

**Findings** (from code analysis):

**AutomatePhaseTasksWorkflow** (`src/workflows/phase_automation.py`):
- **Workflow name**: `"AutomatePhaseTasksWorkflow"`
- **Input parameter**: `AutomatePhaseTasksParams` dataclass
- **Return type**: `PhaseAutomationSummary` dataclass
- **Key parameters**:
  - `repo_path: str` - Repository path
  - `branch: str` - Git branch name
  - `tasks_md_path: str | None` - Path to tasks.md file
  - `tasks_md_content: str | None` - Direct content of tasks.md (alternative to path)
  - `default_model: str | None` - Default AI model for phase execution
  - `default_agent_profile: str | None` - Default agent profile
  - `retry_policy_settings: RetryPolicySettings | None` - Retry configuration
- **State management**: Uses checkpoint pattern for resume capability
- **Invocation pattern**: Can be called as child workflow via `workflow.execute_child_workflow()`

**ReadinessWorkflow** (`src/workflows/readiness.py`):
- **Workflow name**: `"ReadinessWorkflow"`
- **Input parameter**: `Parameters` dataclass
- **Return type**: `ReadinessSummary` dataclass
- **Key parameters**:
  - `github_repo_url: str` - Repository URL
- **Note**: Simpler workflow, coordinates prerequisite checks and repo verification

**Decision**: Existing phase workflows are fully compatible with child workflow invocation pattern. They follow proper dataclass parameter patterns required by Temporal SDK.

**Rationale**:
- Both workflows use dataclass parameters (proper serialization ✅)
- Both return dataclass results (proper deserialization with `result_type` ✅)
- Both use `@workflow.defn` decorator with explicit names
- Both follow Constitution's Temporal-First Architecture principles
- `AutomatePhaseTasksWorkflow` is specifically designed for phase execution with checkpoint support

**Implementation Guidance**:
- Invoke `AutomatePhaseTasksWorkflow` as child workflow for each discovered phase
- Map orchestration parameters to child workflow parameters:
  - Pass through: `repo_path`, `branch`, `default_model`, `default_agent_profile`
  - Generate per-phase: `tasks_md_path` (based on current task file)
  - Configure: `retry_policy_settings` (from orchestration workflow's retry limit)
- Use `result_type=PhaseAutomationSummary` for proper deserialization
- Child workflow timeout: Set to 30 minutes per phase (configurable via workflow parameters)
- Handle child workflow exceptions and map to `PhaseResult` status

**Example invocation pattern**:
```python
from src.models.phase_automation import AutomatePhaseTasksParams, PhaseAutomationSummary

phase_params = AutomatePhaseTasksParams(
    repo_path=orchestration_params.repo_path,
    branch=orchestration_params.branch,
    tasks_md_path=task_file_path,
    default_model=orchestration_params.default_model,
    default_agent_profile=orchestration_params.default_agent_profile,
    retry_policy_settings=retry_settings,
)

result: PhaseAutomationSummary = await workflow.execute_child_workflow(
    "AutomatePhaseTasksWorkflow",
    phase_params,
    start_to_close_timeout=timedelta(minutes=30),
    retry_policy=retry_policy,
    result_type=PhaseAutomationSummary,
)
```

**Alternatives Considered**:
- Creating new phase-specific workflows: Rejected - `AutomatePhaseTasksWorkflow` already handles phase execution
- Activity-based invocation: Rejected - Constitution requires workflow composition for orchestration
- Direct activity calls: Rejected - loses checkpoint/resume capabilities of existing workflows

---

### 3. Signal-Based Interactive Control Best Practices

**Research**: Best practices for implementing signal-based pause/resume pattern in Temporal Python SDK.

**Decision**: Use `asyncio.Event` for internal synchronization with workflow signals for external control.

**Rationale**:
- Temporal signals are the standard mechanism for external workflow control
- `asyncio.Event` provides clean wait/notify pattern within workflow code
- Pattern already used successfully in existing codebase (reviewed worker shutdown handling)
- Signals are durable and survive worker restarts
- Multiple signals can be defined for different control actions

**Implementation Guidance**:
```python
@workflow.defn(name="MultiTaskOrchestrationWorkflow")
class MultiTaskOrchestrationWorkflow:
    def __init__(self) -> None:
        self._continue_event = asyncio.Event()
        self._skip_current = False
        
    @workflow.signal
    async def continue_to_next_phase(self) -> None:
        """Signal to resume from pause."""
        self._continue_event.set()
    
    @workflow.signal
    async def skip_current_task(self) -> None:
        """Signal to skip current task and move to next."""
        self._skip_current = True
        self._continue_event.set()
    
    @workflow.run
    async def run(self, params: OrchestrationInput) -> OrchestrationResult:
        for task in tasks:
            for phase in phases:
                # Execute phase...
                
                if params.interactive_mode:
                    # Pause and wait for signal
                    self._continue_event.clear()
                    await self._continue_event.wait()
                    
                    # Check if skip was requested
                    if self._skip_current:
                        self._skip_current = False
                        break  # Move to next task
```

**Best Practices**:
- Clear event before waiting to handle multiple signals correctly
- Reset skip flag after processing to prevent unintended skips
- Signal handlers should be simple and deterministic (no I/O operations)
- Use separate signals for different actions (clear intent)
- Document signal behavior in workflow docstring

**Alternatives Considered**:
- Condition variables: Rejected - `asyncio.Event` is simpler and sufficient
- Activity-based polling: Rejected - adds unnecessary activity overhead
- Update handlers: Rejected - signals are more appropriate for fire-and-forget commands

---

### 4. Progress Tracking and State Management

**Research**: Patterns for maintaining progress state in workflow variables vs external storage.

**Decision**: Store all progress state and task results in workflow instance variables (fully in-memory within Temporal).

**Rationale**:
- Requirement FR-017 explicitly mandates Temporal workflow state for all results
- Requirement FR-019 specifies no external storage dependencies
- Temporal workflow state is durable and survives worker restarts via event replay
- Simpler architecture - no external database or file system dependencies
- Consistent with Constitution's Simplicity First principle
- Pattern already used in `AutomatePhaseTasksWorkflow` (checkpoint in `self._checkpoint`)

**Implementation Guidance**:
```python
@workflow.defn(name="MultiTaskOrchestrationWorkflow")
class MultiTaskOrchestrationWorkflow:
    def __init__(self) -> None:
        self._completed_task_indices: list[int] = []
        self._task_results: list[TaskResult] = []
        self._current_task_index: int = 0
        self._current_phase: str | None = None
        self._is_paused: bool = False
    
    @workflow.query
    def get_progress(self) -> dict:
        """Query handler to expose current progress."""
        return {
            "current_task_index": self._current_task_index,
            "total_tasks": len(self._input.task_file_paths),
            "current_task_file": self._input.task_file_paths[self._current_task_index] if self._current_task_index < len(self._input.task_file_paths) else None,
            "current_phase": self._current_phase,
            "completed_tasks": list(self._completed_task_indices),
            "is_paused": self._is_paused,
        }
    
    @workflow.query
    def get_task_results(self) -> list[TaskResult]:
        """Query handler to retrieve all task results."""
        return list(self._task_results)
```

**Determinism Considerations**:
- All state variables are deterministically updated based on child workflow results
- No non-deterministic operations (time, random, I/O) in state updates
- State survives replay because it's reconstructed from event history
- Query handlers provide read-only access (no side effects)

**Alternatives Considered**:
- External database: Rejected - contradicts FR-017, adds complexity
- File system storage: Rejected - contradicts FR-019, not cloud-friendly
- Temporal search attributes: Rejected - not suitable for large result objects
- Activity-based persistence: Rejected - unnecessary given workflow state durability

---

### 5. Child Workflow Retry Policy Configuration

**Research**: How to configure retry policies for child workflow invocations to implement workflow-level retry limits.

**Decision**: Configure retry policy on child workflow invocation with maximum attempts matching orchestration workflow's retry limit parameter.

**Rationale**:
- Temporal supports retry policies at child workflow invocation level
- Allows centralized retry configuration from orchestration parameters
- Each child workflow invocation can have independent retry settings
- Retry policy includes exponential backoff by default
- Constitution specifies proper retry policy configuration as best practice

**Implementation Guidance**:
```python
from temporalio.common import RetryPolicy

# In orchestration workflow run method:
retry_policy = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=5),
    backoff_coefficient=2.0,
    maximum_attempts=params.retry_limit,  # From workflow input (default: 3)
)

result: PhaseAutomationSummary = await workflow.execute_child_workflow(
    "AutomatePhaseTasksWorkflow",
    phase_params,
    start_to_close_timeout=timedelta(minutes=30),
    retry_policy=retry_policy,
    result_type=PhaseAutomationSummary,
)
```

**Retry Policy Parameters**:
- `initial_interval`: 10 seconds (allows quick recovery from transient failures)
- `maximum_interval`: 5 minutes (caps backoff for long-running retries)
- `backoff_coefficient`: 2.0 (exponential backoff: 10s, 20s, 40s, ...)
- `maximum_attempts`: From workflow input (default 3, range 1-10)

**Error Handling**:
- When retry limit exhausted, child workflow raises exception
- Orchestration workflow catches exception and marks task as failed
- Workflow immediately stops processing remaining tasks (fail-fast behavior)
- Partial results returned showing completed tasks and failure details

**Alternatives Considered**:
- Activity-level retries: Rejected - child workflows are the execution unit
- Manual retry loops: Rejected - Temporal's built-in retry is more reliable
- Unlimited retries: Rejected - can cause infinite loops, needs bounded attempts

---

## Summary of Decisions

| Research Area | Decision | Impact |
|--------------|----------|--------|
| Max task count | 20 tasks recommended, 50 safe limit | Add documentation and monitoring |
| Phase workflow compatibility | Existing workflows fully compatible | Use `AutomatePhaseTasksWorkflow` as child workflow |
| Signal-based control | `asyncio.Event` + workflow signals | Standard pattern for interactive mode |
| State management | All state in workflow instance variables | Satisfies FR-017, FR-019 requirements |
| Retry configuration | RetryPolicy on child workflow invocation | Centralized retry limit control |

All NEEDS CLARIFICATION items from Technical Context resolved. Constitution Check verification completed - all phase workflows follow proper dataclass patterns and are compatible with child workflow invocation.

## Next Steps

Proceed to Phase 1:
- Define data models in `data-model.md` based on Key Entities in spec
- Generate API contracts (workflow parameters and return types)
- Create `quickstart.md` for developer onboarding
- Update agent context with any new technologies (none expected)
