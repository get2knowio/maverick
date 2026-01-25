---
layout: section
class: text-center
---

# 1. Modern Python Development

<div class="text-lg text-secondary mt-4">
Python 3.10+ features powering Maverick
</div>

<div class="mt-8 flex justify-center gap-6 text-sm">
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-teal"></span>
    <span class="text-muted">8 Slides</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-brass"></span>
    <span class="text-muted">Async-First</span>
  </div>
  <div class="flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-coral"></span>
    <span class="text-muted">Type Safe</span>
  </div>
</div>

<!--
Section 1 covers Modern Python Development - the language features and patterns that Maverick requires and uses throughout its codebase.

We'll cover:
1. Why Python 3.10+ is required
2. Future annotations
3. Type hints fundamentals
4. Advanced type hints
5. Async/await primer
6. asyncio patterns
7. anyio for portability
8. Dataclasses overview
-->

---

## layout: two-cols

# 1.1 Why Python 3.10+?

<div class="pr-4">

Maverick requires Python 3.10+ for critical language features

<div v-click class="mt-4">

## Pattern Matching

```python
match step.type:
    case StepType.PYTHON:
        return await execute_python(step)
    case StepType.AGENT:
        return await execute_agent(step)
    case StepType.VALIDATE:
        return await execute_validate(step)
    case _:
        raise ValueError(f"Unknown: {step.type}")
```

</div>

<div v-click class="mt-4">

## Union Syntax

```python
# 3.10+: Clean pipe syntax
def process(data: str | bytes | None) -> dict:
    ...

# Pre-3.10: Verbose
def process(data: Union[str, bytes, None]) -> dict:
    ...
```

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-16">

## Performance Improvements

<div class="text-sm text-muted mt-2 space-y-2">

- **10-60% faster** than Python 3.9
- Optimized function calls
- Better memory management
- Faster attribute access

</div>

</div>

<div v-click class="mt-6">

## ParamSpec for Decorators

```python
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

def retry(func: Callable[P, R]) -> Callable[P, R]:
    """Type-safe decorator with preserved signature."""
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    return wrapper
```

</div>

<div v-click class="mt-6 p-3 bg-teal/10 border border-teal/30 rounded-lg">
  <div class="text-xs font-mono text-teal">pyproject.toml</div>
  <div class="text-sm mt-1 font-mono">requires-python = ">=3.10"</div>
</div>

</div>

<!--
Python 3.10 introduced several features that Maverick relies upon heavily:

1. **Pattern Matching (match/case)**: Used throughout the DSL for step type dispatch. Much cleaner than if/elif chains.

2. **Union Syntax (X | Y)**: The pipe syntax for union types is more readable. Every function signature benefits.

3. **Performance**: Python 3.10-3.12 brought significant performance improvements. Maverick's async operations benefit greatly.

4. **ParamSpec**: Critical for type-safe decorators. Our @async_command and @retry decorators preserve the original function's signature in IDE autocompletion.
-->

---

## layout: default

# 1.2 Future Annotations

<div class="text-secondary text-sm mb-4">
Every Maverick module starts with this import
</div>

```python {1|1,7-8|all}
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent
    from maverick.dsl.context import WorkflowContext

@dataclass
class StepResult:
    """Result of a workflow step execution."""

    output: Any
    context: WorkflowContext  # Forward reference - no quotes needed!
    agent: MaverickAgent | None = None  # Clean union syntax
```

<div class="grid grid-cols-2 gap-6 mt-6">

<div v-click>

### Without Future Annotations

```python
# Must quote forward references
context: "WorkflowContext"
agent: "MaverickAgent | None"

# Or use Update annotation
from typing import ForwardRef
```

</div>

<div v-click>

### With Future Annotations

```python
# No quotes needed - cleaner code
context: WorkflowContext
agent: MaverickAgent | None

# All annotations are strings at runtime
```

</div>

</div>

<div v-click class="mt-4 p-3 bg-brass/10 border border-brass/30 rounded-lg text-sm">
  <strong class="text-brass">Key Insight:</strong> With <code>from __future__ import annotations</code>, all annotations become strings at runtime, enabling forward references without quotes and avoiding circular import issues.
</div>

<!--
The future annotations import (PEP 563) is the first line in every Maverick module for good reasons:

1. **Forward References**: You can reference types that haven't been defined yet without using string quotes.

2. **Circular Import Prevention**: Combined with TYPE_CHECKING, you can import types needed for annotations without creating runtime circular imports.

