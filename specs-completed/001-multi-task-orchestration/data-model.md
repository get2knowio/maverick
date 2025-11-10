# Data Model: Multi-Task Orchestration Workflow

**Date**: 2025-11-09  
**Feature**: Multi-Task Orchestration Workflow  
**Branch**: `001-multi-task-orchestration`

## Overview

This document defines the data structures (dataclasses) for the multi-task orchestration workflow. All entities follow Constitution requirements: frozen dataclasses with validation in `__post_init__`, timezone-aware datetime fields, and `Literal` types (not Enums) for status values.

## Core Entities

### OrchestrationInput

**Purpose**: Workflow input parameters defining task list and execution settings.

**Source**: FR-001, FR-002, FR-003

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class OrchestrationInput:
    """Input parameters for multi-task orchestration workflow.
    
    Attributes:
        task_file_paths: List of task file paths to process sequentially
        interactive_mode: If True, pause after each phase for approval
        retry_limit: Maximum retry attempts for phase execution (1-10)
        repo_path: Repository root path for task execution
        branch: Git branch name for all tasks (must be consistent)
        default_model: Default AI model for phase execution (optional)
        default_agent_profile: Default agent profile (optional)
        
    Invariants:
        - task_file_paths must be non-empty
        - retry_limit must be between 1 and 10 inclusive
        - repo_path must be non-empty
        - branch must be non-empty
    """
    task_file_paths: tuple[str, ...]
    interactive_mode: bool
    retry_limit: int
    repo_path: str
    branch: str
    default_model: str | None = None
    default_agent_profile: str | None = None
    
    def __post_init__(self) -> None:
        """Validate input parameters."""
        if not self.task_file_paths:
            raise ValueError("task_file_paths must contain at least one path")
        
        if self.retry_limit < 1 or self.retry_limit > 10:
            raise ValueError("retry_limit must be between 1 and 10")
        
        if not self.repo_path or not self.repo_path.strip():
            raise ValueError("repo_path must be non-empty")
        
        if not self.branch or not self.branch.strip():
            raise ValueError("branch must be non-empty")
        
        # Normalize paths
        normalized_paths = tuple(path.strip() for path in self.task_file_paths)
        if any(not path for path in normalized_paths):
            raise ValueError("task_file_paths cannot contain empty paths")
        object.__setattr__(self, "task_file_paths", normalized_paths)
        
        # Normalize strings
        object.__setattr__(self, "repo_path", self.repo_path.strip())
        object.__setattr__(self, "branch", self.branch.strip())
```

---

### TaskProgress

**Purpose**: Internal state tracking for a single task during execution.

**Source**: Key Entities in spec, FR-016

```python
from dataclasses import dataclass
from typing import Literal

TaskProgressStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]

@dataclass
class TaskProgress:
    """Progress state for a single task.
    
    Attributes:
        task_index: Zero-based index in task list
        task_file_path: Path to task file
        current_phase: Name of currently executing phase (None if not started)
        completed_phases: List of phase names that have completed
        status: Current task status
        
    Invariants:
        - task_index must be >= 0
        - task_file_path must be non-empty
        - If status is "pending", current_phase must be None and completed_phases must be empty
        - If status is "completed", current_phase must be None
        - If status is "in_progress", current_phase must be non-None
    """
    task_index: int
    task_file_path: str
    current_phase: str | None
    completed_phases: list[str]
    status: TaskProgressStatus
    
    def __post_init__(self) -> None:
        """Validate task progress state."""
        if self.task_index < 0:
            raise ValueError("task_index must be >= 0")
        
        if not self.task_file_path or not self.task_file_path.strip():
            raise ValueError("task_file_path must be non-empty")
        
        # Validate status invariants
        if self.status == "pending":
            if self.current_phase is not None:
                raise ValueError("status=pending requires current_phase=None")
            if self.completed_phases:
                raise ValueError("status=pending requires empty completed_phases")
        
        if self.status == "completed" and self.current_phase is not None:
            raise ValueError("status=completed requires current_phase=None")
        
        if self.status == "in_progress" and self.current_phase is None:
            raise ValueError("status=in_progress requires non-None current_phase")
```

---

### PhaseResult

**Purpose**: Outcome of executing a single phase within a task.

**Source**: Key Entities in spec, FR-009, FR-040

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

PhaseResultStatus = Literal["success", "failed"]

@dataclass(frozen=True)
class PhaseResult:
    """Result of executing a single phase.
    
    Attributes:
        phase_name: Name of the phase executed
        status: Execution outcome (success or failed)
        duration_seconds: Total execution time in seconds
        error_message: Error description if status is failed (None otherwise)
        retry_count: Number of retries attempted (0 if succeeded on first try)
        
    Invariants:
        - phase_name must be non-empty
        - duration_seconds must be >= 0
        - If status is "failed", error_message must be non-None
        - If status is "success", error_message must be None
        - retry_count must be >= 0
    """
    phase_name: str
    status: PhaseResultStatus
    duration_seconds: int
    error_message: str | None
    retry_count: int
    
    def __post_init__(self) -> None:
        """Validate phase result."""
        if not self.phase_name or not self.phase_name.strip():
            raise ValueError("phase_name must be non-empty")
        
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")
        
        if self.status == "failed" and self.error_message is None:
            raise ValueError("status=failed requires non-None error_message")
        
        if self.status == "success" and self.error_message is not None:
            raise ValueError("status=success requires error_message=None")
        
        if self.retry_count < 0:
            raise ValueError("retry_count must be >= 0")
        
        # Normalize phase name
        object.__setattr__(self, "phase_name", self.phase_name.strip())
```

