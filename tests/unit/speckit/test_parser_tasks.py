"""Table-driven tests for the tasks.md grammar (maverick.speckit.parser)."""

from __future__ import annotations

import pytest

from maverick.speckit.errors import SpeckitParseError, SpeckitValidationError
from maverick.speckit.parser import parse_tasks_md


class TestHappyPath:
    def test_full_fixture_produces_five_phases(self, full_tasks_md: str) -> None:
        phases, story_deps = parse_tasks_md(full_tasks_md)
        assert [p.number for p in phases] == [1, 2, 3, 4, 5]
        assert story_deps == (("US2", "US1"),)

    def test_task_ids_preserved_in_file_order(self, full_tasks_md: str) -> None:
        phases, _ = parse_tasks_md(full_tasks_md)
        all_ids = [t.task_id for phase in phases for t in phase.tasks]
        assert all_ids == [f"T{i:03d}" for i in range(1, 12)]

    def test_parallel_marker_parsed(self, full_tasks_md: str) -> None:
        phases, _ = parse_tasks_md(full_tasks_md)
        by_id = {t.task_id: t for phase in phases for t in phase.tasks}
        assert by_id["T003"].parallel is True
        assert by_id["T001"].parallel is False
        assert by_id["T006"].parallel is True

    def test_story_marker_parsed(self, full_tasks_md: str) -> None:
        phases, _ = parse_tasks_md(full_tasks_md)
        by_id = {t.task_id: t for phase in phases for t in phase.tasks}
        assert by_id["T006"].story_id == "US1"
        assert by_id["T007"].story_id == "US1"
        assert by_id["T008"].story_id == "US2"
        assert by_id["T001"].story_id is None

    def test_checked_vs_unchecked(self, full_tasks_md: str) -> None:
        phases, _ = parse_tasks_md(full_tasks_md)
        by_id = {t.task_id: t for phase in phases for t in phase.tasks}
        assert by_id["T002"].completed is True
        assert by_id["T009"].completed is True
        assert by_id["T001"].completed is False

    def test_line_numbers_are_stable_and_1_indexed(self, full_tasks_md: str) -> None:
        phases, _ = parse_tasks_md(full_tasks_md)
        by_id = {t.task_id: t for phase in phases for t in phase.tasks}
        lines = full_tasks_md.splitlines()
        for task_id, task in by_id.items():
            assert lines[task.line_number - 1].strip().startswith("- [")
            assert task_id in lines[task.line_number - 1]

    def test_explicit_depends_on_extracted(self, full_tasks_md: str) -> None:
        phases, _ = parse_tasks_md(full_tasks_md)
        by_id = {t.task_id: t for phase in phases for t in phase.tasks}
        assert by_id["T004"].explicit_deps == ("T003",)
        assert by_id["T001"].explicit_deps == ()

    def test_file_path_tokens_extracted(self, full_tasks_md: str) -> None:
        phases, _ = parse_tasks_md(full_tasks_md)
        by_id = {t.task_id: t for phase in phases for t in phase.tasks}
        assert "src/config.py" in by_id["T003"].file_paths
        assert "tests/test_feature_a.py" in by_id["T007"].file_paths
        assert by_id["T001"].file_paths == ()

    def test_fenced_code_block_is_skipped(self, full_tasks_md: str) -> None:
        phases, _ = parse_tasks_md(full_tasks_md)
        all_ids = {t.task_id for phase in phases for t in phase.tasks}
        assert "T999" not in all_ids

    def test_dependencies_section_story_pairs(self, full_tasks_md: str) -> None:
        _, story_deps = parse_tasks_md(full_tasks_md)
        assert ("US2", "US1") in story_deps

    def test_dependencies_section_multiple_blockers(self) -> None:
        content = """\
## Phase 1: Setup

- [ ] T001 Do a thing

## Dependencies

- US3: Depends on US1, US2
"""
        _, story_deps = parse_tasks_md(content)
        assert set(story_deps) == {("US3", "US1"), ("US3", "US2")}

    def test_prose_and_checkpoint_lines_ignored(self) -> None:
        content = """\
## Phase 1: Setup

Some prose about this phase.

**Checkpoint**: everything works

- [ ] T001 Do a thing

### A subheading

more prose
"""
        phases, _ = parse_tasks_md(content)
        assert len(phases) == 1
        assert len(phases[0].tasks) == 1

    def test_content_before_first_phase_heading_ignored(self) -> None:
        content = """\
# Tasks: Something

**Input**: some preamble
**Format**: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [ ] T001 Do a thing
"""
        phases, _ = parse_tasks_md(content)
        assert len(phases) == 1
        assert phases[0].tasks[0].task_id == "T001"

    def test_non_phase_h2_terminates_phase_section(self) -> None:
        content = """\
## Phase 1: Setup

- [ ] T001 Do a thing

## Some Other Section

- [ ] this is not parsed as a task since no active phase

## Phase 2: Next

- [ ] T002 Another thing
"""
        phases, _ = parse_tasks_md(content)
        assert [p.number for p in phases] == [1, 2]
        assert phases[0].tasks[0].task_id == "T001"
        assert phases[1].tasks[0].task_id == "T002"

    def test_phase_may_be_empty(self) -> None:
        content = """\
## Phase 1: Setup

## Phase 2: Next

- [ ] T001 A thing
"""
        phases, _ = parse_tasks_md(content)
        assert phases[0].tasks == ()
        assert phases[1].tasks[0].task_id == "T001"


class TestHardErrors:
    def test_malformed_task_shaped_line_raises_parse_error(self) -> None:
        content = """\
## Phase 1: Setup

- [ ] do stuff without a task id
"""
        with pytest.raises(SpeckitParseError) as exc_info:
            parse_tasks_md(content, file="tasks.md")
        err = exc_info.value
        assert err.file == "tasks.md"
        assert err.line == 3
        assert err.expected
        assert err.suggestion

    def test_non_increasing_phase_numbers_raises_parse_error(self) -> None:
        content = """\
## Phase 2: Second

- [ ] T001 A thing

## Phase 1: First (out of order)

- [ ] T002 Another thing
"""
        with pytest.raises(SpeckitParseError) as exc_info:
            parse_tasks_md(content)
        assert "increasing" in str(exc_info.value)

    def test_duplicate_task_id_raises_validation_error_with_both_lines(self) -> None:
        content = """\
## Phase 1: Setup

- [ ] T001 First occurrence
- [ ] T001 Second occurrence
"""
        with pytest.raises(SpeckitValidationError) as exc_info:
            parse_tasks_md(content)
        err = exc_info.value
        assert err.task_id == "T001"
        assert err.lines == (3, 4)

    def test_unknown_dependency_reference_raises_validation_error(self) -> None:
        content = """\
## Phase 1: Setup

- [ ] T001 Depends on T999 which does not exist
"""
        with pytest.raises(SpeckitValidationError) as exc_info:
            parse_tasks_md(content)
        err = exc_info.value
        assert err.unknown_ref == "T999"
        assert err.task_id == "T001"
