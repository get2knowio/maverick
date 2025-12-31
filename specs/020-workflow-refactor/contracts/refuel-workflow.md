# Contract: RefuelWorkflow.execute()

**Module**: `src/maverick/workflows/refuel.py`
**Type**: Internal API (Python interface)

## Overview

RefuelWorkflow.execute() orchestrates tech-debt resolution by processing multiple GitHub issues sequentially with proper isolation. It uses Python for deterministic operations (issue fetching, branch creation, PR creation) and Claude agents for judgment tasks (issue analysis and fixing).

## Interface Definition

### Method Signature

```python
async def execute(
    self, inputs: RefuelInputs
) -> AsyncGenerator[RefuelProgressEvent, None]:
    """Execute the refuel workflow.

    Args:
        inputs: Workflow inputs (label, limit, parallel, dry_run, auto_assign).

    Yields:
        Progress events (RefuelStarted, IssueProcessing*, RefuelCompleted).
    """
```

### Progress Events

| Event | Fields | When Emitted |
|-------|--------|--------------|
| `RefuelStarted` | inputs, issues_found | Workflow begins, after issue discovery |
| `IssueProcessingStarted` | issue, index, total | Each issue processing begins |
| `IssueProcessingCompleted` | result | Each issue processing completes |
| `RefuelCompleted` | result | Workflow finishes |

## Processing Flow Contract

### Phase 1: Issue Discovery (FR-014)

**Operations** (Python-only):
1. Fetch issues via GitHubCLIRunner.list_issues(label=inputs.label)
2. Apply limit: issues[:inputs.limit]
3. Filter by skip_if_assigned policy

**AI Involvement**: None

**Events**:
- RefuelStarted(inputs=inputs, issues_found=len(issues))

### Phase 2: Per-Issue Processing (FR-015, FR-016, FR-017)

For each issue (sequential by default, parallel if inputs.parallel=True):

#### Step 2a: Branch Creation (FR-015)

**Operations** (Python-only):
1. Create branch via GitRunner: `{config.branch_prefix}{issue.number}`

**AI Involvement**: None

#### Step 2b: Context Building (FR-016)

**Operations** (Python-only):
1. Aggregate issue context: title, body, labels, related files

**AI Involvement**: None

#### Step 2c: Issue Fixing (FR-017)

**Operations** (AI):
1. Execute IssueFixerAgent with file manipulation tools

**AI Involvement**: IssueFixerAgent with Read, Write, Edit, Glob, Grep, Bash

#### Step 2d: Validation

**Operations** (Python + conditional AI):
1. Run ValidationRunner
2. On failure, invoke fix agent
3. Retry per config

**AI Involvement**: Fix agent only on failure

#### Step 2e: Commit

**Operations** (Python + AI):
1. Get diff via GitRunner.diff()
2. Generate message via CommitMessageGenerator referencing issue
3. Commit via GitRunner.commit()

**AI Involvement**: CommitMessageGenerator (single-shot)

#### Step 2f: PR Creation

**Operations** (Python):
1. Push via GitRunner.push()
2. Create PR via GitHubCLIRunner.create_pr()
3. Add "Fixes #{issue.number}" if config.link_pr_to_issue

**AI Involvement**: None (PR body uses issue context, not AI-generated)

**Events** (per issue):
- IssueProcessingStarted(issue=issue, index=i, total=n)
- IssueProcessingCompleted(result=IssueProcessingResult)

### Phase 3: Aggregation (FR-019)

**Operations** (Python-only):
1. Aggregate results from all issues
2. Build RefuelResult summary

**Events**:
- RefuelCompleted(result=RefuelResult)

## Isolation Contract (FR-018)

Each issue MUST be processed with proper isolation:

1. **Branch Isolation**: Each issue gets unique branch `{prefix}{issue.number}`
2. **State Isolation**: Errors in one issue don't affect others
3. **Commit Isolation**: Each issue gets separate commits

```python
# Per-issue processing MUST be isolated
for issue in issues:
    try:
        result = await self._process_issue(issue)
        results.append(result)
    except Exception as e:
        # Capture error, continue with next issue
        results.append(IssueProcessingResult(
            issue=issue,
            status=IssueStatus.FAILED,
            branch=None,
            pr_url=None,
            error=str(e),
            duration_ms=...,
            agent_usage=AgentUsage(0, 0, None, 0),
        ))
```

## Dependency Injection Contract

```python
class RefuelWorkflow:
    def __init__(
        self,
        config: RefuelConfig | None = None,
        # Injectable dependencies
        git_runner: GitRunner | None = None,
        github_runner: GitHubCLIRunner | None = None,
        validation_runner: ValidationRunner | None = None,
        issue_fixer_agent: IssueFixerAgent | None = None,
        commit_generator: CommitMessageGenerator | None = None,
    ) -> None:
```

## Result Invariants

```python
# Must hold for RefuelResult
assert result.issues_processed == result.issues_fixed + result.issues_failed
assert len(result.results) == result.issues_found  # after limit
assert result.success == (result.issues_failed == 0)

# Must hold for each IssueProcessingResult
if result.status == IssueStatus.FIXED:
    assert result.branch is not None
    assert result.pr_url is not None
if result.status == IssueStatus.FAILED:
    assert result.error is not None
```

## Test Contract

### Unit Test Requirements

1. All runners and agents mocked
2. Test issue discovery with various label filters
3. Test per-issue isolation (one failure doesn't crash others)
4. Test branch naming pattern
5. Test sequential vs parallel processing
6. Verify no AI calls for deterministic operations (FR-014, FR-015)

### Example Test

```python
@pytest.mark.asyncio
async def test_refuel_processes_issues_in_isolation():
    mock_github = MagicMock()
    mock_github.list_issues = AsyncMock(return_value=[
        GitHubIssue(number=1, ...),
        GitHubIssue(number=2, ...),
        GitHubIssue(number=3, ...),
    ])

    mock_fixer = MagicMock()
    # First issue succeeds, second fails, third succeeds
    mock_fixer.execute = AsyncMock(side_effect=[
        AgentResult.success_result(...),
        AgentError("Something went wrong"),
        AgentResult.success_result(...),
    ])

    workflow = RefuelWorkflow(
        github_runner=mock_github,
        issue_fixer_agent=mock_fixer,
    )

    results = []
    async for event in workflow.execute(RefuelInputs(label="tech-debt")):
        if isinstance(event, RefuelCompleted):
            result = event.result

    # Verify isolation: 2 fixed, 1 failed, none skipped
    assert result.issues_fixed == 2
    assert result.issues_failed == 1
    assert result.success is False  # Because one failed
```

## Token Usage Contract

Token usage aggregated per-issue and across workflow:

```python
RefuelResult(
    success=...,
    issues_found=3,
    issues_processed=3,
    issues_fixed=2,
    issues_failed=1,
    issues_skipped=0,
    results=[...],  # Each has agent_usage
    total_duration_ms=sum(r.duration_ms for r in results),
    total_cost_usd=sum(r.agent_usage.total_cost_usd or 0 for r in results),
)
```
