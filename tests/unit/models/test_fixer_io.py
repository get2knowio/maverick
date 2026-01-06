"""Unit tests for fixer_io data models.

Tests the data models used for fixer agent I/O:
- FixerInputItem frozen dataclass
- FixerInput frozen dataclass
- FixerOutputItem frozen dataclass
- FixerOutput frozen dataclass with validate_against_input()
"""

from __future__ import annotations

import pytest

from maverick.models.fixer_io import (
    FixerInput,
    FixerInputItem,
    FixerOutput,
    FixerOutputItem,
)

# =============================================================================
# FixerInputItem Tests
# =============================================================================


class TestFixerInputItem:
    """Tests for FixerInputItem frozen dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating FixerInputItem with all fields."""
        item = FixerInputItem(
            finding_id="RS001",
            severity="critical",
            title="SQL injection vulnerability",
            description="User input is directly concatenated into SQL query",
            file_path="src/api/users.py",
            line_range=(87, 92),
            suggested_fix="Use parameterized queries",
            previous_attempts=(
                {
                    "iteration": 1,
                    "outcome": "deferred",
                    "justification": "Need more context",
                },
            ),
        )

        assert item.finding_id == "RS001"
        assert item.severity == "critical"
        assert item.title == "SQL injection vulnerability"
        assert item.description == "User input is directly concatenated into SQL query"
        assert item.file_path == "src/api/users.py"
        assert item.line_range == (87, 92)
        assert item.suggested_fix == "Use parameterized queries"
        assert len(item.previous_attempts) == 1
        assert item.previous_attempts[0]["outcome"] == "deferred"

    def test_creation_with_optional_fields_as_none(self) -> None:
        """Test creating FixerInputItem with optional fields as None."""
        item = FixerInputItem(
            finding_id="RT001",
            severity="major",
            title="Missing error handling",
            description="Function does not handle exceptions",
            file_path=None,
            line_range=None,
            suggested_fix=None,
            previous_attempts=(),
        )

        assert item.finding_id == "RT001"
        assert item.file_path is None
        assert item.line_range is None
        assert item.suggested_fix is None
        assert item.previous_attempts == ()

    def test_to_dict_produces_correct_output(self) -> None:
        """Test to_dict() produces correct dictionary representation."""
        item = FixerInputItem(
            finding_id="RS002",
            severity="minor",
            title="Inconsistent naming",
            description="Variable uses camelCase",
            file_path="src/utils/helpers.py",
            line_range=(42, 42),
            suggested_fix="Rename to user_name",
            previous_attempts=(),
        )

        data = item.to_dict()

        assert data["finding_id"] == "RS002"
        assert data["severity"] == "minor"
        assert data["title"] == "Inconsistent naming"
        assert data["description"] == "Variable uses camelCase"
        assert data["file_path"] == "src/utils/helpers.py"
        assert data["line_range"] == [42, 42]  # Tuple converted to list
        assert data["suggested_fix"] == "Rename to user_name"
        assert data["previous_attempts"] == []

    def test_to_dict_with_none_line_range(self) -> None:
        """Test to_dict() with None line_range."""
        item = FixerInputItem(
            finding_id="RS003",
            severity="major",
            title="General issue",
            description="Not file-specific",
            file_path=None,
            line_range=None,
            suggested_fix=None,
            previous_attempts=(),
        )

        data = item.to_dict()

        assert data["line_range"] is None

    def test_immutability_frozen(self) -> None:
        """Test FixerInputItem is frozen (immutable)."""
        item = FixerInputItem(
            finding_id="RS001",
            severity="critical",
            title="Test",
            description="Test",
            file_path="test.py",
            line_range=(1, 1),
            suggested_fix=None,
            previous_attempts=(),
        )

        with pytest.raises(AttributeError):
            item.severity = "minor"  # type: ignore[misc]


# =============================================================================
# FixerInput Tests
# =============================================================================


