"""Unit tests for task parser."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from maverick.exceptions import TaskParseError
from maverick.models.implementation import Task, TaskStatus
from maverick.utils.task_parser import (
    format_task_checkbox,
    get_completed_count,
    get_pending_count,
    parse_task_line,
    parse_tasks_md,
)


class TestParseTaskLine:
    """Tests for parse_task_line function."""

    def test_parse_task_line_basic(self) -> None:
        """Test parsing a basic task line."""
        line = "- [ ] T001 Create directory"
        task = parse_task_line(line, 1)

        assert task is not None
        assert task.id == "T001"
        assert task.description == "Create directory"
        assert task.status == TaskStatus.PENDING
        assert task.parallel is False

    def test_parse_task_line_completed(self) -> None:
        """Test parsing a completed task line."""
        line = "- [x] T001 Create directory"
        task = parse_task_line(line, 1)

        assert task is not None
        assert task.status == TaskStatus.COMPLETED

    def test_parse_task_line_completed_uppercase_x(self) -> None:
        """Test parsing a completed task with uppercase X."""
        line = "- [X] T001 Create directory"
        task = parse_task_line(line, 1)

        assert task is not None
        assert task.status == TaskStatus.COMPLETED

    def test_parse_task_line_with_parallel_marker_bracket(self) -> None:
        """Test parsing task with [P] parallel marker."""
        line = "- [ ] T001 [P] Create directory"
        task = parse_task_line(line, 1)

        assert task is not None
        assert task.parallel is True
        assert task.description == "Create directory"

    def test_parse_task_line_with_parallel_marker_colon(self) -> None:
        """Test parsing task with P: parallel marker."""
        line = "- [ ] T001 P: Create directory"
        task = parse_task_line(line, 1)

        assert task is not None
        assert task.parallel is True
        assert task.description == "Create directory"

    def test_parse_task_line_with_user_story(self) -> None:
        """Test parsing task with user story reference."""
        line = "- [ ] T001 [US1] Create directory"
        task = parse_task_line(line, 1)

        assert task is not None
        assert task.user_story == "US1"
        assert task.description == "Create directory"

    def test_parse_task_line_with_parallel_and_user_story(self) -> None:
        """Test parsing task with both parallel and user story."""
        line = "- [ ] T001 [P] [US2] Complex task"
        task = parse_task_line(line, 1)

        assert task is not None
        assert task.parallel is True
        assert task.user_story == "US2"
        assert task.description == "Complex task"

    def test_parse_task_line_with_phase(self) -> None:
        """Test parsing task with phase context."""
        line = "- [ ] T001 Create directory"
        task = parse_task_line(line, 1, current_phase="Setup")

        assert task is not None
        assert task.phase == "Setup"

    def test_parse_task_line_ignores_non_task_lines(self) -> None:
        """Test parse_task_line returns None for non-task lines."""
        lines = [
            "This is just text",
            "## Phase 1",
            "  Not a task",
            "",
            "- Not a task (no checkbox)",
        ]

        for line in lines:
            task = parse_task_line(line, 1)
            assert task is None

    def test_parse_task_line_raises_on_invalid_format(self) -> None:
        """Test parse_task_line raises TaskParseError on invalid format."""
        # Task ID with only 2 digits is invalid (requires 3+)
        line = "- [ ] T01 description"

        with pytest.raises(TaskParseError) as exc_info:
            parse_task_line(line, 5)

        assert exc_info.value.line_number == 5

    def test_parse_task_line_multiple_digit_task_id(self) -> None:
        """Test parsing task with various ID formats (3+ digits required)."""
        valid_ids = ["T001", "T100", "T9999"]

        for task_id in valid_ids:
            line = f"- [ ] {task_id} Test task"
            task = parse_task_line(line, 1)
            assert task is not None
            assert task.id == task_id.upper()

    def test_parse_task_line_long_description(self) -> None:
        """Test parsing task with long description."""
        long_desc = "This is a very long task description with many words and details"
        line = f"- [ ] T001 {long_desc}"
        task = parse_task_line(line, 1)

        assert task is not None
        assert task.description == long_desc

    def test_parse_task_line_with_special_characters(self) -> None:
        """Test parsing task with special characters in description."""
        line = "- [ ] T001 Create API endpoint (POST /users)"
        task = parse_task_line(line, 1)

        assert task is not None
        assert "POST /users" in task.description


class TestParseTasksMd:
    """Tests for parse_tasks_md function."""

    def test_parse_tasks_md_basic(self) -> None:
        """Test parsing basic tasks.md content."""
        content = """- [ ] T001 First task
