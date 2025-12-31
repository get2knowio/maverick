# Public API Contract: Core Workflow DSL

**Feature Branch**: `022-workflow-dsl`
**Date**: 2025-12-19
**Status**: Complete

This document defines the public API contract for the Workflow DSL module (`maverick.dsl`).

---

## Module Structure

```python
# maverick/dsl/__init__.py - Public API exports

from maverick.dsl.decorator import workflow
from maverick.dsl.builder import step
from maverick.dsl.types import StepType
from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import (
    StepResult,
    WorkflowResult,
    SubWorkflowInvocationResult,
)
from maverick.dsl.steps import (
    StepDefinition,
    PythonStep,
    AgentStep,
    GenerateStep,
    ValidateStep,
    SubWorkflowStep,
)
from maverick.dsl.events import (
    StepStarted,
    StepCompleted,
    WorkflowStarted,
    WorkflowCompleted,
    ProgressEvent,
)
from maverick.dsl.engine import WorkflowEngine

__all__ = [
    # Decorator
    "workflow",
    # Builder
    "step",
    # Types
    "StepType",
    # Context
    "WorkflowContext",
    # Results
    "StepResult",
    "WorkflowResult",
    "SubWorkflowInvocationResult",
    # Steps
    "StepDefinition",
    "PythonStep",
    "AgentStep",
    "GenerateStep",
    "ValidateStep",
    "SubWorkflowStep",
    # Events
    "StepStarted",
    "StepCompleted",
    "WorkflowStarted",
    "WorkflowCompleted",
    "ProgressEvent",
    # Engine
    "WorkflowEngine",
]
```

---

## 1. Workflow Decorator

### `@workflow(name, description="")`

Decorates a generator function to create an executable workflow.

```python
def workflow(
    name: str,
    description: str = "",
) -> Callable[[Callable[P, Generator[StepDefinition, Any, R]]], Callable[P, WorkflowResult]]:
    """Create a workflow from a generator function.

    The decorated function must be a generator that yields StepDefinition objects.
    The workflow decorator captures function signature metadata and creates an
    executable workflow.

    Args:
        name: Unique workflow identifier.
        description: Human-readable workflow description.

    Returns:
        Decorator that transforms generator function into executable workflow.

    Example:
        @workflow(name="my-workflow", description="Does something useful")
        def my_workflow(input_data: str) -> dict[str, Any]:
            result = yield step("process").python(action=process, args=(input_data,))
            return {"processed": result}

    Raises:
        ValueError: If name is empty.
        TypeError: If decorated function is not a generator.
    """
```

**Contract**:
- Input: Generator function that yields `StepDefinition` objects
- Output: Callable that returns `WorkflowResult`
- Side effect: Attaches `__workflow_def__` attribute to wrapper

---

## 2. Step Builder

### `step(name)`

Creates a step builder for defining workflow steps.

```python
def step(name: str) -> StepBuilder:
    """Create a step builder with the given name.

    Args:
        name: Unique step name within the workflow.

    Returns:
        StepBuilder instance for fluent step configuration.

    Raises:
        ValueError: If name is empty.

    Example:
        result = yield step("validate").python(action=validate, args=(data,))
    """
```

### `StepBuilder` Class

```python
class StepBuilder:
    """Fluent builder for creating step definitions."""

    def python(
        self,
        action: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> PythonStep:
        """Create a Python step that executes a callable.

        Args:
            action: Callable to execute (sync or async).
            args: Positional arguments for action.
            kwargs: Keyword arguments for action.

        Returns:
            PythonStep definition.
        """

    def agent(
        self,
        agent: MaverickAgent[Any, Any],
        context: dict[str, Any] | ContextBuilder,
    ) -> AgentStep:
        """Create an agent step that invokes a MaverickAgent.

        Args:
            agent: MaverickAgent instance.
            context: Static dict OR async callable that builds context.

        Returns:
            AgentStep definition.
        """

    def generate(
        self,
        generator: GeneratorAgent,
        context: dict[str, Any] | ContextBuilder,
    ) -> GenerateStep:
        """Create a generate step that invokes a GeneratorAgent.

        Args:
            generator: GeneratorAgent instance.
            context: Static dict OR async callable that builds context.

        Returns:
            GenerateStep definition.
        """

    def validate(
        self,
        stages: list[str] | str | None = None,
        retry: int = 3,
        on_failure: StepDefinition | None = None,
    ) -> ValidateStep:
        """Create a validate step that runs validation stages.

        Args:
            stages: List of stage names, config key, or None for default.
            retry: Number of retry attempts (0 = no retries).
            on_failure: Optional step to run before each retry.

        Returns:
            ValidateStep definition.
        """

    def subworkflow(
        self,
        workflow: Callable[..., WorkflowResult],
        inputs: dict[str, Any] | None = None,
    ) -> SubWorkflowStep:
        """Create a sub-workflow step.

        Args:
            workflow: Workflow function (decorated with @workflow).
            inputs: Input arguments for sub-workflow.

        Returns:
            SubWorkflowStep definition.
        """
```

