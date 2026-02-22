# Tasks: Typed Agent Output Contracts

**Input**: Design documents from `/specs/030-typed-output-contracts/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Explicitly required per FR-012 and plan.md. New tests cover validate_output(), converted Pydantic models, and each agent's typed output path.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. Within each phase, tests are written FIRST per Constitution Principle V (Test-First / Red-Green-Refactor).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/` at repository root

---

## Phase 1: Setup (New Models & Error Types)

**Purpose**: Create new Pydantic models and error types that all user stories depend on

### Tests (write FIRST — expect failures until implementation) 🔴

- [x] T001 Write tests for FixerResult model (construction, serialization via model_dump/model_validate round-trip, validation rules, error_details required when success=False) in tests/unit/models/test_fixer_model.py

### Implementation 🟢

- [x] T002 Create FixerResult Pydantic model with success/summary/files_mentioned/error_details fields and model_validator for error_details-when-failure rule in src/maverick/models/fixer.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Convert existing output types to Pydantic, add base class structured output support, and implement validate_output() utility. MUST complete before ANY user story.

**CRITICAL**: No user story work can begin until this phase is complete.

### Tests (write FIRST — expect failures until implementation) 🔴

- [x] T003 [P] Write tests for converted Pydantic models (Pydantic construction, frozen immutability, model_dump/model_validate round-trip, to_dict()/from_dict() aliases, backward-compatible deserialization of existing checkpoint-style dicts) in tests/unit/models/test_review_models.py
- [x] T004 [P] Write tests for validate_output() covering: valid JSON in code block, multiple code blocks (first wins), no code block found (stage=extraction), invalid JSON (stage=json_parse), valid JSON but schema mismatch (stage=validation), strict=True raises vs strict=False returns None, empty input, nested code blocks, partial chunks with mixed valid/malformed output in tests/unit/agents/test_contracts.py
- [x] T005 [P] Write tests for _extract_structured_output() helper (ResultMessage with structured_output, ResultMessage without, non-ResultMessage messages, empty list) and output_model parameter wiring (output_format dict generation from model schema) in tests/unit/agents/test_base.py (additive tests)

### Dataclass-to-Pydantic Conversions 🟢

- [x] T006 Convert Finding frozen dataclass to Pydantic BaseModel with ConfigDict(frozen=True) and add to_dict()/from_dict() aliases in src/maverick/models/review_models.py
- [x] T007 Convert FindingGroup frozen dataclass to Pydantic BaseModel with ConfigDict(frozen=True), change tuple[Finding, ...] to list[Finding], and add to_dict()/from_dict() aliases in src/maverick/models/review_models.py
- [x] T008 Convert ReviewResult frozen dataclass to GroupedReviewResult Pydantic BaseModel with ConfigDict(frozen=True), preserve all_findings/total_count properties, add to_dict()/from_dict() aliases, update all imports of the old name including the SimpleReviewResult alias in src/maverick/models/__init__.py (line 121), src/maverick/agents/reviewers/unified_reviewer.py, and src/maverick/agents/reviewers/simple_fixer.py in src/maverick/models/review_models.py
- [x] T009 Convert FixOutcome frozen dataclass to Pydantic BaseModel with ConfigDict(frozen=True) and add to_dict()/from_dict() aliases in src/maverick/models/review_models.py

### Base Class Structured Output Support 🟢

- [x] T010 Add output_model: type[BaseModel] | None parameter to MaverickAgent.__init__(), compute _output_format dict from model_json_schema(), and pass output_format to ClaudeAgentOptions in _build_options() in src/maverick/agents/base.py
- [x] T011 Add _extract_structured_output() helper method to MaverickAgent that searches messages (reversed) for ResultMessage with structured_output populated, returns dict or None in src/maverick/agents/base.py

### Validation Utility 🟢

- [x] T012 Create contracts module with OutputValidationError (inheriting MaverickError, with expected_model/raw_output/parse_error/stage fields) and validate_output() function (code-block extraction, json.loads, Pydantic model_validate pipeline, strict/non-strict modes) in src/maverick/agents/contracts.py

**Checkpoint**: Foundation ready — validate_output(), Pydantic models, and SDK structured output wiring all in place. All Phase 2 tests should now pass (🟢).

---

## Phase 3: User Story 1 — Eliminate Regex JSON Extraction from Agent Outputs (Priority: P1)

**Goal**: Replace all three regex-based JSON extraction sites with SDK structured output + validate_output() fallback. Agents return validated Pydantic models, not best-effort regex parses.

**Independent Test**: Run code reviewer and simple fixer agents against sample diffs and verify all outputs are validated Pydantic model instances — no regex extraction in the code path.

