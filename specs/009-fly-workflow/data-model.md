# Data Model: Fly Workflow Interface

**Feature**: 009-fly-workflow
**Date**: 2025-12-15

## Entity Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Fly Workflow Types                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │ FlyInputs   │────▶│ FlyWorkflow │────▶│  FlyResult  │               │
│  │ (Pydantic)  │     │  (class)    │     │ (Pydantic)  │               │
│  └─────────────┘     └──────┬──────┘     └──────┬──────┘               │
│                             │                   │                       │
│                             │ config            │ state                 │
│                             ▼                   ▼                       │
│                      ┌─────────────┐     ┌──────────────┐              │
│                      │  FlyConfig  │     │WorkflowState │              │
│                      │ (Pydantic)  │     │ (Pydantic)   │              │
│                      └─────────────┘     └──────┬───────┘              │
│                                                 │                       │
│                                                 │ stage                 │
│                                                 ▼                       │
│                                          ┌──────────────┐              │
│                                          │WorkflowStage │              │
│                                          │   (Enum)     │              │
│                                          └──────────────┘              │
│                                                                         │
│  Progress Events (dataclasses):                                        │
│  ┌────────────────────┐  ┌─────────────────┐  ┌──────────────────┐    │
│  │FlyWorkflowStarted  │  │FlyStageStarted  │  │FlyStageCompleted │    │
│  └────────────────────┘  └─────────────────┘  └──────────────────┘    │
│  ┌─────────────────────┐  ┌────────────────────┐                      │
│  │FlyWorkflowCompleted │  │FlyWorkflowFailed   │                      │
│  └─────────────────────┘  └────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Enums

### WorkflowStage

Represents the eight possible stages of the fly workflow (FR-001, FR-002).

```python
class WorkflowStage(str, Enum):
    """Eight workflow stages with string representation."""

    INIT = "init"                       # Parse args, validate inputs, checkout branch
    IMPLEMENTATION = "implementation"   # Execute ImplementerAgent on tasks
    VALIDATION = "validation"           # Run ValidationWorkflow (format/lint/test)
    CODE_REVIEW = "code_review"         # Parallel code reviews
    CONVENTION_UPDATE = "convention_update"  # Analyze and update CLAUDE.md
    PR_CREATION = "pr_creation"         # Generate and create/update PR
    COMPLETE = "complete"               # Terminal: successful completion
    FAILED = "failed"                   # Terminal: workflow failed
```

| Value | String | Terminal | Description |
|-------|--------|----------|-------------|
| INIT | "init" | No | Initial setup and validation |
| IMPLEMENTATION | "implementation" | No | Task execution phase |
| VALIDATION | "validation" | No | Code quality checks |
| CODE_REVIEW | "code_review" | No | Code review phase |
| CONVENTION_UPDATE | "convention_update" | No | Convention updates |
| PR_CREATION | "pr_creation" | No | PR creation phase |
| COMPLETE | "complete" | Yes | Successful completion |
| FAILED | "failed" | Yes | Failure state |

---

## Configuration Models (Pydantic)

### FlyInputs

Input parameters for starting a fly workflow (FR-003, FR-004, FR-005).

```python
class FlyInputs(BaseModel):
    """Validated inputs for fly workflow execution."""

    model_config = ConfigDict(frozen=True)

    # Required
    branch_name: str = Field(min_length=1, description="Feature branch name")

    # Optional with defaults
    task_file: Path | None = Field(default=None, description="Path to tasks.md")
    skip_review: bool = Field(default=False, description="Skip code review stage")
    skip_pr: bool = Field(default=False, description="Skip PR creation stage")
    draft_pr: bool = Field(default=False, description="Create PR as draft")
    base_branch: str = Field(default="main", description="Base branch for PR")
```

| Field | Type | Required | Default | Validation |
|-------|------|----------|---------|------------|
| branch_name | str | Yes | - | min_length=1 |
| task_file | Path \| None | No | None | - |
| skip_review | bool | No | False | - |
| skip_pr | bool | No | False | - |
| draft_pr | bool | No | False | - |
| base_branch | str | No | "main" | - |

### FlyConfig

Configuration options for fly workflow behavior (FR-021, FR-022, FR-023).

