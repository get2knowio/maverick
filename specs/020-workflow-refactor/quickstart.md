# Quickstart: Workflow Refactor Implementation

**Feature**: 020-workflow-refactor
**Date**: 2025-12-18

## Overview

This guide provides step-by-step instructions for implementing the workflow refactor. The goal is to implement `FlyWorkflow.execute()` and `RefuelWorkflow.execute()` using Python orchestration for deterministic operations and Claude agents only for judgment tasks.

## Prerequisites

- Python 3.10+
- Maverick development environment set up
- All existing tests passing: `PYTHONPATH=src python -m pytest tests/`
- Familiarity with existing codebase:
  - `/workspaces/maverick/src/maverick/workflows/validation.py` (reference implementation)
  - `/workspaces/maverick/src/maverick/runners/` (existing runners)
  - `/workspaces/maverick/src/maverick/agents/` (existing agents)

## Implementation Order

### Phase 1: GitRunner (Foundation)

**Goal**: Create async git operations wrapper.

**File**: `src/maverick/runners/git.py`

**Steps**:
1. Create `GitResult` dataclass (frozen, slots)
2. Implement `GitRunner` class wrapping CommandRunner
3. Implement methods: `create_branch`, `checkout`, `commit`, `push`, `diff`, `add`, `status`
4. Add branch conflict resolution (timestamp suffix fallback)

**Tests**: `tests/unit/runners/test_git.py`

**Validation**:
```bash
PYTHONPATH=src python -m pytest tests/unit/runners/test_git.py -v
```

### Phase 2: FlyWorkflow.execute() (Core)

**Goal**: Implement the 8-stage workflow.

**File**: `src/maverick/workflows/fly.py` (modify existing)

**Steps**:
1. Add constructor parameters for injectable dependencies
2. Implement INIT stage (Python-only: branch creation, task parsing)
3. Implement IMPLEMENTATION stage (ImplementerAgent with context)
4. Implement VALIDATION stage (ValidationRunner + fix agent)
5. Implement CODE_REVIEW stage (CodeRabbitRunner optional + CodeReviewerAgent)
6. Implement COMMIT stage (GitRunner + CommitMessageGenerator)
7. Implement PR_CREATION stage (PRDescriptionGenerator + GitHubCLIRunner)
8. Implement progress event emission via async generator

**Tests**: `tests/unit/workflows/test_fly.py` (extend existing)

**Validation**:
```bash
PYTHONPATH=src python -m pytest tests/unit/workflows/test_fly.py -v
```

### Phase 3: RefuelWorkflow.execute()

**Goal**: Implement issue processing workflow.

**File**: `src/maverick/workflows/refuel.py` (modify existing)

**Steps**:
1. Add constructor parameters for injectable dependencies
2. Implement issue discovery (GitHubCLIRunner.list_issues)
3. Implement per-issue processing loop with isolation
4. Implement branch creation per issue
5. Implement IssueFixerAgent invocation
6. Implement validation per issue
7. Implement commit and PR creation per issue
8. Implement result aggregation

**Tests**: `tests/unit/workflows/test_refuel.py`

**Validation**:
```bash
PYTHONPATH=src python -m pytest tests/unit/workflows/test_refuel.py -v
```

### Phase 4: Integration Testing

**Goal**: Verify end-to-end workflow behavior.

**File**: `tests/integration/workflows/test_fly_e2e.py`

**Steps**:
1. Create test fixtures with sample task files
2. Mock external services (GitHub API, git)
3. Verify complete workflow execution
4. Verify token usage reduction (SC-001)

**Validation**:
```bash
PYTHONPATH=src python -m pytest tests/integration/ -v
```

## Key Patterns

### Async Generator for Progress Events

```python
async def execute(self, inputs: FlyInputs) -> AsyncIterator[FlyProgressEvent]:
    yield FlyWorkflowStarted(inputs=inputs)

    # INIT stage
    yield FlyStageStarted(stage=WorkflowStage.INIT)
    branch_result = await self._git_runner.create_branch(inputs.branch_name)
    if not branch_result.success:
        yield FlyWorkflowFailed(error=branch_result.error, state=self._state)
        return
    yield FlyStageCompleted(stage=WorkflowStage.INIT, result=branch_result)

    # ... more stages ...

    yield FlyWorkflowCompleted(result=self._build_result())
```

