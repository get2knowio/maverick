# Tasks: Generator Agents

**Input**: Design documents from `/specs/019-generator-agents/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/generator_api.py

**Tests**: Constitution specifies TDD (Test-First principle), so tests are included.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `src/maverick/agents/generators/`
- **Tests**: `tests/unit/agents/generators/`
- **Exceptions**: `src/maverick/exceptions.py` (existing)

---

## Phase 1: Setup

**Purpose**: Create directory structure and add GeneratorError exception

- [X] T001 Create generators package directory at `src/maverick/agents/generators/`
- [X] T002 Create generators test directory at `tests/unit/agents/generators/`
- [X] T003 Add GeneratorError exception class to `src/maverick/exceptions.py`

---

## Phase 2: Foundational (GeneratorAgent Base Class)

**Purpose**: Implement the abstract base class that all generators inherit from. MUST complete before any user story.

**CRITICAL**: No user story work can begin until this phase is complete.

### Tests for Foundational

- [X] T004 [P] Write base class unit tests in `tests/unit/agents/generators/test_base.py`

### Implementation for Foundational

- [X] T005 Implement GeneratorAgent base class in `src/maverick/agents/generators/base.py` with:
  - Constructor accepting name, system_prompt, model (per FR-001)
  - Properties for name, system_prompt, model
  - Abstract `generate(context: dict) -> str` method (per FR-013)
  - `_query(prompt: str) -> str` helper using SDK `query()` with max_turns=1, allowed_tools=[] (per FR-002, FR-003, FR-014)
  - `_truncate_input(content: str, max_size: int, field_name: str) -> str` helper (per FR-017)
  - Constants: MAX_DIFF_SIZE=102400, MAX_SNIPPET_SIZE=10240, DEFAULT_MODEL
  - DEBUG logging for inputs/outputs, WARNING for truncation (per FR-016)
  - Error handling wrapping SDK exceptions in GeneratorError (per FR-018)
- [X] T006 Create package `__init__.py` at `src/maverick/agents/generators/__init__.py` exporting base class

**Checkpoint**: GeneratorAgent base class ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Automated Commit Message Generation (Priority: P1)

**Goal**: Generate conventional commit messages from git diffs

**Independent Test**: Provide sample git diff and file stats, verify output follows `type(scope): description` format

### Tests for User Story 1

- [X] T007 [P] [US1] Write CommitMessageGenerator tests in `tests/unit/agents/generators/test_commit_message.py`:
  - Test generate returns conventional commit format
  - Test scope_hint override works
  - Test bug fix diff produces "fix" type
  - Test empty diff raises GeneratorError (per FR-015)
  - Test diff truncation at 100KB with WARNING (per FR-017)

### Implementation for User Story 1

- [X] T008 [US1] Implement CommitMessageGenerator in `src/maverick/agents/generators/commit_message.py`:
  - Inherit from GeneratorAgent
  - System prompt enforcing conventional commit format (per FR-004, FR-006)
  - Accept diff, file_stats, optional scope_hint (per FR-005)
  - Validate non-empty diff (per FR-015)
  - Truncate diff to MAX_DIFF_SIZE if exceeded (per FR-017)
  - Build prompt from context and call _query()
- [X] T009 [US1] Export CommitMessageGenerator in `src/maverick/agents/generators/__init__.py`

**Checkpoint**: User Story 1 complete - can generate commit messages independently

---

## Phase 4: User Story 2 - Pull Request Description Generation (Priority: P1)

**Goal**: Generate markdown PR descriptions with Summary, Changes, Testing sections

**Independent Test**: Provide commits, diff_stats, task_summary, validation_results and verify markdown output contains all sections

### Tests for User Story 2

- [X] T010 [P] [US2] Write PRDescriptionGenerator tests in `tests/unit/agents/generators/test_pr_description.py`:
  - Test generate returns markdown with Summary, Changes, Testing sections
  - Test failing validation results reflected in Testing section
  - Test task_summary incorporated in Summary section
  - Test custom sections list works
  - Test empty commits raises GeneratorError (per FR-015)

### Implementation for User Story 2

- [X] T011 [US2] Implement PRDescriptionGenerator in `src/maverick/agents/generators/pr_description.py`:
  - Inherit from GeneratorAgent
  - System prompt enforcing markdown section format (per FR-004, FR-008)
  - Accept commits, diff_stats, task_summary, validation_results, optional sections (per FR-007)
  - Default sections: Summary, Changes, Testing (per FR-008)
  - Validate non-empty commits and task_summary (per FR-015)
  - Build prompt with all context and call _query()
- [X] T012 [US2] Export PRDescriptionGenerator in `src/maverick/agents/generators/__init__.py`

**Checkpoint**: User Story 2 complete - can generate PR descriptions independently

---

## Phase 5: User Story 3 - Quick Code Analysis (Priority: P2)

**Goal**: Generate code explanations, reviews, or summaries based on analysis type

**Independent Test**: Provide code snippet and analysis_type, verify output matches requested type

### Tests for User Story 3

- [X] T013 [P] [US3] Write CodeAnalyzer tests in `tests/unit/agents/generators/test_code_analyzer.py`:
  - Test analysis_type="explain" returns explanation
  - Test analysis_type="review" returns issues/improvements
  - Test analysis_type="summarize" returns summary
  - Test invalid analysis_type defaults to "explain" (per FR-009)
  - Test empty code raises GeneratorError (per FR-015)
  - Test code truncation at 10KB with WARNING (per FR-017)

### Implementation for User Story 3

- [X] T014 [US3] Implement CodeAnalyzer in `src/maverick/agents/generators/code_analyzer.py`:
  - Inherit from GeneratorAgent
  - System prompts per analysis type: explain, review, summarize (per FR-004, FR-009, FR-010)
  - Accept code, analysis_type, optional language (per FR-009)
  - Default invalid analysis_type to "explain"
  - Validate non-empty code (per FR-015)
  - Truncate code to MAX_SNIPPET_SIZE if exceeded (per FR-017)
  - Build prompt and call _query()
- [X] T015 [US3] Export CodeAnalyzer in `src/maverick/agents/generators/__init__.py`

**Checkpoint**: User Story 3 complete - can analyze code independently

---

## Phase 6: User Story 4 - Error Explanation (Priority: P2)

**Goal**: Generate plain-English error explanations with fix suggestions

**Independent Test**: Provide error output and optional source context, verify explanation is clear with fix suggestions

### Tests for User Story 4

- [X] T016 [P] [US4] Write ErrorExplainer tests in `tests/unit/agents/generators/test_error_explainer.py`:
  - Test type error explanation with source context
  - Test test failure explanation
  - Test lint error explanation
  - Test error without source context still produces explanation
  - Test empty error_output raises GeneratorError (per FR-015)
  - Test source_context truncation at 10KB with WARNING (per FR-017)

### Implementation for User Story 4

- [X] T017 [US4] Implement ErrorExplainer in `src/maverick/agents/generators/error_explainer.py`:
  - Inherit from GeneratorAgent
  - System prompt enforcing explanation structure: what/why/how (per FR-004, FR-012)
  - Accept error_output, optional source_context, optional error_type (per FR-011)
  - Validate non-empty error_output (per FR-015)
  - Truncate source_context to MAX_SNIPPET_SIZE if exceeded (per FR-017)
  - Build prompt with available context and call _query()
- [X] T018 [US4] Export ErrorExplainer in `src/maverick/agents/generators/__init__.py`

**Checkpoint**: User Story 4 complete - can explain errors independently

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, type checking, and package exports

- [X] T019 [P] Run mypy type checking on `src/maverick/agents/generators/`
- [X] T020 [P] Run ruff linting on `src/maverick/agents/generators/`
- [X] T021 Run all generator tests with pytest to verify full coverage
- [X] T022 Verify quickstart.md examples work correctly
- [X] T023 Update `src/maverick/agents/__init__.py` to export generators subpackage

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001-T003) - BLOCKS all user stories
- **User Stories (Phases 3-6)**: All depend on Foundational phase completion
  - US1 and US2 can run in parallel (both P1 priority)
  - US3 and US4 can run in parallel (both P2 priority)
  - Or all four can run sequentially: US1 → US2 → US3 → US4
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 3 (P2)**: Can start after Foundational - No dependencies on other stories
- **User Story 4 (P2)**: Can start after Foundational - No dependencies on other stories

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Implementation depends on base class (T005)
- Export update depends on implementation

### Parallel Opportunities

| Phase | Parallel Tasks |
|-------|---------------|
| Phase 1 | T001, T002 can run in parallel |
| Phase 2 | T004 (tests) can start immediately |
| Phase 3 | T007 (tests) after T004-T006 complete |
| Phase 4 | T010 (tests) can run parallel with Phase 3 |
| Phase 5 | T013 (tests) can run parallel with Phase 3-4 |
| Phase 6 | T016 (tests) can run parallel with Phase 3-5 |
| Phase 7 | T019, T020 can run in parallel |

---

## Parallel Example: User Stories 1 & 2 (P1 Priority)

```bash
# After Foundational phase completes, launch P1 stories in parallel:

