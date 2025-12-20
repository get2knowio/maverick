# Tasks: Agent Tool Permissions

**Input**: Design documents from `/specs/021-agent-tool-permissions/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Unit tests are REQUIRED per FR-010 specification requirement.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the centralized tool constants module

- [X] T001 Create tool permission constants module in src/maverick/agents/tools.py
- [X] T002 Update src/maverick/agents/__init__.py to export tool constants
- [X] T003 [P] Create test file structure in tests/unit/agents/test_tools.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Verify tool sets are valid and properly typed

**⚠️ CRITICAL**: All tool constant tests must pass before agent updates

- [X] T004 Implement REVIEWER_TOOLS constant in src/maverick/agents/tools.py
- [X] T005 [P] Implement IMPLEMENTER_TOOLS constant in src/maverick/agents/tools.py
- [X] T006 [P] Implement FIXER_TOOLS constant in src/maverick/agents/tools.py
- [X] T007 [P] Implement ISSUE_FIXER_TOOLS constant in src/maverick/agents/tools.py
- [X] T008 [P] Implement GENERATOR_TOOLS constant in src/maverick/agents/tools.py
- [X] T009 Write unit tests for tool set validation in tests/unit/agents/test_tools.py

**Checkpoint**: Tool constants module complete and tested - agent updates can now begin

---

## Phase 3: User Story 1 - Constrained Agent Execution (Priority: P1) 🎯 MVP

**Goal**: Remove Bash and unnecessary tools from all agents, enforce orchestration pattern

**Independent Test**: Execute each agent type and verify they only have access to their designated tool set

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T010 [P] [US1] Write test for ImplementerAgent allowed_tools in tests/unit/agents/test_implementer.py
- [X] T011 [P] [US1] Write test for CodeReviewerAgent allowed_tools in tests/unit/agents/test_code_reviewer.py
- [X] T012 [P] [US1] Write test for IssueFixerAgent allowed_tools in tests/unit/agents/test_issue_fixer.py
- [X] T013 [P] [US1] Write test for GeneratorAgent allowed_tools in tests/unit/agents/test_generators.py

### Implementation for User Story 1

- [X] T014 [US1] Update ImplementerAgent to use IMPLEMENTER_TOOLS in src/maverick/agents/implementer.py
- [X] T015 [P] [US1] Update CodeReviewerAgent to use REVIEWER_TOOLS in src/maverick/agents/code_reviewer.py
- [X] T016 [P] [US1] Update IssueFixerAgent to use ISSUE_FIXER_TOOLS in src/maverick/agents/issue_fixer.py
- [X] T017 [P] [US1] Update GeneratorAgent to use GENERATOR_TOOLS in src/maverick/agents/generators/base.py

**Checkpoint**: All existing agents use centralized tool constants with Bash removed

---

## Phase 4: User Story 2 - Centralized Tool Set Management (Priority: P2)

**Goal**: Ensure all agents reference shared tool definitions for consistency and auditability

**Independent Test**: Verify tool set constants exist and all agents use these shared definitions

### Tests for User Story 2

- [X] T018 [P] [US2] Write test verifying all tool sets are frozenset in tests/unit/agents/test_tools.py
- [X] T019 [P] [US2] Write test verifying all tool sets are subsets of BUILTIN_TOOLS in tests/unit/agents/test_tools.py
- [X] T020 [P] [US2] Write test verifying tool sets cannot be modified at runtime in tests/unit/agents/test_tools.py

### Implementation for User Story 2

- [X] T021 [US2] Add module docstring and usage examples to src/maverick/agents/tools.py
- [X] T022 [US2] Add __all__ export list to src/maverick/agents/tools.py
- [X] T023 [US2] Verify base.py BUILTIN_TOOLS import pattern in src/maverick/agents/base.py

**Checkpoint**: Tool set management is centralized, documented, and auditable

---

## Phase 5: User Story 3 - Context-Driven Agent Prompts (Priority: P2)

**Goal**: Update agent system prompts to reflect constrained roles

**Independent Test**: Review agent system prompts and verify they contain guidance about pre-gathered context

### Tests for User Story 3

- [X] T024 [P] [US3] Write test verifying ImplementerAgent prompt mentions orchestration in tests/unit/agents/test_implementer.py
- [X] T025 [P] [US3] Write test verifying CodeReviewerAgent prompt mentions pre-gathered context in tests/unit/agents/test_code_reviewer.py
- [X] T026 [P] [US3] Write test verifying system prompts do not mention git/PR/API operations in tests/unit/agents/test_prompts.py

### Implementation for User Story 3

- [X] T027 [US3] Update ImplementerAgent system prompt in src/maverick/agents/implementer.py
- [X] T028 [P] [US3] Update CodeReviewerAgent system prompt in src/maverick/agents/code_reviewer.py
- [X] T029 [P] [US3] Update IssueFixerAgent system prompt in src/maverick/agents/issue_fixer.py
- [X] T030 [P] [US3] Update GeneratorAgent system prompt in src/maverick/agents/generators/base.py

**Checkpoint**: All agent prompts reflect constrained roles and mention orchestration layer

---

## Phase 6: User Story 4 - New FixerAgent for Validation Fixes (Priority: P3)

**Goal**: Create a minimal FixerAgent specialized for applying targeted validation fixes

**Independent Test**: Instantiate FixerAgent and verify it has only Read, Write, and Edit tools

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T031 [P] [US4] Write test for FixerAgent allowed_tools in tests/unit/agents/test_fixer.py
- [X] T032 [P] [US4] Write test for FixerAgent system prompt in tests/unit/agents/test_fixer.py
- [X] T033 [P] [US4] Write test for FixerAgent execute method signature in tests/unit/agents/test_fixer.py

### Implementation for User Story 4

- [X] T034 [US4] Create FixerAgent class in src/maverick/agents/fixer.py
- [X] T035 [US4] Implement FixerAgent system prompt per contract in src/maverick/agents/fixer.py
- [X] T036 [US4] Implement FixerAgent execute method in src/maverick/agents/fixer.py
- [X] T037 [US4] Update src/maverick/agents/__init__.py to export FixerAgent

**Checkpoint**: FixerAgent is complete with minimal tool set for validation fixes

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and cleanup

- [X] T038 [P] Run full test suite to verify all agent tool configurations
- [X] T039 [P] Run ruff and mypy to verify type annotations
- [X] T040 Verify no regressions in existing workflow tests (tests/unit/workflows/test_fly.py, tests/unit/workflows/test_refuel.py)
- [X] T041 Run quickstart.md validation scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (Constrained Agent Execution): Core change, recommended first
  - US2 (Centralized Tool Set): Can parallel with US1
  - US3 (Context-Driven Prompts): Can parallel with US1/US2
  - US4 (FixerAgent): Can parallel with US1-US3, new agent creation
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Foundational - MVP scope
- **User Story 2 (P2)**: Depends on Foundational - enhances US1
- **User Story 3 (P2)**: Depends on Foundational - can integrate with US1
- **User Story 4 (P3)**: Depends on Foundational - independent new agent

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Agent class updates after tool constants are verified
- System prompt updates can parallel tool updates
- Verify tests pass after implementation

### Parallel Opportunities

**After Foundational Phase completes, all 4 user stories can begin in parallel:**

```bash
# All test creation tasks can run in parallel:
Task: T010, T011, T012, T013, T018, T019, T020, T024, T025, T026, T031, T032, T033

