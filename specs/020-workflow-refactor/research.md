# Research: Workflow Refactor to Python-Orchestrated Pattern

**Feature**: 020-workflow-refactor
**Date**: 2025-12-18
**Status**: Complete

## Research Questions

1. How to implement focused single-purpose AI calls vs full agent executions?
2. What async workflow orchestration patterns should be used?
3. How to test async workflows with mocked dependencies?

---

## Decision 1: Focused AI Calls vs Full Agent Executions

**Decision**: Use `GeneratorAgent` pattern for text generation tasks; use `MaverickAgent` with `ClaudeSDKClient` for multi-turn tool interactions.

**Rationale**:
- Generator agents use `query()` function with `allowed_tools=[]` and `max_turns=1`
- No tool overhead, lightweight single-shot execution
- Full agents use `ClaudeSDKClient` context manager for stateful multi-turn interactions
- Existing generators (CommitMessageGenerator, PRDescriptionGenerator) provide proven patterns

**Alternatives Considered**:
- Single agent type for all tasks: Rejected because tool validation overhead and multi-turn capability unnecessary for text generation
- Custom query wrapper: Rejected because GeneratorAgent pattern already exists and is well-tested

**Task Categorization**:

| Task | Pattern | Tools | Token Savings |
|------|---------|-------|---------------|
| Commit message generation | GeneratorAgent | None | 60-70% |
| PR description generation | GeneratorAgent | None | 50-60% |
| Error explanation | GeneratorAgent | None | 60-70% |
| Code implementation | MaverickAgent | Read, Write, Edit, Glob, Grep, Bash | 0% (necessary) |
| Validation fix | MaverickAgent | Read, Write, Edit, Glob, Grep | 0% (necessary) |
| Code review interpretation | MaverickAgent | Read, Glob, Grep | 0% (necessary) |

**Implementation References**:
- `/workspaces/maverick/src/maverick/agents/generators/base.py` - GeneratorAgent ABC
- `/workspaces/maverick/src/maverick/agents/generators/commit_message.py` - CommitMessageGenerator
- `/workspaces/maverick/src/maverick/agents/generators/pr_description.py` - PRDescriptionGenerator
- `/workspaces/maverick/src/maverick/agents/base.py` - MaverickAgent with ClaudeSDKClient

---

## Decision 2: Tool Scoping and Permission Management

**Decision**: Use explicit `allowed_tools` lists validated at agent construction time.

**Rationale**:
- Principle of least privilege enforced at build time (not runtime)
- Unknown tools raise `InvalidToolError` immediately
- Tool validation happens once, not per-execution
- Existing pattern proven in ImplementerAgent, CodeReviewerAgent

**Tool Permission Matrix**:

| Agent | Allowed Tools | Justification |
|-------|---------------|---------------|
| ImplementerAgent | Read, Write, Edit, Bash, Glob, Grep | File manipulation for code implementation |
| CodeReviewerAgent | Read, Glob, Grep, Bash | Read-only analysis of code changes |
| IssueFixerAgent | Read, Write, Edit, Bash, Glob, Grep | Targeted bug fixes |
| ValidationFixerAgent | Read, Write, Edit, Glob, Grep | Fix validation failures (no Bash) |
| CommitMessageGenerator | None | Pure text generation |
| PRDescriptionGenerator | None | Pure text generation |

**Implementation Reference**:
- `/workspaces/maverick/src/maverick/agents/base.py:145-178` - Tool validation logic

---

## Decision 3: Token Usage Tracking

**Decision**: Extract usage from `ResultMessage` using existing `_extract_usage()` pattern; aggregate across workflow stages.

**Rationale**:
- Claude Agent SDK returns usage in `ResultMessage.usage` dict
- Existing `AgentUsage` dataclass provides immutable structure
- Aggregation at workflow level enables comparison against baseline

**Implementation Pattern**:
```python
def _extract_usage(self, messages: list[Message]) -> AgentUsage:
    result_msg = next((m for m in messages if type(m).__name__ == "ResultMessage"), None)
    if result_msg is None:
        return AgentUsage(input_tokens=0, output_tokens=0, total_cost_usd=None, duration_ms=0)
    usage = getattr(result_msg, "usage", None) or {}
    return AgentUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        total_cost_usd=getattr(result_msg, "total_cost_usd", None),
        duration_ms=getattr(result_msg, "duration_ms", 0),
    )
```