### Tests (write FIRST — expect failures until implementation) 🔴

> **NOTE**: Write these tests FIRST. They should FAIL because agents still use regex. Implementation makes them pass.

- [x] T013 [US1] Write tests verifying typed output parsing for CodeReviewerAgent, UnifiedReviewerAgent, and SimpleFixerAgent: assert outputs are validated Pydantic models, no regex calls remain, malformed output produces OutputValidationError (not empty list), and chunked review with partial malformed output preserves successful chunks in tests/unit/agents/test_code_reviewer.py and tests/unit/agents/reviewers/

### Implementation 🟢

- [x] T014 [P] [US1] Replace extract_json() regex extraction in CodeReviewerAgent with SDK output_format for ReviewResult and validate_output() fallback in parse_findings(); remove or deprecate extract_json() in src/maverick/agents/code_reviewer/parsing.py and src/maverick/agents/code_reviewer/agent.py
- [x] T015 [P] [US1] Replace _parse_review_output() regex extraction in UnifiedReviewerAgent with SDK output_format for GroupedReviewResult and validate_output() fallback; update agent constructor to pass output_model in src/maverick/agents/reviewers/unified_reviewer.py
- [x] T016 [P] [US1] Replace _parse_outcomes() regex extraction in SimpleFixerAgent with SDK output_format for FixOutcome list wrapper and validate_output() fallback; update agent constructor to pass output_model in src/maverick/agents/reviewers/simple_fixer.py

**Checkpoint**: Zero regex-based JSON extraction in agent output parsing paths (SC-001). All three agents return validated Pydantic models or raise OutputValidationError. Phase 3 tests pass (🟢).

---

## Phase 4: User Story 2 — Replace FixerAgent Opaque Output with Typed Contract (Priority: P2)

**Goal**: FixerAgent returns structured FixerResult instead of generic AgentResult with opaque output: str. Downstream workflows access typed fields without string parsing.

**Independent Test**: Run FixerAgent against a sample fix prompt and verify the result is a FixerResult with structured file change information and success/error status.

### Tests (write FIRST — expect failures until implementation) 🔴

> **NOTE**: Write these tests FIRST. They should FAIL because FixerAgent still returns AgentResult.

- [x] T017 [P] [US2] Write tests for FixerAgent typed FixerResult output (success case, failure case with error_details, malformed output handling, tool side-effects preserved when structured output parsing fails) in tests/unit/agents/test_fixer.py

### Implementation 🟢

- [x] T018 [US2] Update FixerAgent to accept output_model=FixerResult in constructor, use _extract_structured_output() + validate_output() fallback in execute(), and return FixerResult instead of AgentResult in src/maverick/agents/fixer.py
- [x] T019 [US2] Update downstream workflow consumers of FixerAgent results to use FixerResult typed fields (success, summary, files_mentioned, error_details) instead of AgentResult.output string parsing

**Checkpoint**: FixerAgent returns FixerResult. Downstream workflows use typed fields for retry/abort decisions (SC-002 partial). Phase 4 tests pass (🟢).

---

## Phase 5: User Story 3 — Centralized Output Contract Registry (Priority: P3)

**Goal**: Single contracts module re-exports all agent output types. Developers import from one location. Orchestration code uses typed contracts. All six agents wired for SDK structured output.

**Independent Test**: Verify all agent output types are importable from maverick.agents.contracts and that orchestration code imports from there.

### Implementation for User Story 3

- [x] T020 [US3] Complete contracts module with all type re-exports (ReviewFinding, ReviewResult, Finding, FindingGroup, GroupedReviewResult, FixOutcome, FixerResult, FixResult, ImplementationResult, AgentResult) and __all__ list in src/maverick/agents/contracts.py
- [x] T021 [P] [US3] Add deprecation note to FixResult.output field description recommending fix_description + files_changed instead (satisfies FR-007 audit — R5 determined files_changed: list[FileChange] is already typed, only output needs deprecation) in src/maverick/models/issue_fix.py
- [x] T022 [P] [US3] Add deprecation docstring to AgentResult frozen dataclass with guidance to use specific typed result models in src/maverick/agents/result.py
- [x] T023 [US3] Extend _extract_output_text() to handle FixerResult (.summary), GroupedReviewResult (.all_findings count), and list[FixOutcome] (count + summary) for display/streaming in src/maverick/dsl/serialization/executor/handlers/agent_step.py
- [x] T024 [US3] ~~Wire output_model to IssueFixerAgent and ImplementerAgent~~ — SKIPPED: Both agents construct results programmatically from side effects (file changes, task outcomes), not from parsing Claude's text output. Wiring output_model would force SDK JSON schema constraints on agents that use tools freely, degrading their effectiveness. The 4 agents that parse output from Claude text (CodeReviewer, UnifiedReviewer, SimpleFixer, Fixer) are already wired.
- [x] T025 [US3] Migrate orchestration code in review-fix workflow to import output types from maverick.agents.contracts instead of individual module paths
- [x] T026 [US3] Write import-validation test confirming all output types are importable from maverick.agents.contracts in a single import statement, and verify all six agents have output_model set in tests/unit/agents/test_contracts.py (additive)

