"""Unit tests for implementation model enums.

Tests the enums used in the implementation models:
- TaskStatus
- ChangeType
- ValidationStep
"""

from __future__ import annotations

import pytest

from maverick.models.implementation import ChangeType, TaskStatus, ValidationStep

# =============================================================================
# TaskStatus Tests
# =============================================================================


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_task_status_pending_value(self) -> None:
        """Test TaskStatus.PENDING has correct value."""
        assert TaskStatus.PENDING.value == "pending"

    def test_task_status_in_progress_value(self) -> None:
        """Test TaskStatus.IN_PROGRESS has correct value."""
        assert TaskStatus.IN_PROGRESS.value == "in_progress"

    def test_task_status_completed_value(self) -> None:
        """Test TaskStatus.COMPLETED has correct value."""
        assert TaskStatus.COMPLETED.value == "completed"

    def test_task_status_failed_value(self) -> None:
        """Test TaskStatus.FAILED has correct value."""
        assert TaskStatus.FAILED.value == "failed"

    def test_task_status_skipped_value(self) -> None:
        """Test TaskStatus.SKIPPED has correct value."""
        assert TaskStatus.SKIPPED.value == "skipped"

    def test_task_status_is_string_enum(self) -> None:
        """Test TaskStatus inherits from str."""
        assert isinstance(TaskStatus.PENDING, str)
        assert isinstance(TaskStatus.COMPLETED, str)

    def test_task_status_string_comparison(self) -> None:
        """Test TaskStatus can be compared to strings."""
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"

    def test_task_status_from_string(self) -> None:
        """Test creating TaskStatus from string value."""
        assert TaskStatus("pending") == TaskStatus.PENDING
        assert TaskStatus("in_progress") == TaskStatus.IN_PROGRESS
        assert TaskStatus("completed") == TaskStatus.COMPLETED
        assert TaskStatus("failed") == TaskStatus.FAILED
        assert TaskStatus("skipped") == TaskStatus.SKIPPED

    def test_task_status_from_string_case_sensitive(self) -> None:
        """Test TaskStatus string conversion is case-sensitive."""
        with pytest.raises(ValueError):
            TaskStatus("Pending")  # Capital P

        with pytest.raises(ValueError):
            TaskStatus("COMPLETED")  # All caps

    def test_task_status_invalid_value_raises(self) -> None:
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            TaskStatus("invalid")

        with pytest.raises(ValueError):
            TaskStatus("running")

    def test_task_status_iteration(self) -> None:
        """Test TaskStatus is iterable."""
        statuses = list(TaskStatus)

        assert len(statuses) == 5
        assert TaskStatus.PENDING in statuses
        assert TaskStatus.IN_PROGRESS in statuses
        assert TaskStatus.COMPLETED in statuses
        assert TaskStatus.FAILED in statuses
        assert TaskStatus.SKIPPED in statuses

    def test_task_status_membership(self) -> None:
        """Test TaskStatus membership checks."""
        assert TaskStatus.PENDING in TaskStatus
        assert TaskStatus.COMPLETED in TaskStatus

    def test_task_status_name_attribute(self) -> None:
        """Test TaskStatus has name attribute."""
        assert TaskStatus.PENDING.name == "PENDING"
        assert TaskStatus.COMPLETED.name == "COMPLETED"
        assert TaskStatus.IN_PROGRESS.name == "IN_PROGRESS"

    def test_task_status_all_members(self) -> None:
        """Test all TaskStatus members are present."""
        expected_statuses = {"pending", "in_progress", "completed", "failed", "skipped"}
        actual_statuses = {status.value for status in TaskStatus}

        assert actual_statuses == expected_statuses

    def test_task_status_used_in_conditional(self) -> None:
        """Test TaskStatus can be used in conditionals."""
        status = TaskStatus.PENDING

        is_pending = status == TaskStatus.PENDING

        assert is_pending is True

    def test_task_status_unique_values(self) -> None:
        """Test each TaskStatus has unique value."""
        values = [status.value for status in TaskStatus]

        assert len(values) == len(set(values))


# =============================================================================
# ChangeType Tests
# =============================================================================


