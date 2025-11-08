---

description: "Task list for implementing Temporal phase automation workflow"
---

# Tasks: Temporal Phase Automation for tasks.md

**Input**: Design documents from `/workspaces/maverick/specs/001-automate-phase-tasks/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Follow project constitution — add failing tests before implementing features.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions (absolute paths per instructions)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create shared fixtures and test helpers required by all user stories

- [X] T001 Create baseline tasks.md fixture for phase automation in `/workspaces/maverick/tests/fixtures/phase_automation/sample_tasks.md`
- [X] T002 Add malformed tasks.md fixture covering missing phase headings in `/workspaces/maverick/tests/fixtures/phase_automation/invalid_missing_phase.md`
- [X] T003 Extend Temporal testing fixtures for phase automation helpers in `/workspaces/maverick/tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define shared data models and markdown utilities required before orchestrating any user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create failing unit tests for phase automation dataclasses invariants in `/workspaces/maverick/tests/unit/test_phase_automation_models.py`
- [X] T005 Implement `PhaseDefinition`, `TaskItem`, `PhaseExecutionHints`, `PhaseExecutionContext`, `PhaseResult`, `WorkflowCheckpoint`, and `ResumeState` dataclasses in `/workspaces/maverick/src/models/phase_automation.py`
- [X] T006 Export new phase automation models from `/workspaces/maverick/src/models/__init__.py`
- [X] T007 Add failing unit tests for markdown parsing, override metadata extraction, and hashing helpers in `/workspaces/maverick/tests/unit/test_tasks_markdown_utils.py`
- [X] T008 Implement deterministic markdown parsing, override metadata extraction, and hashing utilities for phase automation in `/workspaces/maverick/src/utils/tasks_markdown.py`

---

## Phase 3: User Story 1 - Orchestrate sequential phase runs (Priority: P1) 🎯 MVP

**Goal**: Workflow operator triggers automation so phases execute sequentially with AI-backed activities

**Independent Test**: Start workflow with sample `tasks.md`, verify phases run in order and each completion reports success

### Tests for User Story 1

- [X] T009 [US1] Add failing unit tests for `parse_tasks_md` activity edge cases, including override metadata detection, in `/workspaces/maverick/tests/unit/test_phase_tasks_parser.py`
- [X] T010 [US1] Add integration test covering sequential phase execution, override propagation, and tolerant CLI decoding fallbacks in `/workspaces/maverick/tests/integration/test_phase_automation_workflow.py`

### Implementation for User Story 1

- [X] T011 [P] [US1] Implement Temporal activity `parse_tasks_md` using markdown utilities in `/workspaces/maverick/src/activities/phase_tasks_parser.py`
- [X] T012 [P] [US1] Implement Temporal activity `run_phase` to invoke `speckit.implement`, apply timeout/backoff overrides, and capture results with tolerant decoding in `/workspaces/maverick/src/activities/phase_runner.py`
- [X] T013 [US1] Implement `AutomatePhaseTasksWorkflow` orchestrating sequential phase execution and passing phase-level overrides to activities in `/workspaces/maverick/src/workflows/phase_automation.py`
- [X] T014 [US1] Extend CLI dispatcher to launch automate-phase-tasks workflow in `/workspaces/maverick/src/cli/readiness.py`
- [X] T015 [US1] Register new workflow and activities with the Temporal worker and exports in `/workspaces/maverick/src/workers/main.py` and `/workspaces/maverick/src/activities/__init__.py`

**Checkpoint**: Automate Phase Tasks workflow runs sequential phases end-to-end via CLI

---

## Phase 4: User Story 2 - Resume after a failed phase (Priority: P2)

**Goal**: Automation engineer resumes workflow after failure, skipping completed phases and restarting at first incomplete phase

**Independent Test**: Simulate failure in Phase 2, rerun workflow, confirm completed phases skipped and checkpoints refreshed

### Tests for User Story 2

- [X] T016 [US2] Add failing unit tests for resume planning and checkpoint drift handling in `/workspaces/maverick/tests/unit/test_phase_resume.py`
- [X] T017 [US2] Extend integration test suite with resume scenario coverage in `/workspaces/maverick/tests/integration/test_phase_automation_workflow.py`

