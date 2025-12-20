# Data Model: Core Workflow DSL

**Feature Branch**: `022-workflow-dsl`
**Date**: 2025-12-19
**Status**: Complete

This document defines the data models for the Workflow DSL, derived from the key entities in the specification and research decisions.

---

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              WORKFLOW EXECUTION                              │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────┐           ┌──────────────────┐
  │ WorkflowDefinition│◄──────────│   @workflow      │
  │                  │  creates  │   decorator      │
  │  - name          │           └──────────────────┘
  │  - description   │
  │  - parameters    │
  │  - func          │
  └────────┬─────────┘
           │ executed by
           ▼
  ┌──────────────────┐           ┌──────────────────┐
  │  WorkflowEngine  │◄──────────│  WorkflowContext │
  │                  │  uses     │                  │
  │  - execute()     │           │  - inputs        │
  │  - _emit_event() │           │  - results       │
  └────────┬─────────┘           │  - config        │
           │                     └──────────────────┘
           │ yields                      │
           ▼                             │ stores
  ┌──────────────────┐                   │
  │ StepDefinition   │◄──────────────────┘
  │ (abstract)       │
  │  - name          │
  │  - step_type     │
  │  - execute()     │
  │  - to_dict()     │
  └────────┬─────────┘
           │ subtypes
           ├──────────────┬──────────────┬──────────────┬──────────────┐
           ▼              ▼              ▼              ▼              ▼
  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │ PythonStep │  │ AgentStep  │  │GenerateStep│  │ValidateStep│  │SubWorkflow │
  │            │  │            │  │            │  │            │  │   Step     │
  │ - action   │  │ - agent    │  │ - generator│  │ - stages   │  │ - workflow │
  │ - args     │  │ - context  │  │ - context  │  │ - retry    │  │ - inputs   │
  │ - kwargs   │  │            │  │            │  │ - on_failure│ │            │
  └────────────┘  └────────────┘  └────────────┘  └────────────┘  └────────────┘
           │
           │ produces
           ▼
  ┌──────────────────┐
  │   StepResult     │
  │                  │
  │  - name          │
  │  - step_type     │
  │  - success       │
  │  - output        │
  │  - duration_ms   │
  │  - error         │
  └────────┬─────────┘
           │
           │ aggregated into
           ▼
  ┌──────────────────┐
  │ WorkflowResult   │
  │                  │
  │  - workflow_name │
  │  - success       │
  │  - step_results  │
  │  - total_duration│
  │  - final_output  │
  └──────────────────┘
```

---

## Core Entities

### 1. StepType (Enum)

**Purpose**: Categorizes step behavior for reporting and serialization (FR-012).

```python
from enum import Enum

class StepType(str, Enum):
    """Step type categorization."""
    PYTHON = "python"
    AGENT = "agent"
    GENERATE = "generate"
    VALIDATE = "validate"
    SUBWORKFLOW = "subworkflow"
```

| Value | Description | FR Reference |
|-------|-------------|--------------|
| `PYTHON` | Executes a Python callable | FR-006 |
| `AGENT` | Invokes a MaverickAgent | FR-007 |
| `GENERATE` | Invokes a GeneratorAgent | FR-008 |
| `VALIDATE` | Runs validation stages | FR-009 |
| `SUBWORKFLOW` | Executes another workflow | FR-011 |

---

### 2. WorkflowParameter

**Purpose**: Captured parameter metadata from workflow function signature (FR-003).

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import inspect

@dataclass(frozen=True, slots=True)
class WorkflowParameter:
    """Parameter metadata extracted from workflow function signature.

    Attributes:
        name: Parameter name from function signature.
        annotation: Type annotation if provided, else None.
        default: Default value if provided, else None.
        kind: Parameter kind (POSITIONAL_OR_KEYWORD, VAR_POSITIONAL, etc.).
    """
    name: str
    annotation: type | None
    default: Any
    kind: inspect._ParameterKind
```

**Validation Rules**:
- `name` must be non-empty
- `kind` must be a valid `inspect.Parameter` kind

---

### 3. WorkflowDefinition

**Purpose**: Metadata captured from decorated workflow function (FR-002).