**Implementation Reference**:
- `/workspaces/maverick/src/maverick/agents/base.py:251-285` - Usage extraction
- `/workspaces/maverick/src/maverick/agents/result.py` - AgentUsage dataclass

---

## Decision 4: Async Generator Progress Pattern

**Decision**: Use ValidationWorkflow pattern - async generator yielding frozen progress events, with nested stage generators.

**Rationale**:
- Proven pattern in ValidationWorkflow (496 lines, fully functional)
- Real-time progress updates via lazy async generator evaluation
- Immutable events (`@dataclass(frozen=True, slots=True)`)
- Type-safe with explicit `AsyncIterator[ProgressUpdate]` return types

**Core Pattern**:
```python
async def run(self) -> AsyncIterator[ProgressUpdate]:
    stage_results: list[StageResult] = []
    for stage in self._stages:
        if self._cancel_event.is_set():
            yield ProgressUpdate(stage=stage.name, status=CANCELLED)
            continue
        async for progress, result in self._run_stage(stage):
            yield progress
            if result is not None:
                stage_results.append(result)
        if self._config.stop_on_failure and stage_results[-1].status == FAILED:
            break
    self._result = WorkflowResult(stage_results=stage_results, ...)
```

**Alternatives Considered**:
- Callback-based progress: Rejected because async generators compose better and are native Python
- Event emitter pattern: Rejected because more complex and not idiomatic asyncio
- Polling-based: Rejected because inefficient and adds latency

**Implementation Reference**:
- `/workspaces/maverick/src/maverick/workflows/validation.py:380-431` - Main run() pattern

---

## Decision 5: Stage Sequencing with Early Exit

**Decision**: Sequential stage execution with configurable stop-on-failure policy and cooperative cancellation via `asyncio.Event`.

**Rationale**:
- Deterministic ordering ensures predictable workflow behavior
- Early exit prevents wasted work after critical failures
- Cooperative cancellation allows graceful degradation (in-flight work completes)
- Non-blocking cancellation via `Event.set()` callable from TUI thread

**Cancellation Mechanism**:
```python
class Workflow:
    def __init__(self):
        self._cancel_event = asyncio.Event()

    def cancel(self) -> None:
        self._cancel_event.set()  # Non-blocking

    async def run(self):
        for stage in stages:
            if self._cancel_event.is_set():
                # Mark remaining stages as cancelled
                break
```

**Implementation Reference**:
- `/workspaces/maverick/src/maverick/workflows/validation.py:396-430` - Sequential execution
- `/workspaces/maverick/src/maverick/workflows/validation.py:449-451` - Cancel method

---

## Decision 6: Error Isolation Without Workflow Crash

**Decision**: Catch exceptions per-stage and return structured results; never propagate exceptions from stage execution.

**Rationale**:
- Constitution principle IV (Fail Gracefully) requires partial success preservation
- CommandResult includes error flags (`timed_out`, `command_not_found`, `error`)
- StageResult captures failure state without crashing workflow
- Fix agent exceptions logged but don't crash (isolated try/except)

**Pattern**:
```python
async def _run_stage(self, stage) -> AsyncIterator[tuple[ProgressUpdate, StageResult | None]]:
    try:
        result = await self._execute_command(stage)
        if result.command_not_found or result.timed_out:
            yield (ProgressUpdate(...), StageResult(status=FAILED, error_message=result.error))
            return
        # ... handle success/retry
    except Exception as e:
        logger.error(f"Unexpected error in stage {stage.name}: {e}")
        yield (ProgressUpdate(...), StageResult(status=FAILED, error_message=str(e)))
```

**Implementation Reference**:
- `/workspaces/maverick/src/maverick/workflows/validation.py:149-178` - Fix agent error isolation
- `/workspaces/maverick/src/maverick/workflows/validation.py:85-147` - Command execution error handling

---

## Decision 7: Retry Logic with Fix Agent

**Decision**: Bounded retry loop with fix agent invocation between attempts; immediate retry (no exponential backoff).

**Rationale**:
- Fix agent modifies code between retries (not transient error recovery)
- Immediate retry appropriate because state changes between attempts
- Bounded retries prevent infinite loops (configurable `max_fix_attempts`)
- Fix attempt counter visible in progress updates for user awareness

