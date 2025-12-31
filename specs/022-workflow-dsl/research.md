# Research: Core Workflow DSL

**Feature Branch**: `022-workflow-dsl`
**Date**: 2025-12-19
**Status**: Complete

## Research Questions

This document consolidates research findings for the Workflow DSL implementation, addressing key design decisions and technical patterns.

---

## 1. Workflow Decorator with Signature Inspection

### Decision: Use `inspect.signature()` with `ParamSpec` for type-safe decorator

### Rationale

The `@workflow(name, description="")` decorator must capture function signature metadata (parameter names, types, defaults) per FR-002 and FR-003. The recommended approach:

```python
from __future__ import annotations
import functools
import inspect
from typing import TypeVar, ParamSpec, Callable, Any, Generator
from dataclasses import dataclass

P = ParamSpec('P')
R = TypeVar('R')

@dataclass(frozen=True, slots=True)
class WorkflowParameter:
    """Captured parameter metadata from workflow function signature."""
    name: str
    annotation: type | None
    default: Any
    kind: inspect._ParameterKind

@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """Metadata captured from decorated workflow function."""
    name: str
    description: str
    parameters: tuple[WorkflowParameter, ...]
    func: Callable[..., Generator[Any, Any, Any]]

def workflow(
    name: str,
    description: str = ""
) -> Callable[[Callable[P, Generator[Any, Any, R]]], Callable[P, R]]:
    """Decorator that captures workflow metadata."""
    def decorator(func: Callable[P, Generator[Any, Any, R]]) -> Callable[P, R]:
        sig = inspect.signature(func)
        parameters = tuple(
            WorkflowParameter(
                name=param_name,
                annotation=param.annotation if param.annotation != inspect.Parameter.empty else None,
                default=param.default if param.default != inspect.Parameter.empty else None,
                kind=param.kind,
            )
            for param_name, param in sig.parameters.items()
        )

        workflow_def = WorkflowDefinition(
            name=name,
            description=description,
            parameters=parameters,
            func=func,
        )

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            return _execute_workflow(workflow_def, bound_args.arguments)

        wrapper.__workflow_def__ = workflow_def  # type: ignore[attr-defined]
        return wrapper
    return decorator
```

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| `getargspec()` / `getfullargspec()` | Deprecated; `inspect.signature()` is the modern standard |
| Runtime signature parsing (per-call) | Performance overhead; signature doesn't change after decoration |
| Class-based workflow definition | Less Pythonic; decorator pattern matches Prefect/Dagster idioms |

### Sources

