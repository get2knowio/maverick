# Contract: FlyWorkflow.execute()

**Module**: `src/maverick/workflows/fly.py`
**Type**: Internal API (Python interface)

## Overview

FlyWorkflow.execute() implements the 8-stage workflow for spec-based feature implementation. It uses Python orchestration for deterministic operations and Claude agents only for judgment tasks.

## Interface Definition

### Method Signature

```python
async def execute(self, inputs: FlyInputs) -> AsyncIterator[FlyProgressEvent]:
    """Execute the fly workflow.

    Args:
        inputs: Validated workflow inputs including branch name and options.

    Yields:
        Progress events for TUI consumption.

    Returns:
        Async iterator of FlyProgressEvent.
    """
```

### Progress Events

| Event | Fields | When Emitted |
|-------|--------|--------------|
| `FlyWorkflowStarted` | inputs, timestamp | Workflow begins |
| `FlyStageStarted` | stage, timestamp | Each stage begins |
| `FlyStageCompleted` | stage, result, timestamp | Each stage completes |
| `FlyWorkflowCompleted` | result, timestamp | Workflow succeeds |
| `FlyWorkflowFailed` | error, state, timestamp | Workflow fails |

### Final Result Access

```python
# After consuming all events, get final result
workflow = FlyWorkflow(config)
async for event in workflow.execute(inputs):
    # Process events
    pass
result = workflow.get_result()  # Returns FlyResult
```

## Stage Contracts

### INIT Stage (FR-001, FR-002)

**Operations** (Python-only):
1. Validate inputs (branch_name not empty)
2. Create branch via GitRunner.create_branch()
3. Parse task file via Python file I/O

**AI Involvement**: None

**Events**:
- FlyStageStarted(stage=INIT)
- FlyStageCompleted(stage=INIT, result={branch: str, tasks: list})

**Error Handling**:
- Branch conflict: Append timestamp suffix (FR-001a)
- Task file not found: FlyWorkflowFailed

### IMPLEMENTATION Stage (FR-003, FR-004)

**Operations**:
1. Build context (Python): Aggregate files, task definitions, project conventions
2. Execute ImplementerAgent (AI): Code implementation with file tools only

**AI Involvement**: ImplementerAgent with Read, Write, Edit, Glob, Grep, Bash

**Events**:
- FlyStageStarted(stage=IMPLEMENTATION)
- FlyStageCompleted(stage=IMPLEMENTATION, result=AgentResult)

**Error Handling**:
- Agent error: Record in state.errors, emit FlyWorkflowFailed

### VALIDATION Stage (FR-007, FR-008, FR-009)

**Operations** (Python + conditional AI):
1. Run ValidationRunner (Python): format, lint, build, test
2. On failure, invoke fix agent (AI): File modification tools only
3. Retry up to max_validation_attempts

**AI Involvement**: Fix agent only on validation failure

**Events**:
- FlyStageStarted(stage=VALIDATION)
- FlyStageCompleted(stage=VALIDATION, result=ValidationWorkflowResult)

**Error Handling**:
- Exhausted retries: Continue workflow, mark PR as draft (FR-009a)

### CODE_REVIEW Stage (FR-010, FR-011)

**Operations** (Python + AI):
1. Run CodeRabbitRunner (Python): If coderabbit_enabled
2. Run CodeReviewerAgent (AI): Interpret findings with read-only tools

**AI Involvement**: CodeReviewerAgent with Read, Glob, Grep

**Events**:
- FlyStageStarted(stage=CODE_REVIEW)
- FlyStageCompleted(stage=CODE_REVIEW, result=list[AgentResult])

**Error Handling**:
- CodeRabbit unavailable: Skip with warning (FR-010a)

### COMMIT Stage (FR-005, FR-006)

**Operations** (Python + AI):
1. Get diff via GitRunner.diff() (Python)
2. Generate message via CommitMessageGenerator (AI)
3. Execute commit via GitRunner.commit() (Python)

**AI Involvement**: CommitMessageGenerator (no tools, single-shot)

**Events**: (Part of PR_CREATION or after IMPLEMENTATION)

### PR_CREATION Stage (FR-012, FR-013)

**Operations** (Python + AI):
1. Generate PR body via PRDescriptionGenerator (AI)
2. Create PR via GitHubCLIRunner.create_pr() (Python)

**AI Involvement**: PRDescriptionGenerator (no tools, single-shot)

**Events**:
- FlyStageStarted(stage=PR_CREATION)
- FlyStageCompleted(stage=PR_CREATION, result={pr_url: str})

**Error Handling**:
- PR creation failure: FlyWorkflowFailed

## Dependency Injection Contract

```python
class FlyWorkflow:
    def __init__(
        self,
        config: FlyConfig | None = None,
        # Injectable dependencies (all optional, defaults created if None)
        git_runner: GitRunner | None = None,
        validation_runner: ValidationRunner | None = None,
        github_runner: GitHubCLIRunner | None = None,
        coderabbit_runner: CodeRabbitRunner | None = None,
        implementer_agent: ImplementerAgent | None = None,
        code_reviewer_agent: CodeReviewerAgent | None = None,
        commit_generator: CommitMessageGenerator | None = None,
        pr_generator: PRDescriptionGenerator | None = None,
    ) -> None:
```

All runners and agents MUST be injectable via constructor for testing (FR-020).

## Test Contract

### Unit Test Requirements

1. All runners and agents mocked
2. Test each stage transition
3. Test error recovery (branch conflict, validation failure, coderabbit unavailable)
4. Verify progress events emitted correctly
5. Verify no AI calls for deterministic operations

### Example Test

```python
@pytest.mark.asyncio
async def test_init_stage_creates_branch_without_ai():
    mock_git = MagicMock()
    mock_git.create_branch = AsyncMock(return_value=GitResult(
        success=True, output="Switched to new branch", error=None, duration_ms=50
    ))

    workflow = FlyWorkflow(git_runner=mock_git)
    events = []
    async for event in workflow.execute(FlyInputs(branch_name="feature-x")):
        events.append(event)

    # Verify branch created via GitRunner (not agent)
    mock_git.create_branch.assert_called_once_with("feature-x")

    # Verify no agent was invoked during INIT
    # (implementer_agent.execute should not be called yet)
```

## Token Usage Contract

Token usage MUST be tracked per-agent and aggregated in FlyResult:

```python
FlyResult(
    success=True,
    state=...,
    summary="...",
    token_usage=AgentUsage(
        input_tokens=sum_of_all_agent_input_tokens,
        output_tokens=sum_of_all_agent_output_tokens,
        total_cost_usd=sum_of_all_costs,
        duration_ms=total_agent_time,
    ),
    total_cost_usd=...,
)
```