```python
class FlyConfig(BaseModel):
    """Configuration for fly workflow execution."""

    model_config = ConfigDict(frozen=True)

    parallel_reviews: bool = Field(default=True, description="Run reviews in parallel")
    max_validation_attempts: int = Field(default=3, ge=1, le=10, description="Max validation retries")
    coderabbit_enabled: bool = Field(default=False, description="Enable CodeRabbit CLI")
    auto_merge: bool = Field(default=False, description="Auto-merge on success")
    notification_on_complete: bool = Field(default=True, description="Send notification on completion")
```

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| parallel_reviews | bool | True | - | Enable parallel code reviews |
| max_validation_attempts | int | 3 | 1-10 | Maximum validation retry attempts |
| coderabbit_enabled | bool | False | - | Integrate CodeRabbit CLI |
| auto_merge | bool | False | - | Auto-merge PR on success |
| notification_on_complete | bool | True | - | Send ntfy notification |

---

## State Models (Pydantic)

### WorkflowState

Mutable state container tracking workflow execution (FR-006, FR-007, FR-008).

```python
class WorkflowState(BaseModel):
    """Mutable state tracking workflow progress."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Stage tracking
    stage: WorkflowStage = Field(default=WorkflowStage.INIT)
    branch: str = Field(description="Current branch name")
    task_file: Path | None = Field(default=None)

    # Results (populated as stages complete)
    implementation_result: AgentResult | None = Field(default=None)
    validation_result: ValidationWorkflowResult | None = Field(default=None)
    review_results: list[AgentResult] = Field(default_factory=list)

    # Final outputs
    pr_url: str | None = Field(default=None)
    errors: list[str] = Field(default_factory=list)

    # Timestamps
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = Field(default=None)
```

| Field | Type | Mutable | Description |
|-------|------|---------|-------------|
| stage | WorkflowStage | Yes | Current workflow stage |
| branch | str | No | Branch being worked on |
| task_file | Path \| None | No | Tasks file path |
| implementation_result | AgentResult \| None | Yes | Implementation stage result |
| validation_result | ValidationWorkflowResult \| None | Yes | Validation stage result |
| review_results | list[AgentResult] | Yes | Code review results (appended) |
| pr_url | str \| None | Yes | Created PR URL |
| errors | list[str] | Yes | Accumulated error messages |
| started_at | datetime | No | Workflow start time |
| completed_at | datetime \| None | Yes | Workflow completion time |

---

## Result Models (Pydantic)

### FlyResult

Immutable result returned after workflow completion (FR-009, FR-010, FR-011).

```python
class FlyResult(BaseModel):
    """Immutable workflow execution result."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    success: bool = Field(description="Overall workflow success")
    state: WorkflowState = Field(description="Final workflow state")
    summary: str = Field(description="Human-readable outcome summary")
    token_usage: AgentUsage = Field(description="Aggregated token usage")
    total_cost_usd: float = Field(ge=0.0, description="Total execution cost")
```

| Field | Type | Description |
|-------|------|-------------|
| success | bool | True if workflow completed successfully |
| state | WorkflowState | Final state snapshot |
| summary | str | Human-readable summary text |
| token_usage | AgentUsage | Aggregated usage from all agents |
| total_cost_usd | float | Total cost in USD |

**Summary Format Examples**:
- Success: "Fly workflow completed: 5 tasks implemented, validation passed, PR #123 created"
- Failure: "Fly workflow failed at VALIDATION stage: 2 lint errors could not be fixed"

---

## Progress Events (Dataclasses)

### FlyWorkflowStarted

Emitted when workflow execution begins (FR-012).

```python
@dataclass(frozen=True, slots=True)
class FlyWorkflowStarted:
    """Event emitted when fly workflow starts."""

    inputs: FlyInputs
    timestamp: float = field(default_factory=time.time)
```

### FlyStageStarted

Emitted when a stage begins execution (FR-013).

```python
@dataclass(frozen=True, slots=True)
class FlyStageStarted:
    """Event emitted when a stage starts."""

    stage: WorkflowStage
    timestamp: float = field(default_factory=time.time)
```

### FlyStageCompleted

Emitted when a stage finishes (FR-014).

```python
@dataclass(frozen=True, slots=True)
class FlyStageCompleted:
    """Event emitted when a stage completes."""

    stage: WorkflowStage
    result: Any  # Stage-specific result type
    timestamp: float = field(default_factory=time.time)
```

### FlyWorkflowCompleted

Emitted when workflow finishes successfully (FR-015).

```python
@dataclass(frozen=True, slots=True)
class FlyWorkflowCompleted:
    """Event emitted when workflow completes successfully."""

    result: FlyResult
    timestamp: float = field(default_factory=time.time)
```

