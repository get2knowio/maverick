"""Shared fixtures for speckit parser/detect/build tests."""

from __future__ import annotations

from pathlib import Path

import pytest

#: Full-featured tasks.md: multi-phase, [P]/[USn] markers, checked tasks,
#: an explicit "depends on" note, a fenced code block containing a
#: task-shaped line (must be skipped), and a Dependencies section.
FULL_TASKS_MD = """\
# Tasks: Sample Feature

## Phase 1: Setup

- [ ] T001 Initialize project
- [x] T002 [P] Already completed setup task
- [ ] T003 [P] Create config file in src/config.py

## Phase 2: Foundational

- [ ] T004 Create core model in src/models.py (depends on T003)
- [ ] T005 Implement base service in src/service.py

```
# fenced code block containing a task-shaped line that must be skipped
- [ ] T999 this looks like a task but is inside a fence
```

## Phase 3: User Story 1 - Core Feature (Priority: P1)

- [ ] T006 [P] [US1] Implement feature A in src/feature_a.py
- [ ] T007 [US1] Add tests for feature A in tests/test_feature_a.py

## Phase 4: User Story 2 - Extended Feature (Priority: P2)

- [ ] T008 [US2] Implement feature B in src/feature_b.py
- [x] T009 [US2] Already completed extended task

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T010 [P] Run linting
- [ ] T011 [P] Fix type errors

## Dependencies & Execution Order

- US2: Depends on US1
"""

#: spec.md matching FULL_TASKS_MD: SC bullets and per-story Acceptance
#: Scenarios for US1/US2.
FULL_SPEC_MD = """\
# Feature Specification: Sample Feature

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Core Feature (Priority: P1)

Some narrative text describing story 1.

**Acceptance Scenarios**:

1. **Given** a thing, **When** an action, **Then** an outcome for story 1.
2. **Given** another thing, **When** another action, **Then** another outcome.

### User Story 2 - Extended Feature (Priority: P2)

More narrative text describing story 2.

**Acceptance Scenarios**:

1. **Given** something extended, **When** acting, **Then** an extended outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The feature does the thing within a time bound.
- **SC-002**: Every task carries through unmodified.
"""


@pytest.fixture
def full_tasks_md() -> str:
    return FULL_TASKS_MD


@pytest.fixture
def full_spec_md() -> str:
    return FULL_SPEC_MD


@pytest.fixture
def speckit_feature_dir(temp_dir: Path) -> Path:
    """Full-featured Spec Kit feature directory under a temp repo root.

    Layout: ``<temp_dir>/specs/048-sample-feature/{spec.md,tasks.md,plan.md}``.
    """
    feature_dir = temp_dir / "specs" / "048-sample-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "tasks.md").write_text(FULL_TASKS_MD, encoding="utf-8")
    (feature_dir / "spec.md").write_text(FULL_SPEC_MD, encoding="utf-8")
    (feature_dir / "plan.md").write_text("# Plan\n\nImplementation plan.", encoding="utf-8")
    return feature_dir