class TestChangeType:
    """Tests for ChangeType enum."""

    def test_change_type_added_value(self) -> None:
        """Test ChangeType.ADDED has correct value."""
        assert ChangeType.ADDED.value == "added"

    def test_change_type_modified_value(self) -> None:
        """Test ChangeType.MODIFIED has correct value."""
        assert ChangeType.MODIFIED.value == "modified"

    def test_change_type_deleted_value(self) -> None:
        """Test ChangeType.DELETED has correct value."""
        assert ChangeType.DELETED.value == "deleted"

    def test_change_type_renamed_value(self) -> None:
        """Test ChangeType.RENAMED has correct value."""
        assert ChangeType.RENAMED.value == "renamed"

    def test_change_type_is_string_enum(self) -> None:
        """Test ChangeType inherits from str."""
        assert isinstance(ChangeType.ADDED, str)
        assert isinstance(ChangeType.MODIFIED, str)

    def test_change_type_string_comparison(self) -> None:
        """Test ChangeType can be compared to strings."""
        assert ChangeType.ADDED == "added"
        assert ChangeType.MODIFIED == "modified"
        assert ChangeType.DELETED == "deleted"
        assert ChangeType.RENAMED == "renamed"

    def test_change_type_from_string(self) -> None:
        """Test creating ChangeType from string value."""
        assert ChangeType("added") == ChangeType.ADDED
        assert ChangeType("modified") == ChangeType.MODIFIED
        assert ChangeType("deleted") == ChangeType.DELETED
        assert ChangeType("renamed") == ChangeType.RENAMED

    def test_change_type_from_string_case_sensitive(self) -> None:
        """Test ChangeType string conversion is case-sensitive."""
        with pytest.raises(ValueError):
            ChangeType("Added")  # Capital A

        with pytest.raises(ValueError):
            ChangeType("MODIFIED")  # All caps

    def test_change_type_invalid_value_raises(self) -> None:
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            ChangeType("invalid")

        with pytest.raises(ValueError):
            ChangeType("updated")

    def test_change_type_iteration(self) -> None:
        """Test ChangeType is iterable."""
        changes = list(ChangeType)

        assert len(changes) == 4
        assert ChangeType.ADDED in changes
        assert ChangeType.MODIFIED in changes
        assert ChangeType.DELETED in changes
        assert ChangeType.RENAMED in changes

    def test_change_type_membership(self) -> None:
        """Test ChangeType membership checks."""
        assert ChangeType.ADDED in ChangeType
        assert ChangeType.DELETED in ChangeType

    def test_change_type_name_attribute(self) -> None:
        """Test ChangeType has name attribute."""
        assert ChangeType.ADDED.name == "ADDED"
        assert ChangeType.MODIFIED.name == "MODIFIED"
        assert ChangeType.DELETED.name == "DELETED"
        assert ChangeType.RENAMED.name == "RENAMED"

    def test_change_type_all_members(self) -> None:
        """Test all ChangeType members are present."""
        expected_types = {"added", "modified", "deleted", "renamed"}
        actual_types = {change.value for change in ChangeType}

        assert actual_types == expected_types

    def test_change_type_unique_values(self) -> None:
        """Test each ChangeType has unique value."""
        values = [change.value for change in ChangeType]

        assert len(values) == len(set(values))


# =============================================================================
# ValidationStep Tests
# =============================================================================


class TestValidationStep:
    """Tests for ValidationStep enum."""

    def test_validation_step_format_value(self) -> None:
        """Test ValidationStep.FORMAT has correct value."""
        assert ValidationStep.FORMAT.value == "format"

    def test_validation_step_lint_value(self) -> None:
        """Test ValidationStep.LINT has correct value."""
        assert ValidationStep.LINT.value == "lint"

    def test_validation_step_typecheck_value(self) -> None:
        """Test ValidationStep.TYPECHECK has correct value."""
        assert ValidationStep.TYPECHECK.value == "typecheck"

    def test_validation_step_test_value(self) -> None:
        """Test ValidationStep.TEST has correct value."""
        assert ValidationStep.TEST.value == "test"

    def test_validation_step_is_string_enum(self) -> None:
        """Test ValidationStep inherits from str."""
        assert isinstance(ValidationStep.FORMAT, str)
        assert isinstance(ValidationStep.TEST, str)

    def test_validation_step_string_comparison(self) -> None:
        """Test ValidationStep can be compared to strings."""
        assert ValidationStep.FORMAT == "format"
        assert ValidationStep.LINT == "lint"
        assert ValidationStep.TYPECHECK == "typecheck"
        assert ValidationStep.TEST == "test"

    def test_validation_step_from_string(self) -> None:
        """Test creating ValidationStep from string value."""
        assert ValidationStep("format") == ValidationStep.FORMAT
        assert ValidationStep("lint") == ValidationStep.LINT
        assert ValidationStep("typecheck") == ValidationStep.TYPECHECK
        assert ValidationStep("test") == ValidationStep.TEST

    def test_validation_step_from_string_case_sensitive(self) -> None:
        """Test ValidationStep string conversion is case-sensitive."""
        with pytest.raises(ValueError):
            ValidationStep("Format")  # Capital F

        with pytest.raises(ValueError):
            ValidationStep("LINT")  # All caps

    def test_validation_step_invalid_value_raises(self) -> None:
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            ValidationStep("invalid")

        with pytest.raises(ValueError):
            ValidationStep("type-check")  # Wrong format

    def test_validation_step_iteration(self) -> None:
        """Test ValidationStep is iterable."""
        steps = list(ValidationStep)

        assert len(steps) == 4
        assert ValidationStep.FORMAT in steps
        assert ValidationStep.LINT in steps
        assert ValidationStep.TYPECHECK in steps
        assert ValidationStep.TEST in steps

    def test_validation_step_membership(self) -> None:
        """Test ValidationStep membership checks."""
        assert ValidationStep.FORMAT in ValidationStep
        assert ValidationStep.TEST in ValidationStep

    def test_validation_step_name_attribute(self) -> None:
        """Test ValidationStep has name attribute."""
        assert ValidationStep.FORMAT.name == "FORMAT"
        assert ValidationStep.LINT.name == "LINT"
        assert ValidationStep.TYPECHECK.name == "TYPECHECK"
        assert ValidationStep.TEST.name == "TEST"

    def test_validation_step_all_members(self) -> None:
        """Test all ValidationStep members are present."""
        expected_steps = {"format", "lint", "typecheck", "test"}
        actual_steps = {step.value for step in ValidationStep}

        assert actual_steps == expected_steps

    def test_validation_step_unique_values(self) -> None:
        """Test each ValidationStep has unique value."""
        values = [step.value for step in ValidationStep]

        assert len(values) == len(set(values))


