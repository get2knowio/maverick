# Research: Validation Workflow

**Feature**: 008-validation-workflow
**Date**: 2025-12-15

## Research Areas

### 1. Async Generator Patterns for Progress Updates

**Decision**: Use `AsyncIterator[ProgressUpdate]` yielded from workflow's `run()` method.

**Rationale**:
- Constitution I mandates async-first with async generators for TUI consumption
- Existing patterns in `MaverickAgent.query()` use `AsyncIterator[Message]` for streaming
- TUI can consume progress via `async for progress in workflow.run()` pattern
- Enables real-time updates without blocking

**Alternatives Considered**:
1. Callback-based progress reporting - Rejected: harder to compose, less Pythonic
2. Event emitter pattern - Rejected: adds complexity, less type-safe than async iterators
3. Queue-based pattern - Rejected: unnecessary indirection for single consumer

**Implementation Pattern**:
```python
async def run(self) -> AsyncIterator[ProgressUpdate]:
    for stage in self._stages:
        yield ProgressUpdate(stage=stage.name, status=StageStatus.IN_PROGRESS)
        # ... execute stage ...
        yield ProgressUpdate(stage=stage.name, status=StageStatus.PASSED)
```

### 2. Fix Agent Injection Pattern

**Decision**: Constructor injection following existing workflow/agent patterns.

**Rationale**:
- Constitution III mandates dependency injection over global state
- Existing agents (ImplementerAgent, IssueFixerAgent) use constructor injection for model and mcp_servers
- Spec clarification confirms "Follow existing pattern for agent injection into workflows"
- Enables testing with mock fix agents

**Alternatives Considered**:
1. Factory method pattern - Rejected: less explicit, harder to test
2. Method injection - Rejected: less consistent, agent needed throughout workflow
3. Global registry - Rejected: violates Constitution III (no global state)

**Implementation Pattern**:
```python
class ValidationWorkflow:
    def __init__(
        self,
        stages: list[ValidationStage],
        fix_agent: MaverickAgent | None = None,  # Optional - some workflows may not need fixing
        config: ValidationWorkflowConfig | None = None,
    ) -> None:
        self._stages = stages
        self._fix_agent = fix_agent
        self._config = config or ValidationWorkflowConfig()
```

### 3. Cancellation Pattern

**Decision**: Use `asyncio.Event` for cancellation flag with cooperative checking.

**Rationale**:
- SC-005 requires cancellation within 5 seconds
- Stage execution is async subprocess-based (from `src/maverick/utils/validation.py`)
- Cooperative cancellation with check points is standard Python asyncio pattern
- Can terminate running subprocess on cancellation

**Alternatives Considered**:
1. asyncio.Task.cancel() only - Rejected: doesn't cleanly terminate subprocesses
2. Threading with signals - Rejected: violates Constitution I (async-first)
3. Context managers with cleanup - Considered but adds complexity without benefit

**Implementation Pattern**:
```python
class ValidationWorkflow:
    def __init__(self, ...):
        self._cancel_event = asyncio.Event()

    def cancel(self) -> None:
        """Request workflow cancellation."""
        self._cancel_event.set()

    async def run(self) -> AsyncIterator[ProgressUpdate]:
        for stage in self._stages:
            if self._cancel_event.is_set():
                yield ProgressUpdate(stage=stage.name, status=StageStatus.CANCELLED)
                return
            # ... execute stage with cancellation checks ...
```

### 4. Existing Validation Infrastructure

**Decision**: Reuse `src/maverick/utils/validation.py` and `src/maverick/tools/validation.py` patterns.

**Rationale**:
- `ValidationStep` enum already exists in `src/maverick/models/implementation.py`
- `run_validation_step()` and `run_validation_pipeline()` in `src/maverick/utils/validation.py`
- MCP tools in `src/maverick/tools/validation.py` for agent-based fixes
- Consistent with existing codebase patterns

**Relevant Existing Code**:
- `ValidationStep` enum: FORMAT, LINT, TYPECHECK, TEST
- `ValidationResult` model with step, success, output, duration_ms, auto_fixed
- `run_validation_step()`: async command execution with timeout
- `create_validation_tools_server()`: MCP tools for agents

**Gap Analysis**:
- Need new `ValidationStage` model (different from `ValidationStep`) with fixability and max_attempts
- Need new `StageResult` with fix attempt tracking (distinct from existing `ValidationResult`)
- Need workflow-level orchestration (not just pipeline)
- Need progress update model

### 5. Stage Configuration Model

**Decision**: New `ValidationStage` Pydantic model with command, fixability, and retry config.

**Rationale**:
- FR-003 to FR-005 require configurable stages with commands, fixability, and max attempts
- Distinct from existing `ValidationStep` which is just an enum
- Pydantic model enables validation and serialization
- Follows Constitution VI (Type Safety)

**Implementation Pattern**:
```python
class ValidationStage(BaseModel):
    """A single validation stage configuration."""
    name: str
    command: list[str]
    fixable: bool = True
    max_fix_attempts: int = Field(default=3, ge=0)
    timeout_seconds: float = Field(default=300.0, gt=0)

    model_config = ConfigDict(frozen=True)
```