- [Python inspect.signature documentation](https://docs.python.org/3/library/inspect.html)
- [ParamSpec Guide (PEP 612)](https://sobolevn.me/2021/12/paramspec-guide)
- [Decorator JITs - Python as a DSL](https://eli.thegreenplace.net/2025/decorator-jits-python-as-a-dsl)

---

## 2. Generator-Based Step Execution Pattern

### Decision: Use Dapr-style generator pattern with `send()` for bidirectional communication

### Rationale

Workflows yield step definitions; the engine executes them and sends outputs back via `generator.send()`. This enables:
- Two-way communication (workflow yields steps, engine sends results)
- Natural step-by-step execution with pause/resume capability
- Clean separation between workflow logic and execution engine
- Explicit return values via `StopIteration.value`

```python
def _execute_workflow(
    workflow_def: WorkflowDefinition,
    inputs: dict[str, Any]
) -> WorkflowResult:
    """Execute workflow by iterating generator, executing steps, sending outputs back."""
    context = WorkflowContext(inputs=inputs)
    gen = workflow_def.func(**inputs)

    # Start generator
    try:
        step_to_execute = gen.send(None)
    except StopIteration as e:
        return _finalize_result(context, e.value, has_explicit_return=True)

    # Execute steps
    while True:
        step_result = _execute_step(step_to_execute, context)
        context.results[step_result.name] = step_result

        if not step_result.success:
            return _finalize_result(context, None, has_explicit_return=False)

        try:
            step_to_execute = gen.send(step_result.output)
        except StopIteration as e:
            return _finalize_result(context, e.value, has_explicit_return=True)
```

### FR-021 Implementation: Explicit Return vs Last Step Output

```python
def _finalize_result(
    context: WorkflowContext,
    explicit_return: Any,
    has_explicit_return: bool
) -> WorkflowResult:
    """Set final_output per FR-021."""
    if has_explicit_return and explicit_return is not None:
        final_output = explicit_return
    elif context.results:
        last_step_name = list(context.results.keys())[-1]
        final_output = context.results[last_step_name].output
    else:
        final_output = None

    return WorkflowResult(
        workflow_name=...,
        success=all(r.success for r in context.results.values()),
        step_results=tuple(context.results.values()),
        final_output=final_output,
        total_duration_ms=...,
    )
```

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Prefect-style direct function calls | Requires magic interception; less explicit; harder to test |
| Callback-based step execution | More complex; callbacks harder to reason about than generators |
| Async generator with `async for` | Steps are yielded, not iterated; send() pattern is more appropriate |

### Sources

- [Dapr Workflow Patterns](https://docs.dapr.io/developing-applications/building-blocks/workflow/workflow-patterns/)
- [PEP 479 – StopIteration handling](https://peps.python.org/pep-0479/)
- [Advanced Generator Patterns](https://www.datanovia.com/learn/programming/python/advanced/generators/advanced-generator-patterns.html)

---

## 3. Context Builder Pattern for Agent/Generate Steps

### Decision: Support both static dict and async callable that receives `WorkflowContext`

### Rationale

Per FR-007 and FR-008, agent and generate steps need context that can be:
- **Static dict**: Simple cases where context is known at definition time
- **Callable context builder**: Dynamic cases where context depends on prior step results

```python
from typing import Union, Callable, Awaitable, Any

# Type alias for context specification
ContextBuilder = Callable[[WorkflowContext], Awaitable[dict[str, Any]]]
StepContext = Union[dict[str, Any], ContextBuilder]

@dataclass(frozen=True, slots=True)
class AgentStep:
    """Agent step with context builder support (FR-007)."""
    name: str
    agent: Any  # MaverickAgent instance
    context: StepContext
    step_type: StepType = StepType.AGENT

    async def _resolve_context(self, workflow_context: WorkflowContext) -> dict[str, Any]:
        """Resolve context from static dict or callable builder."""
        if callable(self.context):
            return await self.context(workflow_context)
        return self.context
```

### Error Handling for Context Builders

Per clarification (Session 2025-12-19): context builder failure is treated as step failure.

```python
async def execute(self, workflow_context: WorkflowContext) -> StepResult:
    try:
        agent_context = await self._resolve_context(workflow_context)
        if not isinstance(agent_context, dict):
            raise WorkflowError(
                f"Context builder must return dict, got {type(agent_context).__name__}"
            )
        result = await self.agent.execute(agent_context)
        return StepResult(success=result.success, output=result, ...)
    except Exception as e:
        return StepResult(success=False, error=f"Step failed: {e}", ...)
```

### Usage Examples

```python
# Static context
step("review").agent(
    agent=ReviewerAgent(),
    context={"branch": "feature-123"}
)

# Context builder accessing prior step results
async def build_review_context(ctx: WorkflowContext) -> dict[str, Any]:
    impl_result = ctx.results["implementation"].output
    return {
        "files_changed": impl_result.files,
        "commit_sha": impl_result.commit,
    }

step("review").agent(
    agent=ReviewerAgent(),
    context=build_review_context  # Callable
)
```

### Sources

- [Repository Pattern with Context Variables in Async Python](https://medium.com/@sawaamun/repository-pattern-with-context-variables-in-async-python-519728211d67)
- [PEP 677 – Callable Type Syntax](https://peps.python.org/pep-0677/)

---

## 4. Result Objects: Pydantic vs Frozen Dataclasses

### Decision: Use frozen dataclasses with slots for `StepResult` and `WorkflowResult`

### Rationale

| Criterion | Frozen Dataclass | Pydantic | Winner |
|-----------|------------------|----------|--------|
| **Serialization (FR-014)** | Manual `to_dict()` with full control | Auto but complex types fail | Dataclass |
| **Performance** | ~50μs per instantiation | ~150-300μs per instantiation | Dataclass (3-5x faster) |
| **Validation** | `__post_init__` for invariants | Field validators | Tie (dataclass sufficient) |
| **Async compatibility** | Native | Native | Tie |
| **Type safety** | MyPy native | Sometimes confuses MyPy | Dataclass |
| **Memory** | ~56 bytes base (with slots) | ~240 bytes base | Dataclass (2-3x efficient) |
| **Codebase consistency** | Used for AgentResult, CommandResult, etc. | Used for config models | Dataclass (for results) |

### Pattern in Maverick Codebase

The existing codebase establishes a clear pattern:
- **Immutable value objects / results**: Frozen dataclasses (AgentResult, CommandResult, StageResult)
- **Configuration / user input**: Pydantic (FlyConfig, MaverickConfig)

### Implementation

```python
@dataclass(frozen=True, slots=True)
class StepResult:
    """Result of executing a single workflow step (FR-013)."""
    name: str
    step_type: StepType
    success: bool
    output: Any
    duration_ms: int
    error: str | None = None

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if not self.success and self.error is None:
            raise ValueError("Failed steps must have an error message")

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
        if hasattr(self.output, 'to_dict'):
            return self.output.to_dict()
        return str(self.output)

@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Aggregate workflow execution result (FR-020)."""
    workflow_name: str
    success: bool
    step_results: tuple[StepResult, ...]
    total_duration_ms: int
    final_output: Any
```

### Alternatives Considered

| Alternative | Rejected Because |
|-------------|------------------|
| Pydantic BaseModel | Overhead for simple value objects; auto-serialization fails on complex `output` types |
| Regular dataclass (mutable) | Results should be immutable; mutable state leads to bugs |
| Named tuples | Less readable; no validation; limited IDE support |

---

## 5. Step Builder API Design

### Decision: Fluent builder pattern with `step(name)` factory

### Rationale

Per FR-004, the DSL needs a `step(step_name)` function that creates step definitions. A fluent builder enables clean, readable workflow definitions:

```python
def step(name: str) -> StepBuilder:
    """Create a step definition with the provided name (FR-004)."""
    return StepBuilder(name)

class StepBuilder:
    """Fluent builder for step definitions."""

    def __init__(self, name: str) -> None:
        self._name = name

    def python(
        self,
        action: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> PythonStep:
        return PythonStep(name=self._name, action=action, args=args, kwargs=kwargs or {})

    def agent(
        self,
        agent: MaverickAgent,
        context: StepContext,
    ) -> AgentStep:
        return AgentStep(name=self._name, agent=agent, context=context)

    def generate(
        self,
        generator: GeneratorAgent,
        context: StepContext,
    ) -> GenerateStep:
        return GenerateStep(name=self._name, generator=generator, context=context)

    def validate(
        self,
        stages: list[str] | str | None = None,
        retry: int = 3,
        on_failure: StepDefinition | None = None,
    ) -> ValidateStep:
        return ValidateStep(name=self._name, stages=stages, retry=retry, on_failure=on_failure)

    def subworkflow(
        self,
        workflow: Callable[..., Any],
        inputs: dict[str, Any] | None = None,
    ) -> SubWorkflowStep:
        return SubWorkflowStep(name=self._name, workflow=workflow, inputs=inputs or {})
```

### Usage

```python
@workflow(name="example", description="Example workflow")
def example_workflow(input_data: str):
    # Python step
    validated = yield step("validate_input").python(
        action=validate,
        args=(input_data,),
    )

    # Agent step
    result = yield step("implement").agent(
        agent=ImplementerAgent(),
        context={"task": validated},
    )

    # Validate step with retry
    yield step("verify").validate(
        stages=["lint", "test"],
        retry=3,
        on_failure=step("fix").agent(agent=FixerAgent(), context={}),
    )

    return result
```

---

## 6. Duplicate Step Name Detection

### Decision: Fail-fast with clear error at step execution time

### Rationale

Per FR-005, duplicate step names must fail the workflow with a clear error message. Detection should happen when storing step results:

```python
def _execute_workflow(...) -> WorkflowResult:
    context = WorkflowContext(inputs=inputs)
    seen_names: set[str] = set()

    while True:
        step_result = _execute_step(step_to_execute, context)

        # Check for duplicate (FR-005)
        if step_result.name in seen_names:
            return WorkflowResult(
                success=False,
                step_results=tuple(context.results.values()),
                final_output=None,
                error=f"Duplicate step name: '{step_result.name}'. Step names must be unique.",
            )

        seen_names.add(step_result.name)
        context.results[step_result.name] = step_result
        # ...
```

---

## 7. ValidateStep with Retry and On-Failure

### Decision: Retry loop with configurable on-failure step

### Rationale

Per FR-009, FR-010, and clarifications:
- `retry=0`: No retries, fail immediately (on-failure never runs)
- `retry=1`: One retry allowed (on-failure runs once if validation fails, then re-validate)
- `retry=N`: N retries allowed (on-failure runs up to N times)

```python
@dataclass(frozen=True, slots=True)
class ValidateStep:
    name: str
    stages: list[str] | str | None
    retry: int = 3
    on_failure: StepDefinition | None = None
    step_type: StepType = StepType.VALIDATE

    async def execute(self, workflow_context: WorkflowContext) -> StepResult:
        # Resolve stages from config if needed
        resolved_stages = self._resolve_stages(workflow_context.config)

        for attempt in range(self.retry + 1):
            validation_result = await self._run_validation(resolved_stages)

            if validation_result.success:
                return StepResult(success=True, output=validation_result, ...)

            # Fail immediately if retry=0 or no retries left
            if self.retry == 0 or attempt >= self.retry:
                break

            # Run on-failure step if configured
            if self.on_failure:
                await self.on_failure.execute(workflow_context)

        return StepResult(success=False, error="Validation failed after retries", ...)
```

---

## 8. Progress Events for TUI

### Decision: Emit frozen dataclass events at step start/complete

### Rationale

Per FR-019, the workflow must emit progress events. Using frozen dataclasses matches the codebase pattern and provides:
- Immutable events safe for concurrent access
- Clean type discrimination via isinstance()
- Slots for memory efficiency

```python
@dataclass(frozen=True, slots=True)
class StepStarted:
    """Emitted when a step begins execution."""
    step_name: str
    step_type: StepType
    timestamp: float = field(default_factory=time.time)

@dataclass(frozen=True, slots=True)
class StepCompleted:
    """Emitted when a step finishes execution."""
    step_name: str
    step_type: StepType
    success: bool
    duration_ms: int
    timestamp: float = field(default_factory=time.time)

ProgressEvent = StepStarted | StepCompleted | WorkflowStarted | WorkflowCompleted
```

---

## Summary of Decisions

| Topic | Decision | Key Rationale |
|-------|----------|---------------|
| Decorator | `@workflow` with `inspect.signature()` | One-time capture; ParamSpec for type safety |
| Execution | Generator with `send()` pattern | Dapr-style bidirectional communication |
| Return values | Explicit return or last step output | FR-021 compliance |
| Context builders | `Union[dict, Callable[[WorkflowContext], Awaitable[dict]]]` | Flexibility for static and dynamic contexts |
| Result objects | Frozen dataclasses with slots | Performance, serialization control, codebase consistency |
| Step builder | Fluent `step(name).python/agent/etc.` | Readable DSL, explicit step types |
| Duplicate detection | Fail-fast at execution time | Clear errors per FR-005 |
| Validation retry | Loop with on-failure step | FR-009, FR-010 compliance |
| Progress events | Frozen dataclass union type | Type-safe, immutable, TUI-ready |

All research items resolved. Ready for Phase 1: Design.