3. **Cleaner Code**: No quotes around type names means cleaner, more readable annotations.

4. **Performance**: Annotations aren't evaluated at import time, making imports faster.

This is a Maverick coding standard - check any file in src/maverick/ and you'll see this pattern.
-->

---

## layout: default

# 1.3 Type Hints Fundamentals

<div class="text-secondary text-sm mb-6">
Complete type annotations are required for all public functions in Maverick
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### Basic Types

```python {1-4|6-9|11-14|all}
# Primitives
name: str = "maverick"
count: int = 42
enabled: bool = True

# Collections (3.9+ built-in syntax)
tasks: list[str] = ["lint", "test"]
config: dict[str, Any] = {"timeout": 30}
results: set[int] = {1, 2, 3}

# Optional values
branch: str | None = None
timeout: int | None = None
```

<div v-click class="mt-4">

### Function Signatures

```python
def execute_step(
    step: WorkflowStep,
    context: WorkflowContext,
    *,  # Keyword-only after this
    timeout: float = 30.0,
    retry: bool = True,
) -> StepResult:
    """Execute a workflow step."""
    ...
```

</div>

</div>

<div>

<div v-click>

### Why Types Matter

<div class="space-y-3 text-sm mt-4">

<div class="flex items-start gap-2">
  <span class="text-teal">✓</span>
  <div><strong>IDE Support</strong>: Autocompletion, refactoring, find usages</div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal">✓</span>
  <div><strong>Documentation</strong>: Types are self-documenting</div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal">✓</span>
  <div><strong>Early Errors</strong>: mypy catches bugs before runtime</div>
</div>

<div class="flex items-start gap-2">
  <span class="text-teal">✓</span>
  <div><strong>AI Assistants</strong>: Claude understands typed code better</div>
</div>

</div>

</div>

<div v-click class="mt-6">

### Maverick Validation

```bash
# Run type checker
make typecheck

# mypy runs with strict mode
mypy src/maverick/ --strict
```

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Rule:</strong> No <code>Any</code> on public APIs without explicit justification in docstring.
</div>

</div>

</div>

<!--
Type hints are not optional in Maverick - they're a core requirement for code quality.

**Basic Types**: Python 3.9+ allows using built-in types like list, dict, set directly in annotations without importing from typing.

**Optional Values**: Use `X | None` instead of the old `Optional[X]` syntax for clarity.

**Function Signatures**: Every public function must have complete type annotations including:
- All parameters typed
- Return type specified
- Keyword-only parameters where appropriate

**Why This Matters**:
- IDE gives accurate autocompletion
- Types serve as documentation
- mypy catches type errors before runtime
- AI coding assistants (including Claude) work better with typed code

Run `make typecheck` to verify your types are correct.
-->

---

## layout: default

# 1.4 Advanced Type Hints

<div class="text-secondary text-sm mb-6">
Patterns used throughout Maverick for complex typing scenarios
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### TypeVar & Generic

```python {1-3|5-12|all}
from typing import TypeVar, Generic

TResult = TypeVar("TResult", covariant=True)

class MaverickAgent(Generic[TContext, TResult]):
    """Generic agent with typed context and result."""

    @abstractmethod
    async def execute(
        self,
        context: TContext
    ) -> TResult:
        """Execute agent with typed context."""
        ...
```

<div v-click class="mt-4">

### Protocol (Structural Typing)

```python
from typing import Protocol

class SupportsExecute(Protocol):
    """Any object with an execute method."""

    async def execute(self) -> Any: ...

# Duck typing with type safety!
def run_executor(e: SupportsExecute) -> None:
    await e.execute()
```

</div>

</div>

<div>

<div v-click>

### Literal Types

```python
from typing import Literal

# Only these exact values allowed
StepType = Literal[
    "python",
    "agent",
    "validate",
    "branch"
]

PermissionMode = Literal[
    "default",
    "acceptEdits",
    "plan",
    "bypassPermissions"
]

def set_mode(mode: PermissionMode) -> None:
    ...  # IDE autocompletes valid options
```

</div>

<div v-click class="mt-4">

### TypedDict

```python
from typing import TypedDict, Required

class StepOutput(TypedDict, total=False):
    """Typed dictionary for step outputs."""

    output: Required[Any]
    error: str | None
    duration_ms: int
    metadata: dict[str, Any]
```

</div>

</div>

</div>

<!--
Maverick uses advanced typing patterns for type safety without sacrificing flexibility:

**TypeVar & Generic**: The MaverickAgent base class uses Generic to allow specialized agents with different context and result types. ReviewerAgent uses ReviewContext, ImplementerAgent uses ImplementerContext, etc.

**Protocol**: Enables structural typing (duck typing with types). Instead of requiring inheritance, any object with the right methods works. Great for dependency injection.

**Literal**: Restricts values to specific strings or numbers. Used extensively for step types, permission modes, and other enums. IDE autocompletes valid options.

**TypedDict**: Typed dictionaries for structured data that needs to be JSON-serializable. Used for workflow outputs and API responses.
-->

---

## layout: two-cols

# 1.5 Async/Await Primer

<div class="pr-4">

<div class="text-secondary text-sm mb-4">
Maverick is async-first — all I/O operations are non-blocking
</div>

### What is Async?

<div class="text-sm space-y-2 mt-2">

- **Coroutines**: Functions that can pause and resume
- **Non-blocking**: Other code runs while waiting for I/O
- **Concurrent**: Multiple operations in flight simultaneously

</div>

<div v-click class="mt-4">

### The Basics

```python
import asyncio

# Define a coroutine
async def fetch_issue(issue_id: int) -> Issue:
    """Async function - returns a coroutine."""
    response = await github_client.get(
        f"/issues/{issue_id}"
    )
    return Issue.from_response(response)

# Await the coroutine
issue = await fetch_issue(123)
```

</div>

<div v-click class="mt-4 p-3 bg-coral/10 border border-coral/30 rounded-lg text-sm">
  <strong class="text-coral">Rule:</strong> Never call <code>subprocess.run</code> from <code>async def</code> — use <code>asyncio.create_subprocess_exec</code>
</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-10">

### Why Async Matters

```python
# ❌ Blocking - wastes time waiting
def review_issues_sync(ids: list[int]) -> list[Result]:
    results = []
    for id in ids:  # Sequential, slow
        results.append(review_issue(id))
    return results  # Total: N × time_per_issue

# ✅ Async - concurrent execution
async def review_issues_async(ids: list[int]) -> list[Result]:
    tasks = [review_issue(id) for id in ids]
    return await asyncio.gather(*tasks)
    # Total: max(time_per_issue) ≈ 1 operation
```

</div>

<div v-click class="mt-6">

### Maverick Agent Example

```python
class ReviewerAgent(MaverickAgent[ReviewContext, ReviewResult]):

    async def execute(
        self,
        context: ReviewContext
    ) -> ReviewResult:
        """Review is async - calls Claude API."""
        async for chunk in self._stream_response(context):
            yield chunk  # Stream results as they arrive
```

</div>

</div>

<!--
Maverick is async-first because AI agent operations involve significant I/O:
- API calls to Claude (each takes 1-30 seconds)
- GitHub API calls
- Git operations
- File system operations

**Async allows**:
- Running multiple reviews in parallel
- Streaming responses as they arrive
- Keeping the TUI responsive during long operations

**Key Rule**: Never use blocking calls in async code. Use:
- `asyncio.create_subprocess_exec` instead of `subprocess.run`
- `aiohttp` or async HTTP clients instead of `requests`
- `asyncio.to_thread` to wrap unavoidable sync code
-->

---

## layout: default

# 1.6 asyncio Patterns

<div class="text-secondary text-sm mb-4">
Essential patterns used throughout Maverick's async codebase
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### asyncio.gather — Parallel Execution

```python {1-5|7-12|all}
async def validate_all(files: list[Path]) -> list[Result]:
    """Run all validations in parallel."""
    return await asyncio.gather(
        *[validate_file(f) for f in files]
    )

# With error handling
results = await asyncio.gather(
    lint_check(),
    type_check(),
    run_tests(),
    return_exceptions=True  # Don't fail on first error
)
```

<div v-click class="mt-4">

### asyncio.create_task — Fire and Forget

```python
async def start_workflow(workflow: Workflow) -> None:
    # Start background task
    task = asyncio.create_task(
        emit_metrics(workflow),
        name="metrics-emitter"
    )

    # Do main work while metrics emit
    await execute_steps(workflow)

    # Clean up
    task.cancel()
```

</div>

</div>

<div>

<div v-click>

### asyncio.to_thread — Wrap Blocking Code

```python
from git import Repo

async def get_status() -> GitStatus:
    """Wrap blocking GitPython in thread."""
    repo = Repo(self.path)

    # Run blocking code in thread pool
    status = await asyncio.to_thread(
        repo.git.status,
        porcelain=True
    )

    return parse_status(status)
```