class TestFixerInput:
    """Tests for FixerInput frozen dataclass."""

    def test_creation_with_multiple_items(self) -> None:
        """Test creating FixerInput with multiple items."""
        item1 = FixerInputItem(
            finding_id="RS001",
            severity="critical",
            title="Issue 1",
            description="Description 1",
            file_path="file1.py",
            line_range=(10, 15),
            suggested_fix="Fix 1",
            previous_attempts=(),
        )
        item2 = FixerInputItem(
            finding_id="RS002",
            severity="major",
            title="Issue 2",
            description="Description 2",
            file_path="file2.py",
            line_range=(20, 25),
            suggested_fix="Fix 2",
            previous_attempts=(),
        )

        fixer_input = FixerInput(
            iteration=1,
            items=(item1, item2),
            context="Review findings from PR #123",
        )

        assert fixer_input.iteration == 1
        assert len(fixer_input.items) == 2
        assert fixer_input.items[0].finding_id == "RS001"
        assert fixer_input.items[1].finding_id == "RS002"
        assert fixer_input.context == "Review findings from PR #123"

    def test_to_dict_produces_correct_output(self) -> None:
        """Test to_dict() produces correct dictionary."""
        item = FixerInputItem(
            finding_id="RS001",
            severity="critical",
            title="Test issue",
            description="Test description",
            file_path="test.py",
            line_range=(1, 5),
            suggested_fix="Test fix",
            previous_attempts=(),
        )
        fixer_input = FixerInput(
            iteration=2,
            items=(item,),
            context="Context info",
        )

        data = fixer_input.to_dict()

        assert data["iteration"] == 2
        assert len(data["items"]) == 1
        assert data["items"][0]["finding_id"] == "RS001"
        assert data["context"] == "Context info"

    def test_empty_items_tuple(self) -> None:
        """Test FixerInput with empty items tuple."""
        fixer_input = FixerInput(
            iteration=1,
            items=(),
            context="No items to fix",
        )

        assert fixer_input.items == ()
        data = fixer_input.to_dict()
        assert data["items"] == []


# =============================================================================
# FixerOutputItem Tests
# =============================================================================


class TestFixerOutputItem:
    """Tests for FixerOutputItem frozen dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating FixerOutputItem with all fields."""
        item = FixerOutputItem(
            finding_id="RS001",
            status="fixed",
            justification=None,
            changes_made="Updated query to use parameterized format",
        )

        assert item.finding_id == "RS001"
        assert item.status == "fixed"
        assert item.justification is None
        assert item.changes_made == "Updated query to use parameterized format"

    def test_creation_blocked_with_justification(self) -> None:
        """Test creating blocked FixerOutputItem with justification."""
        item = FixerOutputItem(
            finding_id="RS002",
            status="blocked",
            justification="Requires external service modification",
            changes_made=None,
        )

        assert item.status == "blocked"
        assert item.justification == "Requires external service modification"
        assert item.changes_made is None

    def test_creation_deferred_with_justification(self) -> None:
        """Test creating deferred FixerOutputItem with justification."""
        item = FixerOutputItem(
            finding_id="RS003",
            status="deferred",
            justification="Need more context from other files",
            changes_made=None,
        )

        assert item.status == "deferred"
        assert item.justification == "Need more context from other files"

    def test_to_dict_produces_correct_output(self) -> None:
        """Test to_dict() produces correct dictionary."""
        item = FixerOutputItem(
            finding_id="RS001",
            status="fixed",
            justification=None,
            changes_made="Applied fix",
        )

        data = item.to_dict()

        assert data["finding_id"] == "RS001"
        assert data["status"] == "fixed"
        assert data["justification"] is None
        assert data["changes_made"] == "Applied fix"

    def test_immutability_frozen(self) -> None:
        """Test FixerOutputItem is frozen (immutable)."""
        item = FixerOutputItem(
            finding_id="RS001",
            status="fixed",
            justification=None,
            changes_made="Fixed",
        )

        with pytest.raises(AttributeError):
            item.status = "blocked"  # type: ignore[misc]


# =============================================================================
# FixerOutput Tests
# =============================================================================