### 6. Result Model Design

**Decision**: Separate `StageResult` from existing `ValidationResult`; new `ValidationWorkflowResult`.

**Rationale**:
- FR-014 to FR-017 require structured results with fix attempt tracking
- Existing `ValidationResult` doesn't track fix attempts or stage status beyond success/fail
- Need workflow-level aggregate result with per-stage breakdown
- Follows existing pattern of specific result models per feature

**Implementation Pattern**:
```python
class StageStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    FIXED = "fixed"  # Passed after fix attempts
    CANCELLED = "cancelled"

class StageResult(BaseModel):
    stage_name: str
    status: StageStatus
    fix_attempts: int = 0
    error_message: str | None = None
    output: str = ""
    duration_ms: int = 0

class ValidationWorkflowResult(BaseModel):
    success: bool
    stage_results: list[StageResult]
    cancelled: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 7. Progress Update Model

**Decision**: Simple ProgressUpdate dataclass for async generator yields.

**Rationale**:
- FR-010 requires progress updates as async events
- TUI needs current stage, status, and contextual info
- Keep lightweight for frequent emission
- Use slots for performance (Constitution VI guidance)

**Implementation Pattern**:
```python
@dataclass(slots=True, frozen=True)
class ProgressUpdate:
    stage: str
    status: StageStatus
    message: str = ""
    fix_attempt: int = 0
    timestamp: float = field(default_factory=time.time)
```

### 8. Dry-Run Implementation

**Decision**: Check dry_run flag before executing commands; emit what-would-run info.

**Rationale**:
- FR-011 requires dry-run mode that reports without execution
- Simple conditional check in execution loop
- Return planned actions in progress updates

**Implementation Pattern**:
```python
async def _execute_stage(self, stage: ValidationStage) -> StageResult:
    if self._config.dry_run:
        yield ProgressUpdate(stage=stage.name, status=StageStatus.PENDING,
                             message=f"Would run: {' '.join(stage.command)}")
        return StageResult(stage_name=stage.name, status=StageStatus.PASSED)
    # ... actual execution ...
```

### 9. Default Stage Commands

**Decision**: Provide Python defaults matching existing config; support custom commands per stage.

**Rationale**:
- FR-013 requires defaults for common project types (starting with Python per existing codebase)
- Existing `ValidationConfig` in `src/maverick/config.py` has Python defaults (ruff, mypy, pytest)
- Custom commands configurable per stage via `ValidationStage.command`

**Default Configuration**:
```python
DEFAULT_PYTHON_STAGES = [
    ValidationStage(name="format", command=["ruff", "format", "."], fixable=True),
    ValidationStage(name="lint", command=["ruff", "check", "--fix", "."], fixable=True),
    ValidationStage(name="typecheck", command=["mypy", "."], fixable=True, max_fix_attempts=2),
    ValidationStage(name="test", command=["pytest", "-x", "--tb=short"], fixable=False),
]
```

### 10. Edge Case Handling

**Decision**: Follow spec edge case guidance with explicit handling.

**Edge Cases from Spec**:
1. **Command not found/fails to start**: Mark stage failed immediately, no fix attempts, continue
2. **Fix agent produces no changes**: Count as fix attempt, retry stage (uniform behavior)
3. **Stages never re-run**: Each stage executes once (with fix retries), report final state
4. **max_fix_attempts = 0**: Treat as non-fixable, skip fix agent
5. **Same error persists across fix attempts**: Exhaust attempts, mark failed, continue to next
6. **Cancellation during fix attempt**: Stop at earliest safe point, report partial results

**Implementation**:
- FileNotFoundError caught at stage execution = immediate fail
- Fix agent invocation checks for changes via git diff
- Counter tracks attempts per stage
- Cancellation check between fix attempts

## Technology Summary

| Component | Technology | Notes |
|-----------|------------|-------|
| Language | Python 3.10+ | `from __future__ import annotations` |
| Models | Pydantic | Frozen models for immutability |
| Async | asyncio | Async generators for progress |
| Testing | pytest-asyncio | All tests async-compatible |
| Command Execution | asyncio.subprocess | Existing pattern from utils/validation.py |

## Dependencies

- **Internal**: `maverick.models.implementation.ValidationStep` (existing enum reference)
- **Internal**: `maverick.utils.validation` (pattern reference, may refactor)
- **Internal**: `maverick.agents.base.MaverickAgent` (fix agent type)
- **External**: Pydantic v2 (already in project)
- **External**: asyncio (stdlib)

## Open Questions Resolved

All NEEDS CLARIFICATION items from spec have been resolved in Clarifications section:
- Command failure handling: fail-fast per stage, continue workflow
- Fix agent injection: constructor injection
- Stage re-runs: no re-runs, single execution with fix retries
- No-change fixes: count as attempt, retry
- Zero max_attempts: treat as non-fixable