### Implementation for User Story 2

- [X] T018 [US2] Persist and reload workflow checkpoints with resume branching in `/workspaces/maverick/src/workflows/phase_automation.py`
- [X] T019 [P] [US2] Enhance `run_phase` activity to respect checkpoints, skip completed tasks, and return updated hashes while preserving override and timeout behaviour in `/workspaces/maverick/src/activities/phase_runner.py`
- [X] T020 [US2] Extend markdown utilities with checkpoint hash comparison helpers in `/workspaces/maverick/src/utils/tasks_markdown.py`
- [X] T021 [US2] Support resume-friendly workflow options (workflow ID, overrides, timeout/backoff tuning) in `/workspaces/maverick/src/cli/readiness.py`

**Checkpoint**: Workflow resumes from checkpoints and respects document drift rules

---

## Phase 5: User Story 3 - Review AI execution outcomes (Priority: P3)

**Goal**: Delivery lead retrieves structured per-phase execution logs without reading raw CLI output

**Independent Test**: Run a phase, confirm JSON result stored with status, timestamps, sanitized log paths, and accessible via workflow query or CLI command

### Tests for User Story 3

- [X] T022 [US3] Add failing unit tests for phase result persistence, serialization, and sanitized log references in `/workspaces/maverick/tests/unit/test_phase_results_store.py`
- [X] T023 [US3] Add integration tests for retrieving phase automation results via workflow query or CLI in `/workspaces/maverick/tests/integration/test_phase_automation_workflow.py`

### Implementation for User Story 3

- [X] T024 [P] [US3] Implement phase result persistence helper writing JSON under `/workspaces/maverick/src/utils/phase_results_store.py`
- [X] T025 [US3] Extend workflow to persist per-phase results and aggregate summary output in `/workspaces/maverick/src/workflows/phase_automation.py`
- [X] T026 [P] [US3] Implement Temporal query and CLI command to retrieve phase automation results in `/workspaces/maverick/src/workflows/phase_automation.py` and `/workspaces/maverick/src/cli/readiness.py`
- [X] T027 [US3] Wire CLI command dependencies and update worker exports without introducing FastAPI in `/workspaces/maverick/pyproject.toml`, `/workspaces/maverick/uv.lock`, and `/workspaces/maverick/src/workers/main.py`

**Checkpoint**: Stakeholders can query structured phase results via API and workflow summary output

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Finalize documentation, logging, and validation across all user stories

- [X] T028 Harden structured logging for new workflow and activities in `/workspaces/maverick/src/utils/logging.py` and `/workspaces/maverick/src/workflows/phase_automation.py`
- [X] T029 Update automation documentation for run/resume/review flows in `/workspaces/maverick/README.md` and `/workspaces/maverick/specs/001-automate-phase-tasks/quickstart.md`
- [X] T030 Validate full automation workflow via project test suite in `/workspaces/maverick/tests/`

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → Phase 3 (US1) → Phase 4 (US2) → Phase 5 (US3) → Polish
- Phase 3 unlocks MVP delivery for sequential automation
- Phase 4 depends on checkpoints and utilities from Phase 2 & Phase 3
- Phase 5 depends on Phase 3 orchestration and Phase 4 checkpoint data to populate results
- Polish tasks require all user story phases to be feature-complete

## Parallel Opportunities

- Phase 3: T011 and T012 can proceed in parallel after tests T009-T010 exist (distinct activity modules)
- Phase 4: T019 can proceed alongside T018 once resume tests are in place (separate module work)
- Phase 5: T024 and T026 can proceed in parallel after tests T022-T023 are defined (persistence utilities vs CLI/query integration)
- Polish: T028 can run in parallel with T029 after core implementation completes (logging vs docs)

## Implementation Strategy

1. Deliver MVP by completing Phases 1-3, validating sequential automation through integration tests.
2. Layer in resume robustness by completing Phase 4, ensuring checkpoints and drift handling work before tackling results UX.
3. Implement observability and results retrieval tooling in Phase 5 to enable stakeholder review without raw logs.
4. Finish with polish tasks, validating structured logging, documentation, and the full pytest suite prior to release.

```
MVP Scope = Phases 1-3 (User Story 1)
```
