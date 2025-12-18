# Tasks: Base Agent Abstraction Layer

**Input**: Design documents from `/specs/002-base-agent/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Tests**: Unit tests included per Constitution V (Test-First principle).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root (per plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and error hierarchy

- [x] T001 Create agents module directory structure at src/maverick/agents/
- [x] T002 Create agents package __init__.py with public API exports in src/maverick/agents/__init__.py
- [x] T003 [P] Add AgentError exception hierarchy to src/maverick/exceptions.py (CLINotFoundError, ProcessError, TimeoutError, NetworkError, StreamingError, MalformedResponseError, InvalidToolError, DuplicateAgentError, AgentNotFoundError)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core dataclasses that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [P] Create AgentUsage dataclass (frozen, slots) in src/maverick/agents/result.py with input_tokens, output_tokens, total_cost_usd, duration_ms fields and total_tokens computed property
- [x] T005 [P] Create AgentResult dataclass (frozen, slots) in src/maverick/agents/result.py with success, output, metadata, errors, usage fields and success_result/failure_result factory methods
- [x] T006 [P] Create AgentContext dataclass (frozen, slots) in src/maverick/agents/context.py with cwd, branch, config, extra fields and from_cwd factory method
- [x] T007 [P] Create BUILTIN_TOOLS constant (frozenset), DEFAULT_MODEL constant, and DEFAULT_PERMISSION_MODE constant in src/maverick/agents/base.py

**Checkpoint**: Foundation ready - unit tests can now be written

---

## Phase 3: Unit Tests (Constitution V: Test-First)

**Purpose**: Tests written before implementation per TDD Red-Green-Refactor

- [x] T008 [P] Create tests/unit/agents/test_result.py with tests for AgentUsage and AgentResult dataclasses (frozen, computed properties, factory methods, error requirement for failure)
- [x] T009 [P] Create tests/unit/agents/test_context.py with tests for AgentContext dataclass (frozen, from_cwd factory)
- [x] T010 [P] Create tests/unit/agents/test_registry.py with tests for AgentRegistry (register, get, list_agents, create, DuplicateAgentError, AgentNotFoundError)
- [x] T011 [P] Create tests/unit/agents/test_utils.py with tests for extract_text and extract_all_text functions
- [x] T012 Create tests/unit/agents/test_base.py with tests for MaverickAgent (_validate_tools, _build_options, _wrap_sdk_error, query)

**Checkpoint**: All tests written and failing (Red phase) - implementation can begin

---

## Phase 4: User Story 1 - Create a Simple Agent (Priority: P1)

**Goal**: Developers can create a fully functional agent by defining a system prompt and implementing execute() - no additional boilerplate required

**Independent Test**: Create a minimal GreeterAgent with a system prompt, call execute() with an AgentContext, verify it returns a structured AgentResult

### Implementation for User Story 1

- [x] T013 [US1] Create MaverickAgent abstract base class in src/maverick/agents/base.py with name, system_prompt, allowed_tools, model properties and __init__ accepting mcp_servers parameter
- [x] T014 [US1] Implement _validate_tools() method in src/maverick/agents/base.py to validate allowed_tools against BUILTIN_TOOLS and MCP tool patterns (mcp__<server>__<tool>), raising InvalidToolError for unknown tools
- [x] T015 [US1] Implement _build_options() method in src/maverick/agents/base.py to create ClaudeAgentOptions with sensible defaults (permission_mode, model, system_prompt, allowed_tools, mcp_servers)
- [x] T016 [US1] Add abstract async execute(context: AgentContext) -> AgentResult method to MaverickAgent in src/maverick/agents/base.py
- [x] T017 [US1] Implement _wrap_sdk_error() method in src/maverick/agents/base.py to map Claude SDK errors (CLINotFoundError, ProcessError, CLIConnectionError, CLIJSONDecodeError) to Maverick error hierarchy
- [x] T018 [US1] Implement _extract_usage() helper method in src/maverick/agents/base.py to extract AgentUsage from ResultMessage

**Checkpoint**: User Story 1 complete - developers can create agents by subclassing MaverickAgent

---

## Phase 5: User Story 2 - Stream Agent Responses (Priority: P2)

**Goal**: Developers can stream responses from agents for real-time TUI display using an async iterator

**Independent Test**: Call query() on an agent, verify messages arrive incrementally via async iterator

### Implementation for User Story 2

- [x] T019 [US2] Implement async query(prompt, cwd) -> AsyncIterator[Message] method in src/maverick/agents/base.py using ClaudeSDKClient with receive_response() for streaming
- [x] T020 [US2] Add mid-stream failure handling in query() to yield partial content before raising StreamingError in src/maverick/agents/base.py

**Checkpoint**: User Story 2 complete - streaming responses work for TUI integration

---

## Phase 6: User Story 3 - Discover and Instantiate Agents (Priority: P2)

**Goal**: Workflows can dynamically discover agents and instantiate them by name via the registry

**Independent Test**: Register agents, look them up by name, instantiate with config

### Implementation for User Story 3

- [x] T021 [US3] Create AgentRegistry class in src/maverick/agents/registry.py with _agents dict and register(name, cls) method raising DuplicateAgentError on duplicates
- [x] T022 [US3] Add get(name) method to AgentRegistry in src/maverick/agents/registry.py raising AgentNotFoundError for unknown names
- [x] T023 [US3] Add list_agents() method returning list[str] to AgentRegistry in src/maverick/agents/registry.py
- [x] T024 [US3] Add create(name, **kwargs) method to AgentRegistry in src/maverick/agents/registry.py to lookup and instantiate agents
- [x] T025 [US3] Add @register decorator support to AgentRegistry in src/maverick/agents/registry.py for class-level registration
- [x] T026 [US3] Create module-level registry singleton instance in src/maverick/agents/registry.py

**Checkpoint**: User Story 3 complete - workflows can discover and create agents dynamically

---

## Phase 7: User Story 4 - Extract Structured Output (Priority: P3)

**Goal**: Developers can extract clean text from AssistantMessage objects without manual parsing

**Independent Test**: Pass AssistantMessage objects to extract utilities, verify correct text extraction

### Implementation for User Story 4

- [x] T027 [P] [US4] Create extract_text(message) function in src/maverick/agents/utils.py to extract text content from a single AssistantMessage (FR-006)
- [x] T028 [P] [US4] Create extract_all_text(messages) function in src/maverick/agents/utils.py to extract and concatenate text from multiple messages (FR-006)

**Checkpoint**: User Story 4 complete - text extraction utilities available

---

## Phase 8: User Story 5 - Handle Agent Errors Gracefully (Priority: P3)

**Goal**: Errors during execution are caught, wrapped with context, and returned in structured format

**Independent Test**: Simulate error conditions (missing CLI, process error), verify structured error responses

### Implementation for User Story 5

- [x] T029 [US5] Add try/except in query() method to catch SDK exceptions and wrap them via _wrap_sdk_error() in src/maverick/agents/base.py
- [x] T030 [US5] Update failure_result() factory to require at least one error when success=False per FR-008 in src/maverick/agents/result.py

**Checkpoint**: User Story 5 complete - all agent errors are gracefully handled and wrapped

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, exports, and validation

- [x] T031 Update src/maverick/agents/__init__.py to export MaverickAgent, AgentResult, AgentUsage, AgentContext, AgentRegistry, registry, extract_text, extract_all_text
- [x] T032 Add type alias AgentMessage = Message to src/maverick/agents/__init__.py
- [x] T033 Run quickstart.md validation - verify code examples work with implemented classes
- [x] T034 Create tests/integration/agents/test_performance.py with timing assertions for SC-002 (<100ms overhead) and SC-003 (<500ms to first yield) using mocked Claude responses

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T003) - BLOCKS all user stories
- **Unit Tests (Phase 3)**: Depends on Phase 2 - write tests against interfaces before implementation
- **User Story 1 (Phase 4)**: Depends on Phase 3 - core agent abstraction (make tests pass)
- **User Story 2 (Phase 5)**: Depends on T013-T017 (base agent class must exist)
- **User Story 3 (Phase 6)**: Depends on Phase 3 only (registry is independent of streaming)
- **User Story 4 (Phase 7)**: Depends on Phase 3 only (utilities are independent)
- **User Story 5 (Phase 8)**: Depends on T029 (query method must exist for error wrapping)
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Core agent abstraction - no dependencies on other stories
- **User Story 2 (P2)**: Streaming - depends on base agent (US1)
- **User Story 3 (P2)**: Registry - can run parallel to US1/US2 after Phase 3
- **User Story 4 (P3)**: Utilities - can run parallel to all stories after Phase 3
- **User Story 5 (P3)**: Error handling - depends on query() existing (US2)

### Within Each User Story

- Foundation tasks before implementation
- Core methods before helpers
- Private methods before public methods that use them

### Parallel Opportunities

**Phase 2 (Foundational)**: All 4 tasks (T004-T007) can run in parallel - different files

**Phase 3 (Unit Tests)**: Tasks T008-T011 can run in parallel - different test files

**After Phase 3 completes**:
- US1 (T013-T018): Sequential - building base class incrementally
- US3 (T021-T026): Can run in parallel with US1 - separate file
- US4 (T027-T028): Can run in parallel with US1/US3 - separate file

**After US1 completes**:
- US2 (T019-T020): Sequential - depends on US1
- US5 (T029-T030): Sequential - depends on US2

---

## Parallel Example: Foundational Phase

```bash
# Launch all foundational tasks together (Phase 2):
Task: "Create AgentUsage dataclass in src/maverick/agents/result.py"
Task: "Create AgentResult dataclass in src/maverick/agents/result.py"  # Same file but different classes
Task: "Create AgentContext dataclass in src/maverick/agents/context.py"
Task: "Create constants in src/maverick/agents/base.py"
```

## Parallel Example: Unit Tests Phase

```bash
# Launch all test tasks together (Phase 3):
Task: "Create tests for AgentUsage/AgentResult in tests/unit/agents/test_result.py"
Task: "Create tests for AgentContext in tests/unit/agents/test_context.py"
Task: "Create tests for AgentRegistry in tests/unit/agents/test_registry.py"
Task: "Create tests for extract utilities in tests/unit/agents/test_utils.py"
# T012 (test_base.py) depends on others due to MaverickAgent complexity
```

## Parallel Example: After Phase 3

```bash
# Launch US1, US3, US4 in parallel (different files):
Task: "Create MaverickAgent base class in src/maverick/agents/base.py"  # US1
Task: "Create AgentRegistry in src/maverick/agents/registry.py"         # US3
Task: "Create extract utilities in src/maverick/agents/utils.py"        # US4
```

---

## Implementation Strategy

### TDD Flow (Red-Green-Refactor)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T007) - create stub files with dataclass signatures
3. Complete Phase 3: Unit Tests (T008-T012) - write failing tests
4. **RED**: All tests fail (implementations are stubs)
5. Complete Phases 4-8: Implement code to make tests pass
6. **GREEN**: All tests pass
7. Complete Phase 9: Polish and integration tests
8. **REFACTOR**: Clean up as needed

### MVP First (User Story 1 Only)

1. Complete Phases 1-3: Setup, Foundation, Tests
2. Complete Phase 4: User Story 1 (T013-T018)
3. **STOP and VALIDATE**: Run tests, verify GreeterAgent executes
4. MVP complete - basic agent abstraction works

### Incremental Delivery

1. Setup + Foundational + Tests → Framework ready
2. Add User Story 1 → Test creating agents → Core MVP
3. Add User Story 2 → Test streaming → TUI ready
4. Add User Story 3 → Test registry → Workflows ready
5. Add User Story 4/5 → Test utilities and errors → Full feature
6. Each story adds value without breaking previous stories

### Recommended Order (Single Developer)

1. T001-T003 (Setup)
2. T004-T007 (Foundational) - all parallel
3. T008-T012 (Unit Tests) - T008-T011 parallel, then T012
4. T013-T018 (US1 - Create Agent)
5. T019-T020 (US2 - Streaming)
6. T021-T026 (US3 - Registry)
7. T027-T028 (US4 - Utilities) - parallel
8. T029-T030 (US5 - Error Handling)
9. T031-T034 (Polish)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Unit tests included per Constitution V (Test-First principle)
- All async methods per FR-013 async-first principle
- AgentUsage and AgentResult in same file (result.py) but logically separate
- Commit after each task or logical group
