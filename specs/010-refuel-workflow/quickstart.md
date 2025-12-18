# Quickstart: Refuel Workflow Interface

**Date**: 2025-12-15
**Feature Branch**: `010-refuel-workflow`

## Overview

This spec defines the **interface** for the Refuel Workflow. The implementation raises `NotImplementedError` - full implementation is deferred to Spec 26.

## File Structure

```
src/maverick/workflows/refuel.py    # All entities and workflow class
src/maverick/config.py              # RefuelConfig integration
tests/unit/workflows/test_refuel.py # Unit tests
```

## Implementation Order

### Step 1: Create refuel.py with Data Structures

```python
# src/maverick/workflows/refuel.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator

from maverick.agents.result import AgentUsage

# 1. Define GitHubIssue
@dataclass(frozen=True, slots=True)
class GitHubIssue:
    number: int
    title: str
    body: str | None
    labels: list[str]
    assignee: str | None
    url: str

# 2. Define IssueStatus enum
class IssueStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    FAILED = "failed"
    SKIPPED = "skipped"

# 3. Define RefuelInputs
@dataclass(frozen=True, slots=True)
class RefuelInputs:
    label: str = "tech-debt"
    limit: int = 5
    parallel: bool = False
    dry_run: bool = False
    auto_assign: bool = True

# 4. Define IssueProcessingResult
@dataclass(frozen=True, slots=True)
class IssueProcessingResult:
    issue: GitHubIssue
    status: IssueStatus
    branch: str | None
    pr_url: str | None
    error: str | None
    duration_ms: int
    agent_usage: AgentUsage

# 5. Define RefuelResult
@dataclass(frozen=True, slots=True)
class RefuelResult:
    success: bool
    issues_found: int
    issues_processed: int
    issues_fixed: int
    issues_failed: int
    issues_skipped: int
    results: list[IssueProcessingResult]
    total_duration_ms: int
    total_cost_usd: float
```

### Step 2: Add Progress Events

```python
# Progress events (same file)
@dataclass(frozen=True, slots=True)
class RefuelStarted:
    inputs: RefuelInputs
    issues_found: int

@dataclass(frozen=True, slots=True)
class IssueProcessingStarted:
    issue: GitHubIssue
    index: int
    total: int

@dataclass(frozen=True, slots=True)
class IssueProcessingCompleted:
    result: IssueProcessingResult

@dataclass(frozen=True, slots=True)
class RefuelCompleted:
    result: RefuelResult

# Union type for event handling
RefuelProgressEvent = (
    RefuelStarted
    | IssueProcessingStarted
    | IssueProcessingCompleted
    | RefuelCompleted
)
```

### Step 3: Define RefuelWorkflow Class

```python
class RefuelWorkflow:
    """Refuel workflow orchestrator.

    Orchestrates tech-debt resolution workflow:
    1. Discover issues by label from GitHub
    2. Filter by limit and skip_if_assigned policy
    3. For each issue:
       a. Create branch ({branch_prefix}{issue_number})
       b. Run IssueFixerAgent to implement fix
       c. Run ValidationWorkflow
       d. Commit with conventional message (fix: resolve #{number})
       e. Push and create PR linking to issue
       f. Optionally close issue on PR merge
    4. Aggregate results and emit RefuelCompleted

    Note: Full implementation in Spec 26 using workflow DSL.
    """

    def __init__(self, config: RefuelConfig | None = None) -> None:
        self._config = config or RefuelConfig()

    async def execute(
        self, inputs: RefuelInputs
    ) -> AsyncGenerator[RefuelProgressEvent, None]:
        """Execute the refuel workflow.

        Args:
            inputs: Workflow inputs (label, limit, parallel, etc.)

        Yields:
            Progress events (RefuelStarted, IssueProcessing*, RefuelCompleted)

        Raises:
            NotImplementedError: Always - implementation in Spec 26.
        """
        raise NotImplementedError(
            "RefuelWorkflow.execute() is not implemented. "
            "Full implementation will be provided in Spec 26 using the workflow DSL."
        )
        # Type hint for async generator (never reached)
        yield  # type: ignore[misc]
```

### Step 4: Add RefuelConfig to MaverickConfig

```python
# src/maverick/config.py - add import and field
from maverick.workflows.refuel import RefuelConfig

class MaverickConfig(BaseSettings):
    # ... existing fields ...
    refuel: RefuelConfig = Field(default_factory=RefuelConfig)
```

### Step 5: Export from __init__.py

```python
# src/maverick/workflows/__init__.py
from maverick.workflows.refuel import (
    GitHubIssue,
    IssueStatus,
    RefuelInputs,
    IssueProcessingResult,
    RefuelResult,
    RefuelConfig,
    RefuelStarted,
    IssueProcessingStarted,
    IssueProcessingCompleted,
    RefuelCompleted,
    RefuelProgressEvent,
    RefuelWorkflow,
)

__all__ = [
    # ... existing exports ...
    # Refuel workflow
    "GitHubIssue",
    "IssueStatus",
    "RefuelInputs",
    "IssueProcessingResult",
    "RefuelResult",
    "RefuelConfig",
    "RefuelStarted",
    "IssueProcessingStarted",
    "IssueProcessingCompleted",
    "RefuelCompleted",
    "RefuelProgressEvent",
    "RefuelWorkflow",
]
```

## Testing Strategy

### Unit Tests (test_refuel.py)

1. **Dataclass instantiation**: Verify all dataclasses can be created with valid data
2. **Immutability**: Verify frozen dataclasses reject attribute modification
3. **Default values**: Verify RefuelInputs defaults match spec
4. **IssueStatus enum**: Verify all values accessible and string conversion works
5. **NotImplementedError**: Verify execute() raises with correct message
6. **Config integration**: Verify RefuelConfig loads from MaverickConfig

### Example Test Cases

```python
import pytest
from maverick.workflows.refuel import (
    GitHubIssue, IssueStatus, RefuelInputs, RefuelWorkflow
)

def test_github_issue_immutable():
    issue = GitHubIssue(
        number=123,
        title="Fix bug",
        body="Description",
        labels=["tech-debt"],
        assignee=None,
        url="https://github.com/owner/repo/issues/123"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        issue.number = 456

def test_refuel_inputs_defaults():
    inputs = RefuelInputs()
    assert inputs.label == "tech-debt"
    assert inputs.limit == 5
    assert inputs.parallel is False
    assert inputs.dry_run is False
    assert inputs.auto_assign is True

@pytest.mark.asyncio
async def test_execute_raises_not_implemented():
    workflow = RefuelWorkflow()
    with pytest.raises(NotImplementedError, match="Spec 26"):
        async for _ in workflow.execute(RefuelInputs()):
            pass
```

## Acceptance Checklist

- [ ] All dataclasses use `frozen=True, slots=True`
- [ ] IssueStatus enum has all 5 values
- [ ] RefuelConfig integrates into MaverickConfig
- [ ] RefuelWorkflow.execute() raises NotImplementedError
- [ ] All progress events are dataclasses with correct fields
- [ ] Type alias RefuelProgressEvent defined as union
- [ ] All tests pass with mypy strict mode
- [ ] Exports added to workflows/__init__.py