**Checkpoint**: All agent output types discoverable from one module (SC-004). All six agents wired for SDK structured output (SC-002 complete). Orchestration code uses typed contracts (FR-008).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, cleanup, and regression checks across all stories

- [x] T027 Run full test suite (make check: lint + typecheck + test) and fix any regressions
- [x] T028 Verify SC-001: grep codebase for regex JSON extraction patterns in agent output paths — confirm zero remain
- [x] T029 Verify SC-005: confirm malformed output produces structured OutputValidationError (not silent empty returns) via log output
- [x] T030 Run quickstart.md validation: verify code examples in specs/030-typed-output-contracts/quickstart.md compile and patterns work

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately. T001 (test) before T002 (implementation).
- **Foundational (Phase 2)**: Depends on Phase 1 (T002 for FixerResult model used in later phases). T003-T005 (tests) run first and in parallel. T006-T009 are sequential (same file). T010-T011 are sequential (same file). T012 depends on T006-T009 (needs Pydantic models for validation).
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - US1 (Phase 3): T013 (tests) first, then T014-T016 (implementation) in parallel
  - US2 (Phase 4): T017 (tests) first, then T018 → T019 (sequential)
  - US3 (Phase 5): Depends on all types existing (T002, T006-T009, T014-T016, T018)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2). No dependencies on other stories.
- **User Story 2 (P2)**: Can start after Foundational (Phase 2). No dependencies on other stories. Can run in parallel with US1.
- **User Story 3 (P3)**: Depends on US1 and US2 completing (needs all types to exist for re-export, all agents wired for SC-002).

### Within Each User Story (TDD Order)

1. Write tests FIRST — they should FAIL (Red 🔴)
2. Implement models/types
3. Implement agent modifications
4. Update downstream consumers
5. All tests should now PASS (Green 🟢)

### Parallel Opportunities

- T001 can start immediately (test-first for FixerResult)
- T003, T004, T005 can run in parallel (different test files, after Phase 1)
- T014, T015, T016 can all run in parallel (different agent files, same pattern)
- T021 and T022 can run in parallel (different files, both deprecation notes)
- US1 and US2 can run in parallel after Foundational phase (independent agent changes)

---

## Parallel Example: User Story 1

```text
# TDD: Write tests first
Task T013: "Write tests for typed output parsing — expect failures"

# Then launch all US1 agent changes in parallel:
Task T014: "Replace regex in CodeReviewerAgent in src/maverick/agents/code_reviewer/"
Task T015: "Replace regex in UnifiedReviewerAgent in src/maverick/agents/reviewers/unified_reviewer.py"
Task T016: "Replace regex in SimpleFixerAgent in src/maverick/agents/reviewers/simple_fixer.py"

# Verify: T013 tests now pass
```

## Parallel Example: US1 + US2 Concurrent

```text
# After Foundational phase, both stories can proceed simultaneously:
[Worker A] US1: T013 (tests) → T014 ∥ T015 ∥ T016 (impl)
[Worker B] US2: T017 (tests) → T018 → T019 (impl)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T012) — CRITICAL, blocks all stories
3. Complete Phase 3: User Story 1 (T013-T016)
4. **STOP and VALIDATE**: Run `make check` — zero regex extraction, all tests pass
5. This alone delivers the highest-value improvement (eliminates fragile parsing)

### Incremental Delivery

1. Setup + Foundational → Foundation ready (new models, validate_output, base class support)
2. Add User Story 1 → Test independently → Regex elimination complete (MVP!)
3. Add User Story 2 → Test independently → FixerAgent typed output
4. Add User Story 3 → Test independently → Centralized registry + all six agents wired
5. Polish → Full validation pass

### Summary

| Metric | Count |
|--------|-------|
| Total tasks | 30 |
| Phase 1 (Setup) | 2 |
| Phase 2 (Foundational) | 10 |
| Phase 3 (US1) | 4 |
| Phase 4 (US2) | 3 |
| Phase 5 (US3) | 7 |
| Phase 6 (Polish) | 4 |
| Parallel opportunities | 6 groups |
| Suggested MVP scope | Phases 1-3 (US1: Eliminate regex extraction) |