### Dependency Injection

```python
class FlyWorkflow:
    def __init__(
        self,
        config: FlyConfig | None = None,
        git_runner: GitRunner | None = None,
        validation_runner: ValidationRunner | None = None,
        # ... other dependencies
    ) -> None:
        self._config = config or FlyConfig()
        self._git_runner = git_runner or GitRunner()
        self._validation_runner = validation_runner or ValidationRunner()
        # ...
```

### Error Isolation

```python
async def _run_validation(self) -> ValidationWorkflowResult:
    """Run validation with error isolation."""
    try:
        async for progress in self._validation_runner.run():
            # Forward progress events
            yield self._map_validation_progress(progress)
        return self._validation_runner.get_result()
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return ValidationWorkflowResult(
            success=False,
            stage_results=[],
            cancelled=False,
            total_duration_ms=0,
            metadata={"error": str(e)},
        )
```

### Token Tracking

```python
async def _invoke_agent(self, agent: MaverickAgent, prompt: str) -> AgentResult:
    """Invoke agent and track tokens."""
    result = await agent.execute(prompt)
    self._token_usages.append(result.usage)
    return result

def _aggregate_tokens(self) -> AgentUsage:
    """Aggregate all token usage."""
    return AgentUsage(
        input_tokens=sum(u.input_tokens for u in self._token_usages),
        output_tokens=sum(u.output_tokens for u in self._token_usages),
        total_cost_usd=sum(u.total_cost_usd or 0 for u in self._token_usages),
        duration_ms=sum(u.duration_ms for u in self._token_usages),
    )
```

## Testing Patterns

### Mock Runner Injection

```python
@pytest.fixture
def mock_git_runner():
    runner = MagicMock()
    runner.create_branch = AsyncMock(return_value=GitResult(
        success=True, output="", error=None, duration_ms=10
    ))
    runner.commit = AsyncMock(return_value=GitResult(
        success=True, output="", error=None, duration_ms=10
    ))
    return runner

@pytest.mark.asyncio
async def test_init_stage(mock_git_runner):
    workflow = FlyWorkflow(git_runner=mock_git_runner)
    events = [e async for e in workflow.execute(FlyInputs(branch_name="test"))]
    mock_git_runner.create_branch.assert_called_once_with("test")
```

### Async Generator Consumption

```python
@pytest.mark.asyncio
async def test_progress_events():
    workflow = FlyWorkflow(...)
    events = []
    async for event in workflow.execute(inputs):
        events.append(event)

    # Verify event sequence
    assert isinstance(events[0], FlyWorkflowStarted)
    assert isinstance(events[1], FlyStageStarted)
    assert events[1].stage == WorkflowStage.INIT
    # ...
```

## Verification Checklist

After implementation, verify:

- [ ] All unit tests pass
- [ ] No AI calls during INIT stage (FR-001, FR-002)
- [ ] Branch creation uses GitRunner (not agent)
- [ ] Validation uses ValidationRunner directly
- [ ] Commit message generation uses CommitMessageGenerator (not full agent)
- [ ] PR description generation uses PRDescriptionGenerator (not full agent)
- [ ] Progress events emitted at each stage transition
- [ ] Error isolation: stage failure doesn't crash workflow
- [ ] Token usage aggregated in final result

## Common Issues

### Issue: Async generator not yielding events

**Solution**: Ensure `async for` is used to consume the generator:
```python
# Wrong
result = workflow.execute(inputs)  # Just creates generator

# Right
async for event in workflow.execute(inputs):
    process(event)
```

### Issue: Mock not being injected

**Solution**: Ensure dependency is passed to constructor:
```python
# Wrong
workflow = FlyWorkflow()  # Uses real runner

# Right
workflow = FlyWorkflow(git_runner=mock_runner)
```

### Issue: Cancellation not working

**Solution**: Check `_cancel_event` at stage boundaries:
```python
if self._cancel_event.is_set():
    yield FlyWorkflowFailed(error="Cancelled", state=self._state)
    return
```