</div>

<div v-click class="mt-4">

### asyncio.wait_for — Timeouts

```python
async def call_claude_with_timeout(
    prompt: str,
    timeout: float = 60.0
) -> Response:
    """API call with timeout protection."""
    try:
        return await asyncio.wait_for(
            client.query(prompt),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise AgentTimeoutError(
            f"Claude API timed out after {timeout}s"
        )
```

</div>

</div>

</div>

<!--
These asyncio patterns appear throughout Maverick:

**asyncio.gather**: Run multiple coroutines concurrently. Used for parallel validation, running multiple reviews simultaneously, etc. The `return_exceptions=True` flag prevents one failure from canceling others.

**asyncio.create_task**: Start a coroutine running without waiting for it. Used for background tasks like metrics emission, progress updates, etc. Remember to cancel or await tasks to avoid warnings.

**asyncio.to_thread**: Critical for wrapping blocking libraries like GitPython in async code. Runs the blocking function in a thread pool executor. This is how Maverick's AsyncGitRepository works internally.

**asyncio.wait_for**: Add timeout protection to any async operation. Essential for external API calls that might hang. All network operations in Maverick have timeouts.
-->

---

## layout: two-cols

# 1.7 anyio for Portability

<div class="pr-4">

<div class="text-secondary text-sm mb-4">
Maverick uses anyio alongside asyncio for broader compatibility
</div>

### What is anyio?

<div class="text-sm space-y-2 mt-2">

- Async abstraction layer
- Works with **asyncio** and **Trio**
- Provides structured concurrency
- Used by Textual, httpx, and many libraries

</div>

<div v-click class="mt-4">

### Task Groups (Structured Concurrency)

```python
import anyio

async def process_items(items: list[Item]) -> None:
    """Process items with structured concurrency."""
    async with anyio.create_task_group() as tg:
        for item in items:
            tg.start_soon(process_item, item)
    # All tasks complete when we exit the block
    # Exceptions propagate properly
```

</div>

<div v-click class="mt-4">

### Why Structured Concurrency?

<div class="text-sm space-y-1">

- Tasks can't outlive their scope
- Exceptions always propagate
- Cancellation is automatic
- No orphaned coroutines

</div>

</div>

</div>

::right::

<div class="pl-4">

<div v-click class="mt-10">

### File Operations

```python
import anyio
from pathlib import Path

async def read_workflow(path: Path) -> str:
    """Async file read with anyio."""
    return await anyio.Path(path).read_text()

async def write_output(path: Path, data: str) -> None:
    """Async file write with anyio."""
    await anyio.Path(path).write_text(data)
```

</div>

<div v-click class="mt-4">

### Running Blocking Functions

```python
async def validate_secrets(content: str) -> list[str]:
    """Run detect-secrets in thread pool."""
    return await anyio.to_thread.run_sync(
        detect_secrets,
        content,
        cancellable=True
    )
```

</div>

<div v-click class="mt-4 p-3 bg-teal/10 border border-teal/30 rounded-lg text-sm">
  <strong class="text-teal">Tip:</strong> Use <code>anyio</code> when your code might be used with Textual or in libraries that need backend flexibility.
</div>

</div>

<!--
anyio provides a consistent async API that works across different async backends:

**Why anyio?**:
- Textual (our TUI framework) uses anyio
- Makes code portable between asyncio and Trio
- Provides structured concurrency patterns
- Better primitives for file I/O

**Task Groups**: The killer feature of structured concurrency. Unlike `asyncio.gather`, task groups ensure:
- All tasks complete before the block exits
- Exceptions from any task propagate to the parent
- Cancellation is automatic when the parent is canceled

**When to use anyio vs asyncio?**:
- Use anyio in library code or code used by Textual
- asyncio.gather is fine for top-level orchestration
- Use anyio.Path for async file operations
-->

---

## layout: default

# 1.8 Dataclasses Overview

<div class="text-secondary text-sm mb-4">
Maverick uses dataclasses for simple value types and Pydantic for validated configuration
</div>

<div class="grid grid-cols-2 gap-6">

<div>

### Standard Dataclass

```python {1-10|12-19|all}
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)  # Immutable
class StepResult:
    """Result from executing a workflow step."""

    output: Any
    success: bool = True
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "output": self.output,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }
```

<div v-click class="mt-4">

### With Default Factory