# Team Member A - User Story 1:
Task: "Write CommitMessageGenerator tests in tests/unit/agents/generators/test_commit_message.py"
Task: "Implement CommitMessageGenerator in src/maverick/agents/generators/commit_message.py"

# Team Member B - User Story 2 (parallel):
Task: "Write PRDescriptionGenerator tests in tests/unit/agents/generators/test_pr_description.py"
Task: "Implement PRDescriptionGenerator in src/maverick/agents/generators/pr_description.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T006)
3. Complete Phase 3: User Story 1 (T007-T009)
4. **STOP and VALIDATE**: Test CommitMessageGenerator works
5. Can be used immediately for commit message generation

### Incremental Delivery

1. Setup + Foundational → Base class ready
2. Add User Story 1 → Commit messages (MVP!)
3. Add User Story 2 → PR descriptions
4. Add User Story 3 → Code analysis
5. Add User Story 4 → Error explanations
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With 2 developers after Foundational:

1. Both complete Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 → User Story 3
   - Developer B: User Story 2 → User Story 4
3. All stories complete and integrate independently

---

## Notes

- All generators use `query()` with `max_turns=1` and no tools
- Input validation: empty inputs raise GeneratorError
- Input truncation: oversized inputs logged at WARNING and truncated
- Error handling: SDK exceptions wrapped in GeneratorError, raised immediately
- Logging: DEBUG for inputs/outputs, WARNING/ERROR for issues
- All methods are async per FR-013
- Type hints required on all public interfaces per constitution
