# Research: Refuel Workflow Interface

**Date**: 2025-12-15
**Feature Branch**: `010-refuel-workflow`

## Research Tasks

### 1. Async Generator Pattern for Progress Events

**Decision**: Use `AsyncGenerator[RefuelProgressEvent, None]` as return type for `execute()`

**Rationale**:
- Matches FlyWorkflow pattern in `src/maverick/workflows/fly.py`
- Constitution I (Async-First) mandates async generators for TUI consumption
- Enables real-time progress reporting without blocking

**Alternatives Considered**:
- Callback-based events: Rejected - less composable, harder to test
- Return list of events: Rejected - no real-time updates

### 2. Dataclass Design Pattern

**Decision**: Use `@dataclass(frozen=True, slots=True)` for all data structures

**Rationale**:
- Constitution VI (Type Safety) mandates immutable value objects
- `frozen=True` enforces immutability at runtime
- `slots=True` improves memory efficiency and attribute access speed
- Matches existing AgentUsage pattern in `src/maverick/agents/result.py`

**Alternatives Considered**:
- Pydantic BaseModel: Used for RefuelConfig (needs validation/YAML integration); dataclasses for simple value objects
- Plain classes: Rejected - no built-in immutability

### 3. IssueStatus Enum Values

**Decision**: Define enum with values: PENDING, IN_PROGRESS, FIXED, FAILED, SKIPPED

**Rationale**:
- Covers complete issue lifecycle from spec requirements
- PENDING: Initial state before processing
- IN_PROGRESS: Currently being processed by agent
- FIXED: Successfully fixed and PR created
- FAILED: Processing failed (agent error, validation failure, etc.)
- SKIPPED: Skipped due to dry_run, skip_if_assigned, or other policy

**Alternatives Considered**:
- Using strings: Rejected - type safety violation
- More granular states: Rejected - simplicity principle

### 4. Configuration Integration Pattern

**Decision**: Add RefuelConfig as nested Pydantic BaseModel in MaverickConfig

**Rationale**:
- Matches FlyConfig integration pattern in `src/maverick/config.py`
- Enables YAML configuration loading via pydantic-settings
- Supports environment variable overrides (MAVERICK_REFUEL__*)

**Alternatives Considered**:
- Separate config file: Rejected - fragments configuration
- Flat config in MaverickConfig: Rejected - poor organization

### 5. GitHubIssue Definition Location

**Decision**: Define minimal GitHubIssue locally in `refuel.py`

**Rationale**:
- Spec assumption A-001 states local definition with minimal fields
- Avoids coupling to future GitHub tools spec
- Contains only fields needed for refuel workflow

**Alternatives Considered**:
- Import from github tools: Doesn't exist yet (future spec)
- Define in shared models module: Over-engineering for single use case

### 6. Progress Event Union Type

**Decision**: Create `RefuelProgressEvent` as union type for type-safe event handling

**Rationale**:
- Matches FlyProgressEvent pattern in fly.py
- Enables exhaustive pattern matching in TUI code
- Type-safe event dispatch

**Pattern**:
```python
RefuelProgressEvent = (
    RefuelStarted
    | IssueProcessingStarted
    | IssueProcessingCompleted
    | RefuelCompleted
)
```

**Alternatives Considered**:
- Base class with subclasses: More verbose, no pattern matching benefit
- Generic Event[T]: Over-engineered for this use case

## Dependencies Confirmed

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Pattern matching, type hints |
| dataclasses | stdlib | Frozen/slots dataclasses |
| Pydantic | 2.x | RefuelConfig validation |
| asyncio | stdlib | Async generator support |

## Open Questions

*None - all technical decisions resolved.*