```python
@dataclass
class WorkflowContext:
    """Mutable context passed through workflow."""

    inputs: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

</div>

</div>

<div>

<div v-click>

### When to Use What?

<div class="text-sm space-y-3 mt-2">

<div class="p-3 rounded-lg bg-slate-800/50 border border-slate-600">
  <strong class="text-teal">Dataclass</strong>
  <ul class="text-xs mt-1 space-y-1 text-muted">
    <li>• Simple value objects</li>
    <li>• Internal data structures</li>
    <li>• When validation isn't needed</li>
    <li>• Performance-critical code</li>
  </ul>
</div>

<div class="p-3 rounded-lg bg-slate-800/50 border border-slate-600">
  <strong class="text-brass">Pydantic BaseModel</strong>
  <ul class="text-xs mt-1 space-y-1 text-muted">
    <li>• Configuration loading</li>
    <li>• External data (YAML, JSON, API)</li>
    <li>• When validation is required</li>
    <li>• Serialization/deserialization</li>
  </ul>
</div>

</div>

</div>

<div v-click class="mt-4">

### Maverick Pattern: Frozen + to_dict

```python
@dataclass(frozen=True)
class CommitInfo:
    """Immutable commit information."""

    sha: str
    message: str
    author: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

</div>

</div>

</div>

<!--
Maverick uses both dataclasses and Pydantic, each for their strengths:

**Dataclasses**: For internal value objects that don't need validation
- `frozen=True` makes them immutable (safer, hashable)
- `to_dict()` method for serialization
- `field(default_factory=...)` for mutable defaults
- Fast, zero overhead

**Pydantic BaseModel**: For configuration and external data
- Automatic validation on creation
- Environment variable support
- Rich serialization (JSON, dict)
- Field validators and model validators

**The Rule**: Use dataclass for "trusted" internal data, Pydantic for "untrusted" external data (config files, API responses, user input).
-->

---

layout: center
class: text-center

---

# Section 1 Summary

<div class="text-xl text-secondary mt-4 mb-8">
Modern Python foundations used throughout Maverick
</div>

<div class="grid grid-cols-4 gap-4 max-w-4xl mx-auto text-left">

<div v-click class="p-4 rounded-lg bg-slate-800/50 border border-slate-600">
  <div class="text-2xl mb-2">🐍</div>
  <div class="font-semibold text-sm">Python 3.10+</div>
  <div class="text-xs text-muted mt-1">Pattern matching, union syntax, ParamSpec</div>
</div>

<div v-click class="p-4 rounded-lg bg-slate-800/50 border border-slate-600">
  <div class="text-2xl mb-2">📝</div>
  <div class="font-semibold text-sm">Type Safety</div>
  <div class="text-xs text-muted mt-1">Complete annotations, Generic, Protocol</div>
</div>

<div v-click class="p-4 rounded-lg bg-slate-800/50 border border-slate-600">
  <div class="text-2xl mb-2">⚡</div>
  <div class="font-semibold text-sm">Async/Await</div>
  <div class="text-xs text-muted mt-1">asyncio, anyio, concurrent I/O</div>
</div>

<div v-click class="p-4 rounded-lg bg-slate-800/50 border border-slate-600">
  <div class="text-2xl mb-2">🏗️</div>
  <div class="font-semibold text-sm">Data Models</div>
  <div class="text-xs text-muted mt-1">Dataclasses for internal, Pydantic for config</div>
</div>

</div>

<div v-click class="mt-8 text-sm text-muted">

**Key Takeaways:**

<div class="flex justify-center gap-8 mt-4">
  <div>✓ Every file starts with <code>from __future__ import annotations</code></div>
  <div>✓ All public functions have complete type hints</div>
  <div>✓ Never block the event loop</div>
</div>

</div>

<div v-click class="mt-8">
  <span class="text-brass font-semibold">Next:</span> Section 2 — Click CLI Framework
</div>

<!--
Section 1 covered the Python language foundations that Maverick requires:

1. **Python 3.10+**: Required for pattern matching, pipe union syntax, and ParamSpec
2. **Type Safety**: Complete annotations enable IDE support, documentation, and static analysis
3. **Async/Await**: Non-blocking I/O for concurrent agent operations and responsive TUI
4. **Data Models**: Dataclasses for internal structures, Pydantic for validated configuration

These patterns appear consistently throughout the codebase. Understanding them is essential for contributing to Maverick.

Up next: How Maverick's CLI is built using Click.
-->
