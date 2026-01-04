"""Unit tests for task parsing actions.

Tests the tasks.py action module including:
- get_phase_names action for extracting phases from tasks.md files
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.library.actions.tasks import get_phase_names


class TestGetPhaseNames:
    """Tests for get_phase_names action."""

    @pytest.mark.asyncio
    async def test_extracts_phases_from_task_file(self, tmp_path: Path) -> None:
        """Test extracts phase names from a well-formed tasks.md file."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text(
            """# Tasks

## Setup
- [ ] T001 Initialize the project
- [ ] T002 Configure dependencies

## Implementation
- [ ] T003 [P] Implement feature A
- [ ] T004 [P] Implement feature B

## Testing
- [ ] T005 Write unit tests
- [ ] T006 Write integration tests
"""
        )

        result = await get_phase_names(task_file)

        assert result == ["Setup", "Implementation", "Testing"]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_phases(self, tmp_path: Path) -> None:
        """Test returns empty list when file has no phase headers."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text(
            """# Tasks

- [ ] T001 First task
- [ ] T002 Second task
"""
        )

        result = await get_phase_names(task_file)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_file_not_found(self, tmp_path: Path) -> None:
        """Test returns empty list when file doesn't exist."""
        task_file = tmp_path / "nonexistent.md"

        result = await get_phase_names(task_file)

        assert result == []

    @pytest.mark.asyncio
    async def test_accepts_string_path(self, tmp_path: Path) -> None:
        """Test accepts string path instead of Path object."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text(
            """## Phase One
- [ ] T001 Task one
"""
        )

        result = await get_phase_names(str(task_file))

        assert result == ["Phase One"]

    @pytest.mark.asyncio
    async def test_preserves_phase_order(self, tmp_path: Path) -> None:
        """Test preserves order of phases as they appear in file."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text(
            """## Zebra
- [ ] T001 Task

## Alpha
- [ ] T002 Task

## Middle
- [ ] T003 Task
"""
        )

        result = await get_phase_names(task_file)

        # Order should be as they appear, not alphabetical
        assert result == ["Zebra", "Alpha", "Middle"]

    @pytest.mark.asyncio
    async def test_excludes_phases_with_no_tasks(self, tmp_path: Path) -> None:
        """Test excludes phases that have no tasks (e.g., documentation headers)."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text(
            """## Empty Phase

## Phase With Tasks
- [ ] T001 Task one
"""
        )

        result = await get_phase_names(task_file)

        # Empty phases should be excluded (they're just documentation headers)
        assert result == ["Phase With Tasks"]

    @pytest.mark.asyncio
    async def test_excludes_documentation_headers(self, tmp_path: Path) -> None:
        """Test excludes typical documentation headers without tasks."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text(
            """# Tasks: Feature Name

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Some documentation text here.

## Phase 1: Setup

- [ ] T001 Create directory structure
- [ ] T002 Initialize configuration

## Dependencies & Execution Order

Some notes about dependencies.

## Phase 2: Implementation

- [ ] T003 Implement feature
"""
        )

        result = await get_phase_names(task_file)

        # Only phases with actual tasks should be returned
        assert result == ["Phase 1: Setup", "Phase 2: Implementation"]

    @pytest.mark.asyncio
    async def test_handles_complex_phase_names(self, tmp_path: Path) -> None:
        """Test handles phase names with special characters."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text(
            """## Phase 1: Setup & Configuration
- [ ] T001 Task

## Phase 2 - Implementation (Core)
- [ ] T002 Task
"""
        )

        result = await get_phase_names(task_file)

        assert result == [
            "Phase 1: Setup & Configuration",
            "Phase 2 - Implementation (Core)",
        ]

    @pytest.mark.asyncio
    async def test_handles_empty_file(self, tmp_path: Path) -> None:
        """Test handles empty file gracefully."""
        task_file = tmp_path / "tasks.md"
        task_file.write_text("")

        result = await get_phase_names(task_file)

        assert result == []