---

## 3. Context Builder Type

### `ContextBuilder`

Type alias for async context builder callables.

```python
ContextBuilder = Callable[[WorkflowContext], Awaitable[dict[str, Any]]]
```

**Contract**:
- Input: `WorkflowContext` with inputs and prior step results
- Output: `dict[str, Any]` for step context
- On exception: Treated as step failure (StepResult with success=False)

**Example**:
```python
async def build_review_context(ctx: WorkflowContext) -> dict[str, Any]:
    impl_result = ctx.results["implementation"].output
    return {
        "files": impl_result.files,
        "branch": ctx.inputs["branch_name"],
    }
```

---

## 4. Workflow Engine

### `WorkflowEngine`

Executes workflows and emits progress events.

```python
class WorkflowEngine:
    """Workflow execution engine.

    Executes workflow definitions, manages context, and emits progress events
    for TUI consumption.
    """

    def __init__(
        self,
        config: MaverickConfig | None = None,
        validation_runner: ValidationRunner | None = None,
    ) -> None:
        """Initialize the workflow engine.

        Args:
            config: Optional configuration for validation stages, etc.
            validation_runner: Optional validation runner for validate steps.
        """

    async def execute(
        self,
        workflow_func: Callable[..., WorkflowResult],
        **inputs: Any,
    ) -> AsyncIterator[ProgressEvent]:
        """Execute a workflow and yield progress events.

        Args:
            workflow_func: Decorated workflow function.
            **inputs: Workflow input arguments.

        Yields:
            ProgressEvent objects (WorkflowStarted, StepStarted, StepCompleted, WorkflowCompleted).

        Note:
            Consume the entire iterator to complete workflow execution.
            Call get_result() after iteration to retrieve WorkflowResult.
        """

    def get_result(self) -> WorkflowResult:
        """Get the final workflow result.

        Returns:
            WorkflowResult with success status and step results.

        Raises:
            RuntimeError: If called before execute() completes.
        """

    def cancel(self) -> None:
        """Request workflow cancellation.

        Cancellation is cooperative and takes effect at step boundaries.
        """
```

---

## 5. Result Types

### `StepResult`

```python
@dataclass(frozen=True, slots=True)
class StepResult:
    """Result of executing a single workflow step."""
    name: str
    step_type: StepType
    success: bool
    output: Any
    duration_ms: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]: ...
```

**Invariants**:
- `duration_ms >= 0`
- If `success=False`, `error` must be non-None

### `WorkflowResult`

```python
@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Complete workflow execution result."""
    workflow_name: str
    success: bool
    step_results: tuple[StepResult, ...]
    total_duration_ms: int
    final_output: Any

    def to_dict(self) -> dict[str, Any]: ...

    @property
    def failed_step(self) -> StepResult | None: ...
```

### `SubWorkflowInvocationResult`

```python
@dataclass(frozen=True, slots=True)
class SubWorkflowInvocationResult:
    """Result from executing a sub-workflow."""
    final_output: Any
    workflow_result: WorkflowResult

    def to_dict(self) -> dict[str, Any]: ...
```

---

## 6. Progress Events

### Event Types