---

### TaskResult

**Purpose**: Complete outcome of processing one task through all phases.

**Source**: Key Entities in spec, FR-040

```python
from dataclasses import dataclass
from typing import Literal

TaskResultStatus = Literal["success", "failed", "skipped", "unprocessed"]

@dataclass(frozen=True)
class TaskResult:
    """Complete result of processing a single task.
    
    Attributes:
        task_file_path: Path to task file
        overall_status: Final status after all phases
        phase_results: List of results for each phase executed
        total_duration_seconds: Total time for all phases
        failure_reason: Description if overall_status is failed (None otherwise)
        
    Invariants:
        - task_file_path must be non-empty
        - total_duration_seconds must be >= 0
        - If overall_status is "success", all phase_results must have status "success"
        - If overall_status is "failed", at least one phase_result must have status "failed"
        - If overall_status is "failed", failure_reason must be non-None
        - If overall_status is not "failed", failure_reason must be None
        - If overall_status is "unprocessed", phase_results must be empty
    """
    task_file_path: str
    overall_status: TaskResultStatus
    phase_results: tuple[PhaseResult, ...]
    total_duration_seconds: int
    failure_reason: str | None
    
    def __post_init__(self) -> None:
        """Validate task result."""
        if not self.task_file_path or not self.task_file_path.strip():
            raise ValueError("task_file_path must be non-empty")
        
        if self.total_duration_seconds < 0:
            raise ValueError("total_duration_seconds must be >= 0")
        
        # Validate status-based invariants
        if self.overall_status == "success":
            if any(pr.status == "failed" for pr in self.phase_results):
                raise ValueError("overall_status=success cannot have failed phase_results")
        
        if self.overall_status == "failed":
            if not any(pr.status == "failed" for pr in self.phase_results):
                raise ValueError("overall_status=failed requires at least one failed phase_result")
            if self.failure_reason is None:
                raise ValueError("overall_status=failed requires non-None failure_reason")
        
        if self.overall_status != "failed" and self.failure_reason is not None:
            raise ValueError("failure_reason must be None when overall_status is not failed")
        
        if self.overall_status == "unprocessed" and self.phase_results:
            raise ValueError("overall_status=unprocessed requires empty phase_results")
        
        # Normalize path
        object.__setattr__(self, "task_file_path", self.task_file_path.strip())
```

---

### OrchestrationResult

**Purpose**: Final output of the orchestration workflow containing aggregated results.

**Source**: FR-004, FR-039, FR-041, FR-042, FR-043

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class OrchestrationResult:
    """Aggregated result of multi-task orchestration workflow.
    
    Attributes:
        total_tasks: Total number of tasks in input
        successful_tasks: Count of tasks with overall_status="success"
        failed_tasks: Count of tasks with overall_status="failed"
        skipped_tasks: Count of tasks with overall_status="skipped"
        unprocessed_tasks: Count of tasks with overall_status="unprocessed"
        task_results: List of results for each task (in input order)
        unprocessed_task_paths: Paths of tasks not attempted due to early termination
        early_termination: True if workflow stopped due to task failure
        total_duration_seconds: Total workflow execution time
        
    Invariants:
        - total_tasks must equal sum of successful_tasks, failed_tasks, skipped_tasks, and unprocessed_tasks
        - total_tasks must equal len(task_results) + len(unprocessed_task_paths)
        - If early_termination is True, unprocessed_tasks must be > 0
        - total_duration_seconds must be >= 0
        - All counts must be >= 0
    """
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    skipped_tasks: int
    unprocessed_tasks: int
    task_results: tuple[TaskResult, ...]
    unprocessed_task_paths: tuple[str, ...]
    early_termination: bool
    total_duration_seconds: int
    
    def __post_init__(self) -> None:
        """Validate orchestration result."""
        # Validate counts are non-negative
        if self.total_tasks < 0:
            raise ValueError("total_tasks must be >= 0")
        if self.successful_tasks < 0:
            raise ValueError("successful_tasks must be >= 0")
        if self.failed_tasks < 0:
            raise ValueError("failed_tasks must be >= 0")
        if self.skipped_tasks < 0:
            raise ValueError("skipped_tasks must be >= 0")
        if self.unprocessed_tasks < 0:
            raise ValueError("unprocessed_tasks must be >= 0")
        if self.total_duration_seconds < 0:
            raise ValueError("total_duration_seconds must be >= 0")
        
        # Validate count consistency
        sum_counts = (
            self.successful_tasks + 
            self.failed_tasks + 
            self.skipped_tasks + 
            self.unprocessed_tasks
        )
        if self.total_tasks != sum_counts:
            raise ValueError(
                f"total_tasks ({self.total_tasks}) must equal sum of status counts ({sum_counts})"
            )
        
        # Validate result list consistency
        total_results = len(self.task_results) + len(self.unprocessed_task_paths)
        if self.total_tasks != total_results:
            raise ValueError(
                f"total_tasks ({self.total_tasks}) must equal task_results + unprocessed_task_paths ({total_results})"
            )
        
        # Validate early termination invariant
        if self.early_termination and self.unprocessed_tasks == 0:
            raise ValueError("early_termination=True requires unprocessed_tasks > 0")
        
        # Verify actual counts match task_results
        actual_successful = sum(1 for tr in self.task_results if tr.overall_status == "success")
        actual_failed = sum(1 for tr in self.task_results if tr.overall_status == "failed")
        actual_skipped = sum(1 for tr in self.task_results if tr.overall_status == "skipped")
        
        if self.successful_tasks != actual_successful:
            raise ValueError(f"successful_tasks ({self.successful_tasks}) does not match actual count ({actual_successful})")
        if self.failed_tasks != actual_failed:
            raise ValueError(f"failed_tasks ({self.failed_tasks}) does not match actual count ({actual_failed})")
        if self.skipped_tasks != actual_skipped:
            raise ValueError(f"skipped_tasks ({self.skipped_tasks}) does not match actual count ({actual_skipped})")