# All agent implementation updates can run in parallel:
Task: T015, T016, T017, T028, T029, T030

# FixerAgent creation is independent:
Task: T034, T035, T036, T037
```

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Write test for ImplementerAgent allowed_tools in tests/unit/agents/test_implementer.py"
Task: "Write test for CodeReviewerAgent allowed_tools in tests/unit/agents/test_code_reviewer.py"
Task: "Write test for IssueFixerAgent allowed_tools in tests/unit/agents/test_issue_fixer.py"
Task: "Write test for GeneratorAgent allowed_tools in tests/unit/agents/test_generators.py"

# After tests exist, launch agent updates in parallel (different files):
Task: "Update CodeReviewerAgent to use REVIEWER_TOOLS in src/maverick/agents/code_reviewer.py"
Task: "Update IssueFixerAgent to use ISSUE_FIXER_TOOLS in src/maverick/agents/issue_fixer.py"
Task: "Update GeneratorAgent to use GENERATOR_TOOLS in src/maverick/agents/generators/base.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T009)
3. Complete Phase 3: User Story 1 (T010-T017)
4. **STOP and VALIDATE**: Run tests, verify agents have correct tools
5. Deploy if ready - agents are now constrained

### Incremental Delivery

1. Complete Setup + Foundational → Tool constants ready
2. Add User Story 1 → Agents constrained → **MVP Complete!**
3. Add User Story 2 → Tool management documented
4. Add User Story 3 → Prompts updated → Agent guidance complete
5. Add User Story 4 → FixerAgent available → Full feature complete

### Parallel Team Strategy

With multiple developers:

1. Complete Setup + Foundational together (blocking)
2. Once Foundational is done:
   - Developer A: User Story 1 (agent tool updates)
   - Developer B: User Story 2 (tool set management) + User Story 3 (prompts)
   - Developer C: User Story 4 (FixerAgent creation)
3. All stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All tool sets must be frozenset[str] for immutability
- Bash is removed from ALL agents - orchestration layer handles commands