```python
from dataclasses import dataclass
from typing import Callable, Generator, Any

@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """Workflow metadata captured by @workflow decorator.

    Attributes:
        name: Workflow identifier (unique).
        description: Human-readable workflow description.
        parameters: Captured function parameters.
        func: The decorated generator function.
    """
    name: str
    description: str
    parameters: tuple[WorkflowParameter, ...]
    func: Callable[..., Generator[Any, Any, Any]]
```

**Validation Rules**:
- `name` must be non-empty
- `func` must be a generator function (yields steps)

---

### 4. WorkflowContext

**Purpose**: Per-execution runtime context (FR-015, FR-016).

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class WorkflowContext:
    """Runtime context for workflow execution.

    Attributes:
        inputs: Workflow input parameters (read-only after creation).
        results: Completed step results keyed by step name (mutable during execution).
        config: Shared services/configuration needed by steps.
    """
    inputs: dict[str, Any]
    results: dict[str, StepResult] = field(default_factory=dict)
    config: Any = None  # MaverickConfig or similar

    def get_step_output(self, step_name: str) -> Any:
        """Access prior step output via results[step_name].output (FR-016)."""
        if step_name not in self.results:
            raise KeyError(f"Step '{step_name}' not found in results")
        return self.results[step_name].output
```

**Validation Rules**:
- `inputs` is immutable after workflow starts
- `results` keys must be unique (enforced by engine, FR-005)

**State Transitions**:
- Created at workflow start with inputs
- Results added as steps complete
- Passed to each step's execute() method

---

### 5. StepDefinition (Abstract Base)

**Purpose**: Base class for all step types (FR-012).

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class StepDefinition(ABC):
    """Abstract base for step definitions.

    All step types must implement execute() and to_dict().

    Attributes:
        name: Unique step name within workflow.
        step_type: Categorization for reporting.
    """
    name: str
    step_type: StepType

    @abstractmethod
    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute step and return result (FR-013)."""
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence (FR-014)."""
        ...
```

---

### 6. PythonStep

**Purpose**: Executes a Python callable (FR-006).

```python
from dataclasses import dataclass, field
from typing import Callable, Any

@dataclass(frozen=True, slots=True)
class PythonStep(StepDefinition):
    """Step that executes a Python callable.

    Attributes:
        name: Step name.
        action: Callable to execute.
        args: Positional arguments for action.
        kwargs: Keyword arguments for action.
        step_type: Always StepType.PYTHON.
    """
    name: str
    action: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    step_type: StepType = StepType.PYTHON

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute callable and return result."""
        # Implementation in engine.py
        ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "action": self.action.__name__,
            "args_count": len(self.args),
            "kwargs_keys": list(self.kwargs.keys()),
        }
```

**Validation Rules**:
- `action` must be callable
- If action is async, must be awaited

---

### 7. AgentStep

**Purpose**: Invokes a MaverickAgent with context (FR-007).

```python
from dataclasses import dataclass
from typing import Any, Union, Callable, Awaitable

# Type alias
ContextBuilder = Callable[[WorkflowContext], Awaitable[dict[str, Any]]]
StepContext = Union[dict[str, Any], ContextBuilder]

@dataclass(frozen=True, slots=True)
class AgentStep(StepDefinition):
    """Step that invokes a MaverickAgent.

    Attributes:
        name: Step name.
        agent: MaverickAgent instance or class.
        context: Static dict OR callable context builder.
        step_type: Always StepType.AGENT.
    """
    name: str
    agent: Any  # MaverickAgent[TContext, TResult]
    context: StepContext
    step_type: StepType = StepType.AGENT

    async def _resolve_context(self, workflow_context: WorkflowContext) -> dict[str, Any]:
        """Resolve static dict or invoke context builder."""
        if callable(self.context):
            return await self.context(workflow_context)
        return self.context

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Invoke agent with resolved context, return AgentResult."""
        # Implementation handles context builder failure as step failure
        ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "agent": self.agent.name if hasattr(self.agent, 'name') else str(type(self.agent).__name__),
            "context_type": "callable" if callable(self.context) else "static",
        }
```

**Validation Rules**:
- `agent` must have an `execute()` method
- Context builder must return dict (validated at runtime)
- Context builder failure treated as step failure (per clarification)

---

### 8. GenerateStep

**Purpose**: Invokes a GeneratorAgent with context (FR-008).