```

---

## Internal State Models

### OrchestrationState

**Purpose**: Internal workflow state (not exposed in API, used for workflow variables).

**Note**: This is stored in workflow instance variables, not a separate dataclass. Documented here for completeness.

```python
# In workflow class __init__:
self._completed_task_indices: list[int] = []
self._task_results: list[TaskResult] = []
self._current_task_index: int = 0
self._current_phase: str | None = None
self._is_paused: bool = False
self._continue_event: asyncio.Event = asyncio.Event()
self._skip_current: bool = False
```

---

## Entity Relationships

```text
OrchestrationInput
    ↓ (defines)
OrchestrationWorkflow
    ↓ (tracks)
TaskProgress (per task)
    ↓ (accumulates)
PhaseResult (per phase)
    ↓ (aggregates into)
TaskResult (per task)
    ↓ (aggregates into)
OrchestrationResult
```

**Cardinality**:
- 1 OrchestrationInput → 1 OrchestrationWorkflow
- 1 OrchestrationWorkflow → N TaskProgress (one per task)
- 1 TaskProgress → M PhaseResult (one per phase)
- N TaskProgress → N TaskResult (one-to-one mapping)
- N TaskResult → 1 OrchestrationResult (aggregation)

---

## Validation Summary

All dataclasses follow Constitution requirements:

✅ **Frozen dataclasses**: All entities use `frozen=True` for immutability  
✅ **Post-init validation**: All invariants checked in `__post_init__`  
✅ **Literal types**: Status fields use `Literal` (not Enum)  
✅ **Clear error messages**: Validation errors include field name and expected value  
✅ **Timezone-aware datetimes**: Not used in these models (durations use int seconds)  
✅ **Tuple for sequences**: All sequence fields use `tuple` for immutability

---

## Usage Examples

### Creating workflow input:

```python
orchestration_input = OrchestrationInput(
    task_file_paths=("tasks/feature-001.md", "tasks/feature-002.md"),
    interactive_mode=False,
    retry_limit=3,
    repo_path="/workspace/myrepo",
    branch="main",
    default_model="gpt-4",
)
```

### Building task result:

```python
phase_results = (
    PhaseResult(
        phase_name="initialize",
        status="success",
        duration_seconds=45,
        error_message=None,
        retry_count=0,
    ),
    PhaseResult(
        phase_name="implement",
        status="failed",
        duration_seconds=120,
        error_message="Compilation error in generated code",
        retry_count=2,
    ),
)

task_result = TaskResult(
    task_file_path="tasks/feature-001.md",
    overall_status="failed",
    phase_results=phase_results,
    total_duration_seconds=165,
    failure_reason="Phase 'implement' failed after 2 retries: Compilation error",
)
```

### Building orchestration result:

```python
orchestration_result = OrchestrationResult(
    total_tasks=5,
    successful_tasks=2,
    failed_tasks=1,
    skipped_tasks=0,
    unprocessed_tasks=2,
    task_results=(task_result_1, task_result_2, task_result_3),
    unprocessed_task_paths=("tasks/feature-004.md", "tasks/feature-005.md"),
    early_termination=True,
    total_duration_seconds=3600,
)
```

---

## Type Definitions

All `Literal` type definitions for reference:

```python
TaskProgressStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
PhaseResultStatus = Literal["success", "failed"]
TaskResultStatus = Literal["success", "failed", "skipped", "unprocessed"]
```

These types provide IDE autocomplete and type checking while avoiding Enum serialization complexity.
