"""Unit tests for TUI findings models."""

from __future__ import annotations

import pytest

from maverick.tui.models import (
    CodeContext,
    CodeLocation,
    FindingSeverity,
    ReviewFinding,
    ReviewFindingItem,
)


class TestCodeLocation:
    """Tests for CodeLocation dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating CodeLocation with required fields."""
        location = CodeLocation(file_path="src/main.py", line_number=42)

        assert location.file_path == "src/main.py"
        assert location.line_number == 42
        assert location.end_line is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating CodeLocation with all fields."""
        location = CodeLocation(file_path="src/utils.py", line_number=10, end_line=20)

        assert location.file_path == "src/utils.py"
        assert location.line_number == 10
        assert location.end_line == 20

    def test_end_line_defaults_to_none(self) -> None:
        """Test end_line defaults to None."""
        location = CodeLocation(file_path="test.py", line_number=1)
        assert location.end_line is None

    def test_single_line_location(self) -> None:
        """Test single-line location (no end_line)."""
        location = CodeLocation(file_path="src/app.py", line_number=100)
        assert location.line_number == 100
        assert location.end_line is None

    def test_multi_line_location(self) -> None:
        """Test multi-line location with end_line."""
        location = CodeLocation(file_path="src/app.py", line_number=100, end_line=110)
        assert location.line_number == 100
        assert location.end_line == 110

    def test_code_location_is_frozen(self) -> None:
        """Test CodeLocation is immutable (frozen)."""
        location = CodeLocation(file_path="test.py", line_number=1)

        with pytest.raises(Exception):  # FrozenInstanceError
            location.line_number = 2  # type: ignore[misc]


class TestCodeContext:
    """Tests for CodeContext dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating CodeContext with all fields."""
        code = "def foo():\n    pass\n    return 42"
        context = CodeContext(
            file_path="src/main.py",
            start_line=10,
            end_line=12,
            content=code,
            highlight_line=11,
        )

        assert context.file_path == "src/main.py"
        assert context.start_line == 10
        assert context.end_line == 12
        assert context.content == code
        assert context.highlight_line == 11

    def test_multiline_content(self) -> None:
        """Test CodeContext with multi-line content."""
        code = "line1\nline2\nline3"
        context = CodeContext(
            file_path="test.py",
            start_line=1,
            end_line=3,
            content=code,
            highlight_line=2,
        )

        assert context.content == code
        assert context.start_line == 1
        assert context.end_line == 3

    def test_code_context_is_frozen(self) -> None:
        """Test CodeContext is immutable (frozen)."""
        context = CodeContext(
            file_path="test.py",
            start_line=1,
            end_line=1,
            content="code",
            highlight_line=1,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            context.highlight_line = 2  # type: ignore[misc]


class TestReviewFinding:
    """Tests for ReviewFinding dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ReviewFinding with required fields."""
        location = CodeLocation(file_path="src/main.py", line_number=42)
        finding = ReviewFinding(
            id="finding-001",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Undefined variable",
            description="Variable 'x' is used before being defined",
        )

        assert finding.id == "finding-001"
        assert finding.severity == FindingSeverity.ERROR
        assert finding.location == location
        assert finding.title == "Undefined variable"
        assert finding.description == "Variable 'x' is used before being defined"
        assert finding.suggested_fix is None  # default
        assert finding.source == "review"  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ReviewFinding with all fields."""
        location = CodeLocation(file_path="src/app.py", line_number=10)
        finding = ReviewFinding(
            id="finding-002",
            severity=FindingSeverity.WARNING,
            location=location,
            title="Unused variable",
            description="Variable 'temp' is assigned but never used",
            suggested_fix="Remove unused variable 'temp'",
            source="coderabbit",
        )

        assert finding.id == "finding-002"
        assert finding.severity == FindingSeverity.WARNING
        assert finding.location == location
        assert finding.title == "Unused variable"
        assert finding.suggested_fix == "Remove unused variable 'temp'"
        assert finding.source == "coderabbit"

    def test_suggested_fix_defaults_to_none(self) -> None:
        """Test suggested_fix defaults to None."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.SUGGESTION,
            location=location,
            title="Title",
            description="Description",
        )
        assert finding.suggested_fix is None

    def test_source_defaults_to_review(self) -> None:
        """Test source defaults to 'review'."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Title",
            description="Description",
        )
        assert finding.source == "review"

    def test_different_severities(self) -> None:
        """Test ReviewFinding with different severities."""
        location = CodeLocation(file_path="test.py", line_number=1)
        for severity in FindingSeverity:
            finding = ReviewFinding(
                id=f"test-{severity.value}",
                severity=severity,
                location=location,
                title="Test",
                description="Test finding",
            )
            assert finding.severity == severity

    def test_review_finding_is_frozen(self) -> None:
        """Test ReviewFinding is immutable (frozen)."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Title",
            description="Description",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            finding.title = "Modified"  # type: ignore[misc]


class TestReviewFindingItem:
    """Tests for ReviewFindingItem dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ReviewFindingItem with required fields."""
        location = CodeLocation(file_path="src/main.py", line_number=42)
        finding = ReviewFinding(
            id="finding-001",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test finding",
        )
        item = ReviewFindingItem(finding=finding)

        assert item.finding == finding
        assert item.selected is False  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ReviewFindingItem with all fields."""
        location = CodeLocation(file_path="src/main.py", line_number=42)
        finding = ReviewFinding(
            id="finding-001",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test finding",
        )
        item = ReviewFindingItem(finding=finding, selected=True)

        assert item.finding == finding
        assert item.selected is True

    def test_selected_defaults_to_false(self) -> None:
        """Test selected defaults to False."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding)
        assert item.selected is False

    def test_review_finding_item_is_frozen(self) -> None:
        """Test ReviewFindingItem is immutable (frozen)."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding)

        with pytest.raises(Exception):  # FrozenInstanceError
            item.selected = True  # type: ignore[misc]