```python
@dataclass(frozen=True, slots=True)
class GenerateStep(StepDefinition):
    """Step that invokes a GeneratorAgent.

    Attributes:
        name: Step name.
        generator: GeneratorAgent instance.
        context: Static dict OR callable context builder.
        step_type: Always StepType.GENERATE.
    """
    name: str
    generator: Any  # GeneratorAgent
    context: StepContext
    step_type: StepType = StepType.GENERATE

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Invoke generator, return generated string as output."""
        ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "generator": self.generator.name if hasattr(self.generator, 'name') else str(type(self.generator).__name__),
            "context_type": "callable" if callable(self.context) else "static",
        }
```

---

### 9. ValidateStep

**Purpose**: Runs validation stages with retry logic (FR-009, FR-010).

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class ValidateStep(StepDefinition):
    """Step that runs validation stages.

    Attributes:
        name: Step name.
        stages: Explicit list, config key reference, or None for default.
        retry: Number of retry attempts (0 = no retries).
        on_failure: Optional step to run before each retry.
        step_type: Always StepType.VALIDATE.
    """
    name: str
    stages: list[str] | str | None = None
    retry: int = 3
    on_failure: StepDefinition | None = None
    step_type: StepType = StepType.VALIDATE

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Run validation with retry loop."""
        # Implementation:
        # 1. Resolve stages from config if None
        # 2. Loop: validate -> if fail and retries left -> run on_failure -> retry
        # 3. Return ValidationResult as output
        ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "stages": self.stages,
            "retry": self.retry,
            "has_on_failure": self.on_failure is not None,
        }
```

**Validation Rules**:
- `retry` must be >= 0
- If `stages` is string, must exist in config (fail-fast per clarification)
- `retry=0` means no retries, on_failure never runs

**State Transitions**:
```
validate() -> [PASS] -> StepResult(success=True)
           -> [FAIL, retry=0] -> StepResult(success=False)
           -> [FAIL, retry>0] -> on_failure() -> validate() -> ...
           -> [FAIL, retries exhausted] -> StepResult(success=False)
```

---

### 10. SubWorkflowStep

**Purpose**: Executes another workflow as a step (FR-011).

```python
@dataclass(frozen=True, slots=True)
class SubWorkflowStep(StepDefinition):
    """Step that executes a sub-workflow.

    Attributes:
        name: Step name.
        workflow: Workflow object or decorated workflow function.
        inputs: Input arguments for sub-workflow.
        step_type: Always StepType.SUBWORKFLOW.
    """
    name: str
    workflow: Any  # WorkflowDefinition or decorated function
    inputs: dict[str, Any] = field(default_factory=dict)
    step_type: StepType = StepType.SUBWORKFLOW

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute sub-workflow, return SubWorkflowInvocationResult."""
        ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "workflow": getattr(self.workflow, '__workflow_def__', self.workflow).name
                if hasattr(self.workflow, '__workflow_def__') else str(self.workflow),
            "inputs_keys": list(self.inputs.keys()),
        }
```

---

### 11. StepResult

**Purpose**: Per-step execution record (FR-013).

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class StepResult:
    """Result of executing a single workflow step.

    Attributes:
        name: Step name (matches StepDefinition.name).
        step_type: Step type for categorization.
        success: True if step succeeded.
        output: Step output value (varies by step type).
        duration_ms: Execution time in milliseconds.
        error: Human-readable error string on failure.
    """
    name: str
    step_type: StepType
    success: bool
    output: Any
    duration_ms: int
    error: str | None = None

    def __post_init__(self) -> None:
        """Validate invariants."""
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if not self.success and self.error is None:
            raise ValueError("Failed steps must have an error message (FR-022)")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence (FR-014)."""
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "success": self.success,
            "output": self._serialize_output(),
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    def _serialize_output(self) -> Any:
        """Handle complex output types safely."""
        if hasattr(self.output, 'to_dict'):
            return self.output.to_dict()
        if isinstance(self.output, (str, int, float, bool, type(None))):
            return self.output
        if isinstance(self.output, (list, tuple)):
            return [self._serialize_item(item) for item in self.output]
        if isinstance(self.output, dict):
            return {k: self._serialize_item(v) for k, v in self.output.items()}
        return str(self.output)

    def _serialize_item(self, item: Any) -> Any:
        if hasattr(item, 'to_dict'):
            return item.to_dict()
        return str(item) if not isinstance(item, (str, int, float, bool, type(None))) else item
```

---

### 12. SubWorkflowInvocationResult