- [ ] T002 Second task
"""
        tasks, phases = parse_tasks_md(content)

        assert len(tasks) == 2
        assert tasks[0].id == "T001"
        assert tasks[1].id == "T002"

    def test_parse_tasks_md_with_phases(self) -> None:
        """Test parsing tasks.md with phase headers."""
        content = """## Setup
- [ ] T001 Create directory
- [ ] T002 Initialize git

## Implementation
- [ ] T003 Implement feature
"""
        tasks, phases = parse_tasks_md(content)

        assert len(tasks) == 3
        assert len(phases) == 2
        assert "Setup" in phases
        assert "Implementation" in phases
        assert len(phases["Setup"]) == 2
        assert len(phases["Implementation"]) == 1

    def test_parse_tasks_md_mixed_statuses(self) -> None:
        """Test parsing tasks with mixed completion statuses."""
        content = """- [x] T001 Completed task
- [ ] T002 Pending task
- [x] T003 Another completed
"""
        tasks, phases = parse_tasks_md(content)

        assert len(tasks) == 3
        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.PENDING
        assert tasks[2].status == TaskStatus.COMPLETED

    def test_parse_tasks_md_with_parallel_tasks(self) -> None:
        """Test parsing tasks with parallel markers."""
        content = """- [ ] T001 [P] Parallel task 1
- [ ] T002 [P] Parallel task 2
- [ ] T003 Sequential task
"""
        tasks, phases = parse_tasks_md(content)

        assert tasks[0].parallel is True
        assert tasks[1].parallel is True
        assert tasks[2].parallel is False

    def test_parse_tasks_md_with_user_stories(self) -> None:
        """Test parsing tasks with user story references."""
        content = """- [ ] T001 [US1] Feature 1
- [ ] T002 [US2] Feature 2
"""
        tasks, phases = parse_tasks_md(content)

        assert tasks[0].user_story == "US1"
        assert tasks[1].user_story == "US2"

    def test_parse_tasks_md_empty_content(self) -> None:
        """Test parsing empty content."""
        content = ""
        tasks, phases = parse_tasks_md(content)

        assert len(tasks) == 0
        assert len(phases) == 0

    def test_parse_tasks_md_only_headers(self) -> None:
        """Test parsing content with only headers (no tasks)."""
        content = """## Phase 1
## Phase 2
"""
        tasks, phases = parse_tasks_md(content)

        assert len(tasks) == 0
        assert len(phases) == 2

    def test_parse_tasks_md_preserves_order(self) -> None:
        """Test parsing preserves task order."""
        content = """- [ ] T005 Fifth
- [ ] T001 First
- [ ] T003 Third
"""
        tasks, phases = parse_tasks_md(content)

        assert [t.id for t in tasks] == ["T005", "T001", "T003"]

    def test_parse_tasks_md_multiline_content(self) -> None:
        """Test parsing realistic multi-phase content."""
        content = """## Phase 1: Setup
- [ ] T001 Create directory
- [ ] T002 Initialize project

## Phase 2: Implementation
- [ ] T003 [P] Build API
- [ ] T004 [P] Build UI
- [ ] T005 [US1] Create documentation

## Phase 3: Testing
- [x] T006 Run unit tests
- [ ] T007 Run integration tests
"""
        tasks, phases = parse_tasks_md(content)

        assert len(tasks) == 7
        assert len(phases) == 3
        assert len(phases["Phase 1: Setup"]) == 2
        assert len(phases["Phase 2: Implementation"]) == 3
        assert len(phases["Phase 3: Testing"]) == 2

    def test_parse_tasks_md_invalid_task_raises_error(self) -> None:
        """Test parsing invalid task format raises TaskParseError."""
        # T01 has only 2 digits, which is invalid (requires 3+)
        content = """- [ ] T001 Valid task