### FlyWorkflowFailed

Emitted when workflow fails (FR-016).

```python
@dataclass(frozen=True, slots=True)
class FlyWorkflowFailed:
    """Event emitted when workflow fails."""

    error: str
    state: WorkflowState
    timestamp: float = field(default_factory=time.time)
```

---

## Progress Event Union Type

For type-safe event handling:

```python
FlyProgressEvent = (
    FlyWorkflowStarted
    | FlyStageStarted
    | FlyStageCompleted
    | FlyWorkflowCompleted
    | FlyWorkflowFailed
)
```

---

## Workflow Class

### FlyWorkflow

Main workflow class with stub implementation (FR-017, FR-018, FR-019, FR-020).

```python
class FlyWorkflow:
    """Fly workflow orchestrator.

    Orchestrates the complete fly workflow from spec to PR:

    **INIT Stage**: Parse command-line arguments, validate inputs, create or
    checkout the feature branch, and load the task specification file if
    provided. Syncs branch with origin/main.

    **IMPLEMENTATION Stage**: Execute the ImplementerAgent on tasks defined
    in tasks.md. Tasks marked with "P:" prefix are executed in parallel.
    Each task completion results in atomic commits.

    **VALIDATION Stage**: Run the ValidationWorkflow (format, lint, typecheck,
    test) with auto-fix capabilities. Retries up to max_validation_attempts
    with fix agent for fixable issues.

    **CODE_REVIEW Stage**: Run parallel code reviews if enabled. Optionally
    integrates CodeRabbit CLI for enhanced review. Collects review comments
    and suggestions.

    **CONVENTION_UPDATE Stage**: Analyze implementation findings and review
    feedback. Suggest updates to CLAUDE.md if significant learnings or
    patterns were discovered.

    **PR_CREATION Stage**: Generate pull request body from implementation
    results and review findings. Create or update PR via GitHub CLI.
    Optionally marks PR as draft.

    **COMPLETE Stage**: Terminal state indicating successful workflow
    completion. All stages passed and PR is ready.

    **FAILED Stage**: Terminal state indicating workflow failure.
    WorkflowState.errors contains reasons for failure.

    Note:
        This interface is defined in Spec 009. Full implementation will be
        provided in Spec 26 using the workflow DSL.
    """

    def __init__(self, config: FlyConfig | None = None) -> None:
        """Initialize the fly workflow.

        Args:
            config: Optional workflow configuration. Uses defaults if None.
        """
        self._config = config or FlyConfig()

    async def execute(self, inputs: FlyInputs) -> FlyResult:
        """Execute the fly workflow.

        Args:
            inputs: Validated workflow inputs including branch name and options.

        Returns:
            FlyResult containing success status, final state, and summary.

        Raises:
            NotImplementedError: Always raised - implementation in Spec 26.
        """
        raise NotImplementedError(
            "FlyWorkflow.execute() is not implemented. "
            "Full implementation will be provided in Spec 26 using the workflow DSL."
        )
```

---

## Type Dependencies

### External Types (imported from existing modules)

| Type | Module | Usage |
|------|--------|-------|
| AgentResult | maverick.agents.result | Implementation/review results |
| AgentUsage | maverick.agents.result | Token/cost tracking |
| ValidationWorkflowResult | maverick.models.validation | Validation stage result |
| Path | pathlib | File paths |
| datetime | datetime | Timestamps |

---

## MaverickConfig Integration

FlyConfig integrates into the existing configuration hierarchy:

```python
# In maverick/config.py

class MaverickConfig(BaseSettings):
    # ... existing fields ...
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    parallel: ParallelConfig = Field(default_factory=ParallelConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    verbosity: Literal["error", "warning", "info", "debug"] = "warning"

    # NEW: Fly workflow configuration
    fly: FlyConfig = Field(default_factory=FlyConfig)
```

---

## Validation Rules

### FlyInputs Validation

1. `branch_name` must be non-empty (min_length=1)
2. `task_file` path validation deferred to runtime (Spec 26)

### FlyConfig Validation

1. `max_validation_attempts` must be 1-10 (ge=1, le=10)

### WorkflowState Validation

1. `errors` list accumulates chronologically (append-only semantics)
2. `completed_at` must be None until workflow reaches terminal state

### FlyResult Validation

1. `total_cost_usd` must be non-negative (ge=0.0)
2. `summary` must be human-readable (no structured data)
