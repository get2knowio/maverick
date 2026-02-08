"""Shared fixtures for bead tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import (
    BeadCategory,
    BeadDefinition,
    BeadType,
    CreatedBead,
)
from maverick.runners.command import CommandRunner
from maverick.runners.models import CommandResult

SAMPLE_TASKS_MD = """\
# Tasks: Test Project

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Initialize project
- [ ] T002 [P] Create package init
- [ ] T003 [P] Create config file

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T004 Create core data model
- [ ] T005 Implement base service

## Phase 3: User Story 1 - Basic Feature (Priority: P1)

- [ ] T006 [US1] Implement feature A
- [ ] T007 [US1] Add tests for feature A

## Phase 4: User Story 2 - Advanced Feature (Priority: P2)

- [ ] T008 [US2] Implement feature B
- [ ] T009 [US2] Add tests for feature B

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T010 [P] Run linting
- [ ] T011 [P] Fix type errors
"""

SAMPLE_TASKS_MD_WITH_DEPS = """\
# Tasks: Test Project with Dependencies

## Phase 1: Setup

- [ ] T001 Initialize project

## Phase 2: User Story 1 - Core (Priority: P1)

- [ ] T002 [US1] Core feature

## Phase 3: User Story 2 - Extended (Priority: P2)

- [ ] T003 [US2] Extended feature

## Phase 4: User Story 3 - Advanced (Priority: P2)

- [ ] T004 [US3] Advanced feature

## Phase 5: Cleanup

- [ ] T005 Final cleanup

## Dependencies

- US2: Depends on US1
- US3: Depends on US1, US2
"""

BD_CREATE_RESPONSE = '{"id": "abc123", "title": "Test Bead"}'


@pytest.fixture
def sample_tasks_md() -> str:
    """Return sample tasks.md content."""
    return SAMPLE_TASKS_MD


@pytest.fixture
def sample_tasks_md_with_deps() -> str:
    """Return sample tasks.md content with dependencies."""
    return SAMPLE_TASKS_MD_WITH_DEPS


@pytest.fixture
def mock_runner() -> AsyncMock:
    """Create a mock CommandRunner that returns success."""
    runner = AsyncMock(spec=CommandRunner)
    runner.run.return_value = CommandResult(
        returncode=0,
        stdout=BD_CREATE_RESPONSE,
        stderr="",
        duration_ms=100,
        timed_out=False,
    )
    return runner


@pytest.fixture
def mock_client(mock_runner: AsyncMock, temp_dir: Path) -> BeadClient:
    """Create a BeadClient with a mocked runner."""
    return BeadClient(cwd=temp_dir, runner=mock_runner)


@pytest.fixture
def sample_epic_definition() -> BeadDefinition:
    """Return a sample epic bead definition."""
    return BeadDefinition(
        title="test-project",
        bead_type=BeadType.EPIC,
        priority=1,
        category=BeadCategory.FOUNDATION,
        description="Test epic",
    )


@pytest.fixture
def sample_task_definition() -> BeadDefinition:
    """Return a sample task bead definition."""
    return BeadDefinition(
        title="Foundation",
        bead_type=BeadType.TASK,
        priority=1,
        category=BeadCategory.FOUNDATION,
        description="Foundation tasks",
        phase_names=["Phase 1: Setup"],
        task_ids=["T001", "T002"],
    )


@pytest.fixture
def sample_created_bead(
    sample_task_definition: BeadDefinition,
) -> CreatedBead:
    """Return a sample CreatedBead."""
    return CreatedBead(bd_id="abc123", definition=sample_task_definition)


@pytest.fixture
def spec_dir_with_tasks(temp_dir: Path, sample_tasks_md: str) -> Path:
    """Create a temp spec directory with tasks.md."""
    spec_dir = temp_dir / "specs" / "001-test-project"
    spec_dir.mkdir(parents=True)
    (spec_dir / "tasks.md").write_text(sample_tasks_md)
    (spec_dir / "spec.md").write_text("# Test Project Spec\n\nA test project.")
    (spec_dir / "plan.md").write_text("# Plan\n\nImplementation plan.")
    return spec_dir


@pytest.fixture
def spec_dir_with_deps(temp_dir: Path, sample_tasks_md_with_deps: str) -> Path:
    """Create a temp spec directory with dependency tasks."""
    spec_dir = temp_dir / "specs" / "002-dep-project"
    spec_dir.mkdir(parents=True)
    (spec_dir / "tasks.md").write_text(sample_tasks_md_with_deps)
    return spec_dir