- [ ] T01 Bad task with 2-digit ID
"""
        with pytest.raises(TaskParseError):
            parse_tasks_md(content)

    def test_parse_tasks_md_tasks_without_phase(self) -> None:
        """Test parsing tasks before any phase header."""
        content = """- [ ] T001 Task without phase
## Phase 1
- [ ] T002 Task with phase
"""
        tasks, phases = parse_tasks_md(content)

        assert len(tasks) == 2
        assert tasks[0].phase is None
        assert tasks[1].phase == "Phase 1"


class TestFormatTaskCheckbox:
    """Tests for format_task_checkbox function."""

    def test_format_task_checkbox_pending(self) -> None:
        """Test formatting pending task checkbox."""
        task = Task(
            id="T001",
            description="Test task",
            status=TaskStatus.PENDING,
        )

        formatted = format_task_checkbox(task)

        assert formatted.startswith("- [ ]")
        assert "T001" in formatted
        assert "Test task" in formatted

    def test_format_task_checkbox_completed(self) -> None:
        """Test formatting completed task checkbox."""
        task = Task(
            id="T001",
            description="Test task",
            status=TaskStatus.COMPLETED,
        )

        formatted = format_task_checkbox(task)

        assert formatted.startswith("- [x]")
        assert "T001" in formatted

    def test_format_task_checkbox_with_parallel(self) -> None:
        """Test formatting task with parallel marker."""
        task = Task(
            id="T001",
            description="Test task",
            status=TaskStatus.PENDING,
            parallel=True,
        )

        formatted = format_task_checkbox(task)

        assert "[P]" in formatted
        assert "Test task" in formatted

    def test_format_task_checkbox_without_parallel(self) -> None:
        """Test formatting task without parallel marker."""
        task = Task(
            id="T001",
            description="Test task",
            status=TaskStatus.PENDING,
            parallel=False,
        )

        formatted = format_task_checkbox(task)

        assert "[P]" not in formatted

    def test_format_task_checkbox_with_user_story(self) -> None:
        """Test formatting task with user story."""
        task = Task(
            id="T001",
            description="Test task",
            status=TaskStatus.PENDING,
            user_story="US5",
        )

        formatted = format_task_checkbox(task)

        assert "[US5]" in formatted
        assert "Test task" in formatted

    def test_format_task_checkbox_full_metadata(self) -> None:
        """Test formatting task with all metadata."""
        task = Task(
            id="T042",
            description="Complex task",
            status=TaskStatus.COMPLETED,
            parallel=True,
            user_story="US3",
        )

        formatted = format_task_checkbox(task)

        assert "- [x]" in formatted
        assert "T042" in formatted
        assert "[P]" in formatted
        assert "[US3]" in formatted
        assert "Complex task" in formatted

    def test_format_task_checkbox_roundtrip(self) -> None:
        """Test formatting and re-parsing returns equivalent task."""
        original = Task(
            id="T001",
            description="Test task",
            status=TaskStatus.COMPLETED,
            parallel=True,
            user_story="US1",
        )

        formatted = format_task_checkbox(original)
        reparsed = parse_task_line(formatted, 1)

        assert reparsed is not None
        assert reparsed.id == original.id
        assert reparsed.description == original.description
        assert reparsed.status == original.status
        assert reparsed.parallel == original.parallel
        assert reparsed.user_story == original.user_story


class TestGetPendingCount:
    """Tests for get_pending_count function."""

    def test_get_pending_count_all_pending(self) -> None:
        """Test counting when all tasks are pending."""
        tasks = [
            Task(id="T001", description="Task 1", status=TaskStatus.PENDING),
            Task(id="T002", description="Task 2", status=TaskStatus.PENDING),
        ]

        count = get_pending_count(tasks)

        assert count == 2

    def test_get_pending_count_mixed(self) -> None:
        """Test counting with mixed statuses."""
        tasks = [
            Task(id="T001", description="Task 1", status=TaskStatus.PENDING),
            Task(id="T002", description="Task 2", status=TaskStatus.COMPLETED),
            Task(id="T003", description="Task 3", status=TaskStatus.PENDING),
        ]

        count = get_pending_count(tasks)

        assert count == 2

    def test_get_pending_count_none_pending(self) -> None:
        """Test counting when no tasks are pending."""
        tasks = [
            Task(id="T001", description="Task 1", status=TaskStatus.COMPLETED),
            Task(id="T002", description="Task 2", status=TaskStatus.FAILED),
        ]

        count = get_pending_count(tasks)

        assert count == 0

    def test_get_pending_count_empty(self) -> None:
        """Test counting empty task list."""
        tasks: list[Task] = []

        count = get_pending_count(tasks)

        assert count == 0


class TestGetCompletedCount:
    """Tests for get_completed_count function."""

    def test_get_completed_count_all_completed(self) -> None:
        """Test counting when all tasks are completed."""
        tasks = [
            Task(id="T001", description="Task 1", status=TaskStatus.COMPLETED),
            Task(id="T002", description="Task 2", status=TaskStatus.COMPLETED),
        ]

        count = get_completed_count(tasks)

        assert count == 2

    def test_get_completed_count_mixed(self) -> None:
        """Test counting with mixed statuses."""
        tasks = [
            Task(id="T001", description="Task 1", status=TaskStatus.COMPLETED),
            Task(id="T002", description="Task 2", status=TaskStatus.PENDING),
            Task(id="T003", description="Task 3", status=TaskStatus.COMPLETED),
        ]

        count = get_completed_count(tasks)

        assert count == 2

    def test_get_completed_count_none_completed(self) -> None:
        """Test counting when no tasks are completed."""
        tasks = [
            Task(id="T001", description="Task 1", status=TaskStatus.PENDING),
            Task(id="T002", description="Task 2", status=TaskStatus.FAILED),
        ]

        count = get_completed_count(tasks)

        assert count == 0

    def test_get_completed_count_empty(self) -> None:
        """Test counting empty task list."""
        tasks: list[Task] = []

        count = get_completed_count(tasks)

        assert count == 0


class TestTaskParseEdgeCases:
    """Tests for edge cases in task parsing."""

    def test_parse_task_with_brackets_in_description(self) -> None:
        """Test parsing task with brackets in description."""
        line = "- [ ] T001 Fix [bug] in API [POST]"
        task = parse_task_line(line, 1)

        assert task is not None
        # The parser should handle brackets in description
        assert "bug" in task.description

    def test_parse_task_with_whitespace_variations(self) -> None:
        """Test parsing task with varying whitespace."""
        lines = [
            "-[ ] T001 Task",  # No space after dash
            "- [ ] T001 Task",  # Standard
            "-  [  ] T001 Task",  # Extra spaces
        ]

        for line in lines:
            task = parse_task_line(line, 1)
            # Should handle variations gracefully
            if task is not None:
                assert task.id == "T001"

    def test_parse_task_markdown_emphasis_in_description(self) -> None:
        """Test parsing task with markdown emphasis in description."""
        line = "- [ ] T001 Fix **critical** bug"
        task = parse_task_line(line, 1)

        assert task is not None
        assert "critical" in task.description

    def test_parse_tasks_file_integration(self) -> None:
        """Test parsing from actual file."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tasks.md"
            content = """## Phase 1
- [ ] T001 First task
- [x] T002 [P] Completed parallel task
- [ ] T003 [US1] Task with user story

## Phase 2
- [ ] T004 Second phase task
"""
            path.write_text(content)

            # Import and use the parse_tasks_file function
            from maverick.utils.task_parser import parse_tasks_file

            tasks, phases = parse_tasks_file(path)

            assert len(tasks) == 4
            assert len(phases) == 2
            assert tasks[1].parallel is True
            assert tasks[2].user_story == "US1"