class TestFixerOutput:
    """Tests for FixerOutput frozen dataclass."""

    def test_creation_with_multiple_items(self) -> None:
        """Test creating FixerOutput with multiple items."""
        item1 = FixerOutputItem(
            finding_id="RS001",
            status="fixed",
            justification=None,
            changes_made="Fixed issue 1",
        )
        item2 = FixerOutputItem(
            finding_id="RS002",
            status="blocked",
            justification="Cannot fix without API changes",
            changes_made=None,
        )

        output = FixerOutput(
            items=(item1, item2),
            summary="Fixed 1, blocked 1",
        )

        assert len(output.items) == 2
        assert output.items[0].finding_id == "RS001"
        assert output.items[1].finding_id == "RS002"
        assert output.summary == "Fixed 1, blocked 1"

    def test_to_dict_produces_correct_output(self) -> None:
        """Test to_dict() produces correct dictionary."""
        item = FixerOutputItem(
            finding_id="RS001",
            status="fixed",
            justification=None,
            changes_made="Applied fix",
        )
        output = FixerOutput(
            items=(item,),
            summary="All fixed",
        )

        data = output.to_dict()

        assert len(data["items"]) == 1
        assert data["items"][0]["finding_id"] == "RS001"
        assert data["summary"] == "All fixed"

    def test_creation_with_none_summary(self) -> None:
        """Test FixerOutput with None summary."""
        item = FixerOutputItem(
            finding_id="RS001",
            status="fixed",
            justification=None,
            changes_made="Fixed",
        )
        output = FixerOutput(
            items=(item,),
            summary=None,
        )

        assert output.summary is None


# =============================================================================
# validate_against_input() Tests
# =============================================================================