**Pattern**:
```python
while can_fix and fix_attempts < stage.max_fix_attempts:
    fix_attempts += 1
    yield ProgressUpdate(message=f"Fix attempt #{fix_attempts}")
    await self._invoke_fix_agent(stage, last_error)
    result = await self._execute_command(stage)
    if result.return_code == 0:
        yield (ProgressUpdate(status=FIXED), StageResult(status=FIXED, fix_attempts=fix_attempts))
        return
    last_error = result.stderr
```

**Alternatives Considered**:
- Exponential backoff: Rejected because fixes are code changes, not transient network issues
- Unbounded retries: Rejected because constitution requires bounded attempts (default 3)

**Implementation Reference**:
- `/workspaces/maverick/src/maverick/workflows/validation.py:289-378` - Retry loop

---

## Decision 8: Testing Async Workflows

**Decision**: Use AsyncMock for async methods, inject mocked runners via constructor, consume async generators with `async for`.

**Rationale**:
- AsyncMock required for `async def` methods (not regular MagicMock)
- Constructor injection enables clean test isolation
- `async for` is idiomatic way to consume async generators
- Existing test patterns in test_validation.py proven and comprehensive

**Test Pattern**:
```python
@pytest.mark.asyncio
async def test_workflow_stage_execution(mock_fix_agent):
    workflow = ValidationWorkflow(
        stages=stages,
        fix_agent=mock_fix_agent,  # Injected mock
        config=config,
    )

    with patch("asyncio.create_subprocess_exec", AsyncMock()) as mock_exec:
        mock_exec.return_value = mock_process

        progress_updates = []
        async for update in workflow.run():
            progress_updates.append(update)

        result = workflow.get_result()
        assert result.success is True
        mock_fix_agent.execute.assert_not_called()
```

**Key Fixtures**:
- `temp_dir`: Temporary directory with cwd restoration
- `clean_env`: MAVERICK_ environment variable isolation
- `MockSDKClient`: Queue-based agent response mocking
- `MockGitHubCLI`: Pattern-based CLI response mocking

**Implementation Reference**:
- `/workspaces/maverick/tests/unit/workflows/test_validation.py` - Workflow test patterns
- `/workspaces/maverick/tests/fixtures/agents.py` - MockSDKClient
- `/workspaces/maverick/tests/fixtures/github.py` - MockGitHubCLI
- `/workspaces/maverick/tests/conftest.py` - Core fixtures

---

## Decision 9: GitRunner Abstraction

**Decision**: Create new async `GitRunner` class wrapping git CLI operations, following CommandRunner pattern.

**Rationale**:
- Existing `git_operations.py` is synchronous; workflows require async
- CommandRunner provides proven subprocess handling (timeout, SIGTERM/SIGKILL)
- Git operations are deterministic - no AI involvement needed
- Injectable for testing with mock responses

**Interface Design**:
```python
class GitRunner:
    def __init__(self, command_runner: CommandRunner | None = None):
        self._runner = command_runner or CommandRunner()

    async def create_branch(self, branch_name: str) -> GitResult:
        """Create and checkout new branch."""

    async def checkout(self, ref: str) -> GitResult:
        """Checkout existing branch or commit."""

    async def commit(self, message: str, allow_empty: bool = False) -> GitResult:
        """Create commit with staged changes."""

    async def push(self, remote: str = "origin", force: bool = False) -> GitResult:
        """Push current branch to remote."""

    async def diff(self, base: str = "HEAD") -> str:
        """Get diff output for commit message generation."""
```

**Alternatives Considered**:
- Extend existing `git_operations.py`: Rejected because it's synchronous and uses threading
- Use MCP git tools: Rejected because adds unnecessary AI token overhead

---

## Summary: Token Savings Analysis

**Baseline**: Current workflow routes all operations through agents with full tool access.

**Optimized**: Python orchestration with focused AI calls only where judgment needed.

| Operation | Baseline | Optimized | Savings |
|-----------|----------|-----------|---------|
| Branch creation | Agent tool call | GitRunner | 100% |
| Task file parsing | Agent tool call | Python file I/O | 100% |
| Validation stages | Agent tool call | ValidationRunner | 100% |
| GitHub operations | Agent tool call | GitHubCLIRunner | 100% |
| Commit messages | Full agent | GeneratorAgent | 60-70% |
| PR descriptions | Full agent | GeneratorAgent | 50-60% |
| Code implementation | Full agent | Full agent | 0% |
| Validation fixes | Full agent | Full agent | 0% |
| Code review | Full agent | Full agent | 0% |

**Estimated Total Savings**: 40-60% (SC-001 target achieved)
