# Tasks: Instructions Preset

**Input**: Design documents from `/specs/031-instructions-preset/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Test tasks are included — this feature's remaining work is primarily verification and test hardening per research.md findings.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

**Key context**: Research (research.md) confirmed the core implementation is already complete (FR-001 through FR-005, FR-007). Remaining work is verification of contracts, closing test gaps (FR-006), adding negative tests, and validating quickstart documentation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new project setup needed — feature modifies existing codebase. This phase verifies prerequisites.

- [x] T001 Verify Claude Agent SDK dependency includes `SystemPromptPreset` and `SettingSource` types in installed package at `.venv/lib/python3.12/site-packages/claude_agent_sdk/types.py`
- [x] T002 Run `make check` to confirm existing test suite passes before any modifications

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational changes needed — the base class implementation is already in place per research.md. This phase is empty.

**Checkpoint**: Foundation already in place — user story verification can begin immediately.

---

## Phase 3: User Story 1 - Agents Inherit Claude Code Capabilities (Priority: P1)

**Goal**: Verify that all interactive agents automatically use the Claude Code preset, and add missing test coverage for edge cases (empty instructions per FR-006).

**Independent Test**: Run `make test` and verify all `test_base.py` tests pass, including the new empty-instructions test.

### Tests for User Story 1

- [x] T003 [US1] Add test for empty instructions string (FR-006) in `tests/unit/agents/test_base.py`: create a `ConcreteTestAgent` with `instructions=""`, call `_build_options()`, and verify `system_prompt` dict has `"append": ""` and agent functions correctly with preset alone
- [x] T004 [US1] Add test verifying `system_prompt` is always a dict (never a raw string) for `MaverickAgent._build_options()` in `tests/unit/agents/test_base.py`: assert `isinstance(call_kwargs["system_prompt"], dict)` and verify all three keys (`type`, `preset`, `append`) are present
- [x] T005 [P] [US1] Add test for instructions containing markdown formatting and special characters in `tests/unit/agents/test_base.py`: create agent with instructions containing `**bold**`, `# headers`, backticks, and newlines, verify `append` field preserves the exact string

### Verification for User Story 1

- [x] T006 [US1] Verify existing test `test_passes_correct_parameters_to_options` at `tests/unit/agents/test_base.py:302` confirms preset structure matches contract in `contracts/agent-construction.md` (type=preset, preset=claude_code, append=instructions)

**Checkpoint**: All interactive agents verified to use Claude Code preset; empty instructions edge case covered.

---

## Phase 4: User Story 2 - Clear Separation of Instructions from System Prompt (Priority: P2)

**Goal**: Verify that the parameter naming (`instructions` for interactive agents, `system_prompt` for generators) is correct and that generators do NOT use the preset pattern.

**Independent Test**: Run tests for both `test_base.py` and `generators/test_base.py` and verify parameter naming and prompt composition are correct.

### Tests for User Story 2

- [x] T007 [US2] Add negative test for `GeneratorAgent._build_options()` in `tests/unit/agents/generators/test_base.py`: verify `system_prompt` is a raw string (not a dict/preset), `max_turns` is 1, and `allowed_tools` is empty — confirming generators do NOT use the preset pattern (FR-005)
- [x] T008 [P] [US2] Add negative test verifying `GeneratorAgent._build_options()` does NOT include `setting_sources` in `tests/unit/agents/generators/test_base.py`: assert `setting_sources` key is absent from the `ClaudeAgentOptions` call kwargs

### Verification for User Story 2

- [x] T009 [US2] Verify all concrete interactive agents pass `instructions` (not `system_prompt`) to `MaverickAgent.__init__()` by inspecting `src/maverick/agents/implementer.py`, `src/maverick/agents/fixer.py`, `src/maverick/agents/issue_fixer.py`, `src/maverick/agents/code_reviewer/agent.py`, `src/maverick/agents/reviewers/unified_reviewer.py`, and `src/maverick/agents/reviewers/simple_fixer.py`

**Checkpoint**: Parameter naming verified; generators confirmed to use direct system_prompt without preset.

---

## Phase 5: User Story 3 - Project and User Configuration Loaded Automatically (Priority: P3)

**Goal**: Verify that `setting_sources: ["project", "user"]` is set for all interactive agents and NOT set for generators.

**Independent Test**: Run `test_base.py` and verify the setting_sources assertion in the existing `test_passes_correct_parameters_to_options` test.

### Tests for User Story 3

- [x] T010 [US3] Add explicit test for `setting_sources` ordering in `tests/unit/agents/test_base.py`: verify `setting_sources` is exactly `["project", "user"]` (order matters — project first, then user) and that it is a list (not a tuple or set)

### Verification for User Story 3

- [x] T011 [US3] Verify existing test at `tests/unit/agents/test_base.py:327` asserts `setting_sources=["project", "user"]` matches the contract in `contracts/agent-construction.md`

**Checkpoint**: Project and user configuration loading verified for all interactive agents.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across all user stories.

- [x] T012 [P] Run `make check` (lint + typecheck + test) to verify all changes pass CI checks
- [x] T013 Validate quickstart examples in `specs/031-instructions-preset/quickstart.md` by verifying the code snippets are consistent with the actual constructor signatures in `src/maverick/agents/base.py` and `src/maverick/agents/generators/base.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Empty — no blocking prerequisites
- **User Story 1 (Phase 3)**: Can start after Phase 1 verification
- **User Story 2 (Phase 4)**: Can start after Phase 1 verification — independent of US1
- **User Story 3 (Phase 5)**: Can start after Phase 1 verification — independent of US1/US2
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Independent — focuses on `tests/unit/agents/test_base.py`
- **User Story 2 (P2)**: Independent — focuses on `tests/unit/agents/generators/test_base.py` and source verification
- **User Story 3 (P3)**: Independent — focuses on `tests/unit/agents/test_base.py` (setting_sources)

### Within Each User Story

- Verification tasks confirm existing implementation before adding new tests
- New tests must pass `make test` before marking complete

### Parallel Opportunities

- T004 and T005 can run in parallel (different test scenarios, same file but independent tests)
- T007 and T008 can run in parallel (different test scenarios in generator test file)
- US1, US2, and US3 can all proceed in parallel (independent test files and verification targets)
- T012 and T013 can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch independent tests in parallel:
Task: "T004 — Verify system_prompt is always a dict in tests/unit/agents/test_base.py"
Task: "T005 — Test instructions with markdown/special chars in tests/unit/agents/test_base.py"

# Then sequential:
Task: "T003 — Test empty instructions (depends on understanding existing test structure)"
Task: "T006 — Verify existing test matches contract"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Verify prerequisites (T001-T002)
2. Phase 2: Skipped (no foundational work needed)
3. Complete Phase 3: User Story 1 tests (T003-T006)
4. **STOP and VALIDATE**: Run `make test` — all tests pass
5. Core preset behavior fully verified

### Incremental Delivery

1. Verify prerequisites → Foundation confirmed
2. Add US1 tests (preset pattern + empty instructions) → Run tests → Verified
3. Add US2 tests (generator negative tests) → Run tests → Verified
4. Add US3 tests (setting_sources) → Run tests → Verified
5. Polish: Full CI check + quickstart validation

---

## Notes

- [P] tasks = different files or independent test scenarios, no dependencies
- [Story] label maps task to specific user story for traceability
- This feature is primarily verification + test hardening (not new implementation)
- All source code changes are in test files only — production code is already correct
- The existing test at `test_base.py:302-334` already covers much of US1 and US3; new tests close specific gaps identified in research.md