```python
@dataclass(frozen=True, slots=True)
class WorkflowStarted:
    workflow_name: str
    inputs: dict[str, Any]
    timestamp: float

@dataclass(frozen=True, slots=True)
class StepStarted:
    step_name: str
    step_type: StepType
    timestamp: float

@dataclass(frozen=True, slots=True)
class StepCompleted:
    step_name: str
    step_type: StepType
    success: bool
    duration_ms: int
    timestamp: float

@dataclass(frozen=True, slots=True)
class WorkflowCompleted:
    workflow_name: str
    success: bool
    total_duration_ms: int
    timestamp: float

ProgressEvent = WorkflowStarted | StepStarted | StepCompleted | WorkflowCompleted
```

---

## 7. WorkflowContext

### Public Interface

```python
@dataclass
class WorkflowContext:
    """Runtime context for workflow execution."""
    inputs: dict[str, Any]  # Read-only workflow inputs
    results: dict[str, StepResult]  # Completed step results
    config: Any  # Shared configuration

    def get_step_output(self, step_name: str) -> Any:
        """Get output from a prior step.

        Args:
            step_name: Name of the completed step.

        Returns:
            The step's output value.

        Raises:
            KeyError: If step not found in results.
        """
```

---

## 8. Error Handling Contract

### Exception Hierarchy

```python
# All DSL errors inherit from MaverickError

class WorkflowError(MaverickError):
    """Base class for workflow DSL errors."""
    pass

class DuplicateStepNameError(WorkflowError):
    """Raised when two steps share the same name (FR-005)."""
    step_name: str

class StagesNotFoundError(WorkflowError):
    """Raised when validate step references unknown stages config (clarification)."""
    config_key: str

class ContextBuilderError(WorkflowError):
    """Raised when context builder fails or returns invalid type."""
    step_name: str
    original_error: Exception
```

### Error Behavior

| Scenario | Behavior | FR Reference |
|----------|----------|--------------|
| Step raises exception | Catch, record failed StepResult, stop workflow | FR-022 |
| Duplicate step name | Stop workflow with DuplicateStepNameError | FR-005 |
| Context builder fails | Treat as step failure, record error | Clarification |
| Validation stages not found | Step failure with StagesNotFoundError | Clarification |
| Sub-workflow fails | Parent step fails, parent workflow stops | Clarification |

---

## 9. Usage Example

```python
from maverick.dsl import workflow, step, WorkflowEngine
from maverick.agents import ImplementerAgent, ReviewerAgent

@workflow(name="feature-impl", description="Implement a feature from spec")
async def feature_workflow(spec_path: str, branch: str):
    """Workflow that implements and reviews a feature."""

    # Python step
    parsed = yield step("parse_spec").python(
        action=parse_spec_file,
        args=(spec_path,),
    )

    # Agent step with static context
    impl_result = yield step("implement").agent(
        agent=ImplementerAgent(),
        context={"spec": parsed, "branch": branch},
    )

    # Agent step with context builder
    async def build_review_context(ctx):
        return {
            "files": ctx.results["implement"].output.files,
            "spec": ctx.inputs["spec_path"],
        }

    review_result = yield step("review").agent(
        agent=ReviewerAgent(),
        context=build_review_context,
    )

    # Validate step with retry
    yield step("validate").validate(
        stages=["lint", "test"],
        retry=3,
        on_failure=step("fix").agent(
            agent=FixerAgent(),
            context=lambda ctx: {"errors": ctx.results["validate"].output.errors},
        ),
    )

    return {
        "implementation": impl_result,
        "review": review_result,
    }


# Execution
async def main():
    engine = WorkflowEngine()

    async for event in engine.execute(feature_workflow, spec_path="spec.md", branch="feature-123"):
        print(f"Event: {type(event).__name__} - {event}")

    result = engine.get_result()
    print(f"Workflow {'succeeded' if result.success else 'failed'}")
    print(f"Final output: {result.final_output}")
```

---

## 10. Compatibility Notes

### Integration with Existing Agents

The DSL is compatible with existing Maverick agents:
- `MaverickAgent` instances work directly with `AgentStep`
- `GeneratorAgent` instances work directly with `GenerateStep`
- Agent results are stored in `StepResult.output`

### Migration Path

Existing workflows (`FlyWorkflow`, `RefuelWorkflow`) can optionally migrate to the DSL:
- DSL provides a standardized step model
- Existing workflows remain functional (no breaking changes)
- Gradual migration is supported

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-19 | Initial API contract |