class TestValidateAgainstInput:
    """Tests for FixerOutput.validate_against_input() method."""

    @pytest.fixture
    def sample_input(self) -> FixerInput:
        """Create a sample FixerInput for tests."""
        item1 = FixerInputItem(
            finding_id="RS001",
            severity="critical",
            title="Issue 1",
            description="Description 1",
            file_path="file1.py",
            line_range=(10, 15),
            suggested_fix="Fix 1",
            previous_attempts=(),
        )
        item2 = FixerInputItem(
            finding_id="RS002",
            severity="major",
            title="Issue 2",
            description="Description 2",
            file_path="file2.py",
            line_range=(20, 25),
            suggested_fix="Fix 2",
            previous_attempts=(),
        )
        return FixerInput(
            iteration=1,
            items=(item1, item2),
            context="Test context",
        )

    def test_valid_output_all_ids_present(self, sample_input: FixerInput) -> None:
        """Test valid output with all input IDs present returns (True, [])."""
        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed 1",
                ),
                FixerOutputItem(
                    finding_id="RS002",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed 2",
                ),
            ),
            summary="All fixed",
        )

        is_valid, errors = output.validate_against_input(sample_input)

        assert is_valid is True
        assert errors == []

    def test_missing_id_returns_error(self, sample_input: FixerInput) -> None:
        """Test missing ID returns (False, [error message])."""
        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed 1",
                ),
                # RS002 is missing
            ),
            summary="Partial fix",
        )

        is_valid, errors = output.validate_against_input(sample_input)

        assert is_valid is False
        assert len(errors) == 1
        assert "RS002" in errors[0]
        assert "Missing responses" in errors[0]

    def test_invalid_status_returns_error(self, sample_input: FixerInput) -> None:
        """Test invalid status returns (False, [error message])."""
        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="invalid_status",  # Invalid
                    justification=None,
                    changes_made=None,
                ),
                FixerOutputItem(
                    finding_id="RS002",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed 2",
                ),
            ),
            summary="Test",
        )

        is_valid, errors = output.validate_against_input(sample_input)

        assert is_valid is False
        assert len(errors) == 1
        assert "Invalid status" in errors[0]
        assert "RS001" in errors[0]

    def test_blocked_without_justification_returns_error(
        self, sample_input: FixerInput
    ) -> None:
        """Test blocked without justification returns (False, [error message])."""
        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="blocked",
                    justification=None,  # Missing justification
                    changes_made=None,
                ),
                FixerOutputItem(
                    finding_id="RS002",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed 2",
                ),
            ),
            summary="Test",
        )

        is_valid, errors = output.validate_against_input(sample_input)

        assert is_valid is False
        assert len(errors) == 1
        assert "blocked" in errors[0]
        assert "no justification" in errors[0]
        assert "RS001" in errors[0]

    def test_deferred_without_justification_returns_error(
        self, sample_input: FixerInput
    ) -> None:
        """Test deferred without justification returns (False, [error message])."""
        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="deferred",
                    justification=None,  # Missing justification
                    changes_made=None,
                ),
                FixerOutputItem(
                    finding_id="RS002",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed 2",
                ),
            ),
            summary="Test",
        )

        is_valid, errors = output.validate_against_input(sample_input)

        assert is_valid is False
        assert len(errors) == 1
        assert "deferred" in errors[0]
        assert "no justification" in errors[0]

    def test_fixed_without_justification_is_ok(self, sample_input: FixerInput) -> None:
        """Test fixed without justification is OK."""
        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,  # OK for fixed
                    changes_made="Applied fix",
                ),
                FixerOutputItem(
                    finding_id="RS002",
                    status="fixed",
                    justification=None,
                    changes_made="Applied fix",
                ),
            ),
            summary="All fixed",
        )

        is_valid, errors = output.validate_against_input(sample_input)

        assert is_valid is True
        assert errors == []

    def test_multiple_errors_collected(self, sample_input: FixerInput) -> None:
        """Test multiple validation errors are collected."""
        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="invalid",  # Error 1: invalid status
                    justification=None,
                    changes_made=None,
                ),
                # Error 2: RS002 is missing
            ),
            summary="Test",
        )

        is_valid, errors = output.validate_against_input(sample_input)

        assert is_valid is False
        assert len(errors) == 2

    def test_valid_with_all_statuses(self) -> None:
        """Test valid output with all status types (fixed, blocked, deferred)."""
        input_item1 = FixerInputItem(
            finding_id="RS001",
            severity="critical",
            title="Issue 1",
            description="Desc 1",
            file_path="file1.py",
            line_range=None,
            suggested_fix=None,
            previous_attempts=(),
        )
        input_item2 = FixerInputItem(
            finding_id="RS002",
            severity="major",
            title="Issue 2",
            description="Desc 2",
            file_path="file2.py",
            line_range=None,
            suggested_fix=None,
            previous_attempts=(),
        )
        input_item3 = FixerInputItem(
            finding_id="RS003",
            severity="major",
            title="Issue 3",
            description="Desc 3",
            file_path="file3.py",
            line_range=None,
            suggested_fix=None,
            previous_attempts=(),
        )
        fixer_input = FixerInput(
            iteration=1,
            items=(input_item1, input_item2, input_item3),
            context="Test",
        )

        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Applied fix",
                ),
                FixerOutputItem(
                    finding_id="RS002",
                    status="blocked",
                    justification="Cannot fix without external changes",
                    changes_made=None,
                ),
                FixerOutputItem(
                    finding_id="RS003",
                    status="deferred",
                    justification="Need more context",
                    changes_made=None,
                ),
            ),
            summary="Mixed results",
        )

        is_valid, errors = output.validate_against_input(fixer_input)

        assert is_valid is True
        assert errors == []

    def test_empty_input_empty_output_is_valid(self) -> None:
        """Test empty input with empty output is valid."""
        fixer_input = FixerInput(
            iteration=1,
            items=(),
            context="No items",
        )
        output = FixerOutput(
            items=(),
            summary="Nothing to do",
        )

        is_valid, errors = output.validate_against_input(fixer_input)

        assert is_valid is True
        assert errors == []

    def test_extra_output_ids_are_ignored(self) -> None:
        """Test extra output IDs (not in input) are ignored."""
        input_item = FixerInputItem(
            finding_id="RS001",
            severity="critical",
            title="Issue 1",
            description="Desc 1",
            file_path="file1.py",
            line_range=None,
            suggested_fix=None,
            previous_attempts=(),
        )
        fixer_input = FixerInput(
            iteration=1,
            items=(input_item,),
            context="Test",
        )

        output = FixerOutput(
            items=(
                FixerOutputItem(
                    finding_id="RS001",
                    status="fixed",
                    justification=None,
                    changes_made="Fixed",
                ),
                FixerOutputItem(
                    finding_id="EXTRA001",  # Extra ID not in input
                    status="fixed",
                    justification=None,
                    changes_made="Extra fix",
                ),
            ),
            summary="Test",
        )

        is_valid, errors = output.validate_against_input(fixer_input)

        # Extra IDs are ignored - validation only checks that all input IDs are covered
        assert is_valid is True
        assert errors == []
