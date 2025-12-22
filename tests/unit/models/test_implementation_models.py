"""Unit tests for implementation data models.

Tests the Pydantic models used in the implementation workflow:
- Task
- FileChange
- ValidationResult
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.models.implementation import (
    ChangeType,
    FileChange,
    Task,
    TaskStatus,
    ValidationResult,
    ValidationStep,
)

# =============================================================================
# Task Tests
# =============================================================================


class TestTask:
    """Tests for Task model."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating Task with required fields only."""
        task = Task(
            id="T001",
            description="Implement authentication module",
        )

        assert task.id == "T001"
        assert task.description == "Implement authentication module"
        assert task.status == TaskStatus.PENDING  # default
        assert task.parallel is False  # default
        assert task.user_story is None
        assert task.phase is None
        assert task.dependencies == []

    def test_creation_with_all_fields(self) -> None:
        """Test creating Task with all fields."""
        task = Task(
            id="T042",
            description="Add authentication to API",
            status=TaskStatus.IN_PROGRESS,
            parallel=True,
            user_story="US001",
            phase="Backend Setup",
            dependencies=["T001", "T002"],
        )

        assert task.id == "T042"
        assert task.description == "Add authentication to API"
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.parallel is True
        assert task.user_story == "US001"
        assert task.phase == "Backend Setup"
        assert task.dependencies == ["T001", "T002"]

    def test_id_requires_pattern_t_followed_by_digits(self) -> None:
        """Test task ID pattern must be T### format."""
        # Valid IDs
        Task(id="T001", description="Test")
        Task(id="T999", description="Test")
        Task(id="T00001", description="Test")

        # Invalid IDs
        with pytest.raises(ValidationError) as exc_info:
            Task(id="1001", description="Test")
        assert "id" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            Task(id="Task001", description="Test")
        assert "id" in str(exc_info.value)

    def test_id_pattern_requires_minimum_three_digits(self) -> None:
        """Test task ID must have at least 3 digits."""
        # Valid
        Task(id="T001", description="Test")

        # Invalid - less than 3 digits
        with pytest.raises(ValidationError):
            Task(id="T01", description="Test")

    def test_description_required_nonempty(self) -> None:
        """Test description is required and must be non-empty."""
        # Valid
        Task(id="T001", description="A")

        # Empty description
        with pytest.raises(ValidationError) as exc_info:
            Task(id="T001", description="")
        assert "description" in str(exc_info.value)

    def test_status_defaults_to_pending(self) -> None:
        """Test status defaults to PENDING."""
        task = Task(id="T001", description="Test")

        assert task.status == TaskStatus.PENDING

    def test_status_accepts_enum_and_string(self) -> None:
        """Test status accepts TaskStatus enum or string value."""
        task1 = Task(id="T001", description="Test", status=TaskStatus.COMPLETED)
        assert task1.status == TaskStatus.COMPLETED

        task2 = Task(id="T001", description="Test", status="completed")  # type: ignore[arg-type]
        assert task2.status == TaskStatus.COMPLETED

    def test_parallel_defaults_to_false(self) -> None:
        """Test parallel defaults to False."""
        task = Task(id="T001", description="Test")

        assert task.parallel is False

    def test_user_story_pattern_optional(self) -> None:
        """Test user_story pattern is optional."""
        # Valid with US pattern
        task1 = Task(id="T001", description="Test", user_story="US1")
        assert task1.user_story == "US1"

        task2 = Task(id="T001", description="Test", user_story="US999")
        assert task2.user_story == "US999"

        # Valid without user_story
        task3 = Task(id="T001", description="Test")
        assert task3.user_story is None

    def test_user_story_pattern_validation(self) -> None:
        """Test user_story pattern validation."""
        # Invalid pattern
        with pytest.raises(ValidationError) as exc_info:
            Task(id="T001", description="Test", user_story="story1")
        assert "user_story" in str(exc_info.value)

        with pytest.raises(ValidationError):
            Task(id="T001", description="Test", user_story="U1")  # Missing S

    def test_dependencies_defaults_to_empty_list(self) -> None:
        """Test dependencies defaults to empty list."""
        task = Task(id="T001", description="Test")

        assert task.dependencies == []
        assert isinstance(task.dependencies, list)

    def test_is_parallelizable_property(self) -> None:
        """Test is_parallelizable property."""
        # Parallelizable: marked parallel and no dependencies
        task1 = Task(
            id="T001",
            description="Test",
            parallel=True,
            dependencies=[],
        )
        assert task1.is_parallelizable is True

        # Not parallelizable: has dependencies
        task2 = Task(
            id="T001",
            description="Test",
            parallel=True,
            dependencies=["T002"],
        )
        assert task2.is_parallelizable is False

        # Not parallelizable: not marked parallel
        task3 = Task(
            id="T001",
            description="Test",
            parallel=False,
            dependencies=[],
        )
        assert task3.is_parallelizable is False

    def test_is_actionable_property(self) -> None:
        """Test is_actionable property."""
        # Actionable: PENDING status
        task1 = Task(
            id="T001",
            description="Test",
            status=TaskStatus.PENDING,
        )
        assert task1.is_actionable is True

        # Not actionable: COMPLETED status
        task2 = Task(
            id="T001",
            description="Test",
            status=TaskStatus.COMPLETED,
        )
        assert task2.is_actionable is False

        # Not actionable: IN_PROGRESS status
        task3 = Task(
            id="T001",
            description="Test",
            status=TaskStatus.IN_PROGRESS,
        )
        assert task3.is_actionable is False

        # Not actionable: FAILED status
        task4 = Task(
            id="T001",
            description="Test",
            status=TaskStatus.FAILED,
        )
        assert task4.is_actionable is False

    def test_task_is_frozen(self) -> None:
        """Test Task model is immutable (frozen)."""
        task = Task(id="T001", description="Test")

        with pytest.raises(ValidationError):
            task.description = "Updated description"  # type: ignore[misc]

        with pytest.raises(ValidationError):
            task.status = TaskStatus.COMPLETED  # type: ignore[misc]

    def test_task_with_multiple_dependencies(self) -> None:
        """Test Task with multiple dependencies."""
        task = Task(
            id="T005",
            description="Final step",
            dependencies=["T001", "T002", "T003"],
        )

        assert len(task.dependencies) == 3
        assert "T001" in task.dependencies
        assert "T002" in task.dependencies
        assert "T003" in task.dependencies

    def test_task_comparison_by_id(self) -> None:
        """Test tasks can be compared by ID."""
        task1 = Task(id="T001", description="First task")
        task2 = Task(id="T002", description="Second task")

        # Both are Task instances
        assert isinstance(task1, Task)
        assert isinstance(task2, Task)
        assert task1.id != task2.id