# =============================================================================
# Enum Comparison Tests
# =============================================================================


class TestEnumComparisons:
    """Tests for comparing different enums."""

    def test_different_enums_not_equal(self) -> None:
        """Test comparing enum values from different enums."""
        # Different enums should not be equal
        assert TaskStatus.PENDING != ChangeType.ADDED
        assert ValidationStep.FORMAT != TaskStatus.PENDING

    def test_same_value_different_enums_not_equal(self) -> None:
        """Test enums with same string value are not equal."""
        # Even if values look similar, they're different enums
        task_completed = TaskStatus.COMPLETED
        validation_test = ValidationStep.TEST

        # Different enum types
        assert type(task_completed) is not type(validation_test)

    def test_enum_sorting(self) -> None:
        """Test enums can be sorted by value."""
        statuses = [
            TaskStatus.SKIPPED,
            TaskStatus.PENDING,
            TaskStatus.COMPLETED,
        ]

        # Sort by string value
        sorted_statuses = sorted(statuses, key=lambda x: x.value)

        assert sorted_statuses[0] == TaskStatus.COMPLETED
        assert sorted_statuses[1] == TaskStatus.PENDING


# =============================================================================
# Enum Serialization Tests
# =============================================================================


class TestEnumSerialization:
    """Tests for enum serialization."""

    def test_task_status_str(self) -> None:
        """Test TaskStatus string representation via .value."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.COMPLETED.value == "completed"

    def test_change_type_str(self) -> None:
        """Test ChangeType string representation via .value."""
        assert ChangeType.ADDED.value == "added"
        assert ChangeType.MODIFIED.value == "modified"

    def test_validation_step_str(self) -> None:
        """Test ValidationStep string representation via .value."""
        assert ValidationStep.FORMAT.value == "format"
        assert ValidationStep.LINT.value == "lint"

    def test_enum_format_with_f_string(self) -> None:
        """Test enum value can be used in f-strings."""
        status = TaskStatus.PENDING

        result = f"Status: {status.value}"

        assert result == "Status: pending"

    def test_enum_in_dict_keys(self) -> None:
        """Test enums can be used as dictionary keys."""
        status_counts = {
            TaskStatus.PENDING: 5,
            TaskStatus.COMPLETED: 3,
            TaskStatus.FAILED: 1,
        }

        assert status_counts[TaskStatus.PENDING] == 5
        assert status_counts[TaskStatus.COMPLETED] == 3

    def test_enum_in_list(self) -> None:
        """Test enums can be used in lists."""
        pipeline = [
            ValidationStep.FORMAT,
            ValidationStep.LINT,
            ValidationStep.TYPECHECK,
            ValidationStep.TEST,
        ]

        assert len(pipeline) == 4
        assert pipeline[0] == ValidationStep.FORMAT


# =============================================================================
# Enum Hashing Tests
# =============================================================================


class TestEnumHashing:
    """Tests for enum hashing and equality."""

    def test_enum_hashable(self) -> None:
        """Test enums are hashable."""
        status_set = {TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.PENDING}

        # Should deduplicate
        assert len(status_set) == 2

    def test_enum_identity(self) -> None:
        """Test enum members are singletons."""
        status1 = TaskStatus.PENDING
        status2 = TaskStatus.PENDING

        # Should be same object
        assert status1 is status2

    def test_enum_equality_reflexive(self) -> None:
        """Test enum equality is reflexive."""
        status = TaskStatus.PENDING

        assert status == status

    def test_enum_equality_symmetric(self) -> None:
        """Test enum equality is symmetric."""
        status = TaskStatus.PENDING

        assert status == TaskStatus("pending")
        assert TaskStatus("pending") == status