**Purpose**: Output of a sub-workflow step (FR-011).

```python
@dataclass(frozen=True, slots=True)
class SubWorkflowInvocationResult:
    """Result from executing a sub-workflow.

    Exposes both final output and full workflow result to parent.

    Attributes:
        final_output: The sub-workflow's final output (per FR-021).
        workflow_result: Full WorkflowResult for detailed inspection.
    """
    final_output: Any
    workflow_result: WorkflowResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_output": str(self.final_output),
            "workflow_name": self.workflow_result.workflow_name,
            "success": self.workflow_result.success,
            "step_count": len(self.workflow_result.step_results),
        }
```

---

### 13. WorkflowResult

**Purpose**: Per-workflow execution record (FR-020).

```python
@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Complete workflow execution result.

    Attributes:
        workflow_name: Name from WorkflowDefinition.
        success: True if all steps succeeded.
        step_results: Ordered list of all step results.
        total_duration_ms: Total execution time.
        final_output: Workflow's final output (per FR-021).
    """
    workflow_name: str
    success: bool
    step_results: tuple[StepResult, ...]
    total_duration_ms: int
    final_output: Any

    def __post_init__(self) -> None:
        if self.total_duration_ms < 0:
            raise ValueError("total_duration_ms must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_name": self.workflow_name,
            "success": self.success,
            "step_results": [sr.to_dict() for sr in self.step_results],
            "total_duration_ms": self.total_duration_ms,
            "final_output": str(self.final_output),
        }

    @property
    def failed_step(self) -> StepResult | None:
        """Return the first failed step, if any."""
        for result in self.step_results:
            if not result.success:
                return result
        return None
```

---

## Progress Event Entities

### 14. StepStarted

**Purpose**: Emitted when a step begins (FR-019).

```python
from dataclasses import dataclass, field
import time

@dataclass(frozen=True, slots=True)
class StepStarted:
    """Progress event: step execution started."""
    step_name: str
    step_type: StepType
    timestamp: float = field(default_factory=time.time)
```

### 15. StepCompleted

**Purpose**: Emitted when a step finishes (FR-019).

```python
@dataclass(frozen=True, slots=True)
class StepCompleted:
    """Progress event: step execution completed."""
    step_name: str
    step_type: StepType
    success: bool
    duration_ms: int
    timestamp: float = field(default_factory=time.time)
```

### 16. WorkflowStarted

**Purpose**: Emitted when workflow begins.

```python
@dataclass(frozen=True, slots=True)
class WorkflowStarted:
    """Progress event: workflow execution started."""
    workflow_name: str
    inputs: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
```

### 17. WorkflowCompleted

**Purpose**: Emitted when workflow finishes.

```python
@dataclass(frozen=True, slots=True)
class WorkflowCompleted:
    """Progress event: workflow execution completed."""
    workflow_name: str
    success: bool
    total_duration_ms: int
    timestamp: float = field(default_factory=time.time)
```

### ProgressEvent Type

```python
ProgressEvent = StepStarted | StepCompleted | WorkflowStarted | WorkflowCompleted
```

---

## Type Aliases

```python
from typing import Union, Callable, Awaitable, Any

# Context builder for agent/generate steps
ContextBuilder = Callable[[WorkflowContext], Awaitable[dict[str, Any]]]

# Context can be static dict or builder callable
StepContext = Union[dict[str, Any], ContextBuilder]

# Union of all step types
AnyStep = PythonStep | AgentStep | GenerateStep | ValidateStep | SubWorkflowStep

# Progress event union
ProgressEvent = StepStarted | StepCompleted | WorkflowStarted | WorkflowCompleted
```

---

## Relationships Summary

| Entity | Relationship | Target | Cardinality |
|--------|--------------|--------|-------------|
| WorkflowDefinition | contains | WorkflowParameter | 1:N |
| WorkflowDefinition | references | func (generator) | 1:1 |
| WorkflowContext | stores | StepResult | 1:N |
| WorkflowContext | has | inputs | 1:1 |
| StepDefinition | produces | StepResult | 1:1 |
| ValidateStep | optionally has | on_failure step | 1:0..1 |
| SubWorkflowStep | references | workflow | 1:1 |
| SubWorkflowInvocationResult | contains | WorkflowResult | 1:1 |
| WorkflowResult | aggregates | StepResult | 1:N |