# =============================================================================
# FileChange Tests
# =============================================================================


class TestFileChange:
    """Tests for FileChange model."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating FileChange with required fields only."""
        change = FileChange(
            file_path="src/maverick/models/implementation.py",
        )

        assert change.file_path == "src/maverick/models/implementation.py"
        assert change.change_type == ChangeType.MODIFIED  # default
        assert change.lines_added == 0
        assert change.lines_removed == 0
        assert change.old_path is None

    def test_creation_with_all_fields(self) -> None:
        """Test creating FileChange with all fields."""
        change = FileChange(
            file_path="src/maverick/agents/implementer.py",
            change_type=ChangeType.ADDED,
            lines_added=150,
            lines_removed=0,
            old_path=None,
        )

        assert change.file_path == "src/maverick/agents/implementer.py"
        assert change.change_type == ChangeType.ADDED
        assert change.lines_added == 150
        assert change.lines_removed == 0
        assert change.old_path is None

    def test_change_type_defaults_to_modified(self) -> None:
        """Test change_type defaults to MODIFIED."""
        change = FileChange(file_path="test.py")

        assert change.change_type == ChangeType.MODIFIED

    def test_change_type_accepts_enum_and_string(self) -> None:
        """Test change_type accepts ChangeType enum or string value."""
        change1 = FileChange(
            file_path="test.py",
            change_type=ChangeType.ADDED,
        )
        assert change1.change_type == ChangeType.ADDED

        change2 = FileChange(
            file_path="test.py",
            change_type="deleted",  # type: ignore[arg-type]
        )
        assert change2.change_type == ChangeType.DELETED

    def test_lines_added_defaults_to_zero(self) -> None:
        """Test lines_added defaults to 0."""
        change = FileChange(file_path="test.py")

        assert change.lines_added == 0

    def test_lines_removed_defaults_to_zero(self) -> None:
        """Test lines_removed defaults to 0."""
        change = FileChange(file_path="test.py")

        assert change.lines_removed == 0

    def test_lines_added_must_be_nonnegative(self) -> None:
        """Test lines_added must be >= 0."""
        # Valid
        FileChange(file_path="test.py", lines_added=0)
        FileChange(file_path="test.py", lines_added=100)

        # Invalid
        with pytest.raises(ValidationError) as exc_info:
            FileChange(file_path="test.py", lines_added=-1)
        assert "lines_added" in str(exc_info.value)

    def test_lines_removed_must_be_nonnegative(self) -> None:
        """Test lines_removed must be >= 0."""
        # Valid
        FileChange(file_path="test.py", lines_removed=0)
        FileChange(file_path="test.py", lines_removed=50)

        # Invalid
        with pytest.raises(ValidationError) as exc_info:
            FileChange(file_path="test.py", lines_removed=-1)
        assert "lines_removed" in str(exc_info.value)

    def test_old_path_optional_for_renamed(self) -> None:
        """Test old_path is optional, used for rename changes."""
        # Without old_path
        change1 = FileChange(
            file_path="new_name.py",
            change_type=ChangeType.RENAMED,
        )
        assert change1.old_path is None

        # With old_path
        change2 = FileChange(
            file_path="new_name.py",
            change_type=ChangeType.RENAMED,
            old_path="old_name.py",
        )
        assert change2.old_path == "old_name.py"

    def test_net_lines_property(self) -> None:
        """Test net_lines computed property."""
        # Added file
        change1 = FileChange(
            file_path="new.py",
            change_type=ChangeType.ADDED,
            lines_added=100,
            lines_removed=0,
        )
        assert change1.net_lines == 100

        # Modified file with net addition
        change2 = FileChange(
            file_path="modified.py",
            lines_added=50,
            lines_removed=10,
        )
        assert change2.net_lines == 40

        # Modified file with net deletion
        change3 = FileChange(
            file_path="refactored.py",
            lines_added=20,
            lines_removed=80,
        )
        assert change3.net_lines == -60

        # Deleted file
        change4 = FileChange(
            file_path="deleted.py",
            change_type=ChangeType.DELETED,
            lines_added=0,
            lines_removed=50,
        )
        assert change4.net_lines == -50

    def test_net_lines_zero(self) -> None:
        """Test net_lines when equal additions and deletions."""
        change = FileChange(
            file_path="test.py",
            lines_added=25,
            lines_removed=25,
        )

        assert change.net_lines == 0

    def test_file_change_is_frozen(self) -> None:
        """Test FileChange model is immutable (frozen)."""
        change = FileChange(file_path="test.py")

        with pytest.raises(ValidationError):
            change.file_path = "new_test.py"  # type: ignore[misc]

        with pytest.raises(ValidationError):
            change.lines_added = 100  # type: ignore[misc]

    def test_file_path_required(self) -> None:
        """Test file_path is required."""
        with pytest.raises(ValidationError):
            FileChange()  # type: ignore[call-arg]

    def test_various_file_paths(self) -> None:
        """Test various valid file path formats."""
        paths = [
            "single.py",
            "nested/path/file.py",
            "src/maverick/agents/base.py",
            "tests/unit/test_file.py",
            "README.md",
            ".github/workflows/test.yml",
        ]

        for path in paths:
            change = FileChange(file_path=path)
            assert change.file_path == path


# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ValidationResult with required fields only."""
        result = ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
        )

        assert result.step == ValidationStep.FORMAT
        assert result.success is True
        assert result.output == ""  # default
        assert result.duration_ms == 0  # default
        assert result.auto_fixed is False  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ValidationResult with all fields."""
        result = ValidationResult(
            step=ValidationStep.LINT,
            success=False,
            output="E501 line too long (105 > 100 characters)",
            duration_ms=2500,
            auto_fixed=True,
        )

        assert result.step == ValidationStep.LINT
        assert result.success is False
        assert result.output == "E501 line too long (105 > 100 characters)"
        assert result.duration_ms == 2500
        assert result.auto_fixed is True

    def test_step_accepts_enum_and_string(self) -> None:
        """Test step accepts ValidationStep enum or string value."""
        result1 = ValidationResult(
            step=ValidationStep.TEST,
            success=True,
        )
        assert result1.step == ValidationStep.TEST

        result2 = ValidationResult(
            step="typecheck",  # type: ignore[arg-type]
            success=True,
        )
        assert result2.step == ValidationStep.TYPECHECK

    def test_success_required_and_boolean(self) -> None:
        """Test success is required and must be boolean."""
        # Valid
        ValidationResult(step=ValidationStep.FORMAT, success=True)
        ValidationResult(step=ValidationStep.FORMAT, success=False)

        # Invalid - missing success
        with pytest.raises(ValidationError):
            ValidationResult(step=ValidationStep.FORMAT)  # type: ignore[call-arg]

    def test_output_defaults_to_empty_string(self) -> None:
        """Test output defaults to empty string."""
        result = ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
        )

        assert result.output == ""
        assert isinstance(result.output, str)

    def test_output_can_contain_multiline_text(self) -> None:
        """Test output can be multiline text."""
        output = "Error on line 5: undefined variable\nError on line 10: unused import"
        result = ValidationResult(
            step=ValidationStep.LINT,
            success=False,
            output=output,
        )

        assert result.output == output
        assert "\n" in result.output

    def test_duration_ms_defaults_to_zero(self) -> None:
        """Test duration_ms defaults to 0."""
        result = ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
        )

        assert result.duration_ms == 0

    def test_duration_ms_must_be_nonnegative(self) -> None:
        """Test duration_ms must be >= 0."""
        # Valid
        ValidationResult(step=ValidationStep.FORMAT, success=True, duration_ms=0)
        ValidationResult(step=ValidationStep.FORMAT, success=True, duration_ms=5000)

        # Invalid
        with pytest.raises(ValidationError) as exc_info:
            ValidationResult(
                step=ValidationStep.FORMAT,
                success=True,
                duration_ms=-1,
            )
        assert "duration_ms" in str(exc_info.value)

    def test_auto_fixed_defaults_to_false(self) -> None:
        """Test auto_fixed defaults to False."""
        result = ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
        )

        assert result.auto_fixed is False

    def test_validation_result_scenarios(self) -> None:
        """Test realistic validation result scenarios."""
        # Format step that auto-fixed issues
        format_result = ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
            output="Formatted 5 files",
            duration_ms=1200,
            auto_fixed=True,
        )
        assert format_result.auto_fixed is True
        assert format_result.success is True

        # Lint step that found issues
        lint_result = ValidationResult(
            step=ValidationStep.LINT,
            success=False,
            output="E501 line too long\nF401 unused import",
            duration_ms=800,
            auto_fixed=False,
        )
        assert lint_result.success is False
        assert lint_result.auto_fixed is False

        # Test step that passed
        test_result = ValidationResult(
            step=ValidationStep.TEST,
            success=True,
            output="10 passed in 3.45s",
            duration_ms=3450,
        )
        assert test_result.success is True

    def test_validation_result_is_frozen(self) -> None:
        """Test ValidationResult model is immutable (frozen)."""
        result = ValidationResult(
            step=ValidationStep.FORMAT,
            success=True,
        )

        with pytest.raises(ValidationError):
            result.success = False  # type: ignore[misc]

        with pytest.raises(ValidationError):
            result.output = "Modified output"  # type: ignore[misc]

    def test_all_validation_steps(self) -> None:
        """Test ValidationResult with each ValidationStep."""
        for step in ValidationStep:
            result = ValidationResult(
                step=step,
                success=True,
            )
            assert result.step == step


# =============================================================================
# Model Serialization Tests
# =============================================================================


class TestModelSerialization:
    """Tests for model serialization."""

    def test_task_to_dict(self) -> None:
        """Test Task serializes to dict correctly."""
        task = Task(
            id="T001",
            description="Test task",
            status=TaskStatus.COMPLETED,
            parallel=True,
        )

        data = task.model_dump()

        assert data["id"] == "T001"
        assert data["description"] == "Test task"
        assert data["status"] == "completed"
        assert data["parallel"] is True

    def test_file_change_to_dict(self) -> None:
        """Test FileChange serializes to dict correctly."""
        change = FileChange(
            file_path="test.py",
            change_type=ChangeType.ADDED,
            lines_added=50,
        )

        data = change.model_dump()

        assert data["file_path"] == "test.py"
        assert data["change_type"] == "added"
        assert data["lines_added"] == 50

    def test_validation_result_to_dict(self) -> None:
        """Test ValidationResult serializes to dict correctly."""
        result = ValidationResult(
            step=ValidationStep.LINT,
            success=True,
            output="All good",
            duration_ms=1000,
        )

        data = result.model_dump()

        assert data["step"] == "lint"
        assert data["success"] is True
        assert data["output"] == "All good"
        assert data["duration_ms"] == 1000

    def test_task_from_dict(self) -> None:
        """Test Task deserializes from dict."""
        data = {
            "id": "T010",
            "description": "Implementation task",
            "status": "in_progress",
            "parallel": False,
            "dependencies": ["T005"],
        }

        task = Task.model_validate(data)

        assert task.id == "T010"
        assert task.description == "Implementation task"
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.parallel is False

    def test_file_change_from_dict(self) -> None:
        """Test FileChange deserializes from dict."""
        data = {
            "file_path": "src/new_module.py",
            "change_type": "added",
            "lines_added": 200,
            "lines_removed": 0,
        }

        change = FileChange.model_validate(data)

        assert change.file_path == "src/new_module.py"
        assert change.change_type == ChangeType.ADDED
        assert change.lines_added == 200

    def test_validation_result_from_dict(self) -> None:
        """Test ValidationResult deserializes from dict."""
        data = {
            "step": "test",
            "success": True,
            "output": "All tests passed",
            "duration_ms": 5000,
            "auto_fixed": False,
        }

        result = ValidationResult.model_validate(data)

        assert result.step == ValidationStep.TEST
        assert result.success is True
        assert result.duration_ms == 5000


# =============================================================================
# Model Relationship Tests
# =============================================================================


class TestModelRelationships:
    """Tests for relationships between models."""

    def test_task_with_multiple_file_changes(self) -> None:
        """Test multiple FileChanges can represent a task's impact."""
        task = Task(
            id="T001",
            description="Refactor authentication module",
        )

        changes = [
            FileChange(
                file_path="src/auth.py",
                change_type=ChangeType.MODIFIED,
                lines_added=50,
                lines_removed=30,
            ),
            FileChange(
                file_path="tests/test_auth.py",
                change_type=ChangeType.MODIFIED,
                lines_added=100,
                lines_removed=20,
            ),
        ]

        assert task.id == "T001"
        assert len(changes) == 2
        total_net_lines = sum(c.net_lines for c in changes)
        assert total_net_lines == 100  # (50-30) + (100-20)

    def test_validation_pipeline_sequence(self) -> None:
        """Test sequence of ValidationResults representing a pipeline."""
        pipeline = [
            ValidationResult(
                step=ValidationStep.FORMAT,
                success=True,
                duration_ms=1000,
                auto_fixed=True,
            ),
            ValidationResult(
                step=ValidationStep.LINT,
                success=True,
                duration_ms=2000,
            ),
            ValidationResult(
                step=ValidationStep.TYPECHECK,
                success=True,
                duration_ms=3000,
            ),
            ValidationResult(
                step=ValidationStep.TEST,
                success=True,
                duration_ms=5000,
            ),
        ]

        assert len(pipeline) == 4
        assert all(r.success for r in pipeline)
        total_duration = sum(r.duration_ms for r in pipeline)
        assert total_duration == 11000

    def test_task_with_dependencies_and_parallel_flag(self) -> None:
        """Test Task properties with dependencies and parallel flags."""
        # Sequential task with dependency
        sequential = Task(
            id="T002",
            description="Step 2",
            parallel=False,
            dependencies=["T001"],
        )
        assert sequential.is_parallelizable is False

        # Parallel task without dependency
        parallel = Task(
            id="T003",
            description="Step 3 (parallel)",
            parallel=True,
            dependencies=[],
        )
        assert parallel.is_parallelizable is True
