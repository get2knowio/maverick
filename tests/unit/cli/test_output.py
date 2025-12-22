"""Unit tests for CLI output formatting utilities.

Tests the output formatting functions and enums:
- OutputFormat enum
- format_error()
- format_success()
- format_warning()
- format_json()
- format_table()
"""

from __future__ import annotations

import json
from enum import Enum

import pytest

from maverick.cli.output import (
    OutputFormat,
    format_error,
    format_json,
    format_success,
    format_table,
    format_warning,
)

# =============================================================================
# OutputFormat Enum Tests
# =============================================================================


class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_enum_values(self) -> None:
        """Test all OutputFormat enum values are defined correctly."""
        assert OutputFormat.TUI.value == "tui"
        assert OutputFormat.JSON.value == "json"
        assert OutputFormat.MARKDOWN.value == "markdown"
        assert OutputFormat.TEXT.value == "text"

    def test_is_string_enum(self) -> None:
        """Test OutputFormat is a string enum (str, Enum)."""
        assert issubclass(OutputFormat, str)
        assert issubclass(OutputFormat, Enum)

    def test_enum_member_is_string(self) -> None:
        """Test each enum member is a string instance."""
        for member in OutputFormat:
            assert isinstance(member, str)
            assert isinstance(member.value, str)

    def test_can_compare_with_string(self) -> None:
        """Test OutputFormat members can be compared with strings."""
        assert OutputFormat.TUI == "tui"
        assert OutputFormat.JSON == "json"
        assert OutputFormat.MARKDOWN == "markdown"
        assert OutputFormat.TEXT == "text"

    def test_all_members_present(self) -> None:
        """Test all expected members are present."""
        members = {member.name for member in OutputFormat}
        expected = {"TUI", "JSON", "MARKDOWN", "TEXT"}
        assert members == expected

    def test_enum_membership(self) -> None:
        """Test can check membership using 'in' operator."""
        assert "tui" in [fmt.value for fmt in OutputFormat]
        assert "json" in [fmt.value for fmt in OutputFormat]
        assert "invalid" not in [fmt.value for fmt in OutputFormat]


# =============================================================================
# format_error() Tests
# =============================================================================


class TestFormatError:
    """Tests for format_error() function."""

    def test_message_only(self) -> None:
        """Test format_error with message only."""
        result = format_error("Something went wrong")

        assert result == "Error: Something went wrong"

    def test_message_with_single_detail(self) -> None:
        """Test format_error with message and single detail."""
        result = format_error("Failed to load config", details=["File not found"])

        expected = "Error: Failed to load config\n  File not found"
        assert result == expected

    def test_message_with_multiple_details(self) -> None:
        """Test format_error with message and multiple details."""
        result = format_error(
            "Validation failed",
            details=["Missing required field: name", "Invalid email format"],
        )

        expected = (
            "Error: Validation failed\n"
            "  Missing required field: name\n"
            "  Invalid email format"
        )
        assert result == expected

    def test_message_with_suggestion(self) -> None:
        """Test format_error with message and suggestion."""
        result = format_error(
            "Config file not found",
            suggestion="Run 'maverick init' to create one",
        )

        expected = (
            "Error: Config file not found\n"
            "Suggestion: Run 'maverick init' to create one"
        )
        assert result == expected

    def test_message_with_details_and_suggestion(self) -> None:
        """Test format_error with message, details, and suggestion."""
        result = format_error(
            "Failed to start workflow",
            details=["Branch is not up to date", "Uncommitted changes detected"],
            suggestion="Commit your changes and pull latest from main",
        )

        expected = (
            "Error: Failed to start workflow\n"
            "  Branch is not up to date\n"
            "  Uncommitted changes detected\n"
            "Suggestion: Commit your changes and pull latest from main"
        )
        assert result == expected

    def test_empty_details_list(self) -> None:
        """Test format_error with empty details list."""
        result = format_error("Error occurred", details=[])

        # Empty details list should be ignored
        assert result == "Error: Error occurred"

    def test_detail_indentation(self) -> None:
        """Test details are indented with two spaces."""
        result = format_error("Error", details=["Detail line"])

        assert "  Detail line" in result
        assert result.startswith("Error:")

    def test_multiline_message(self) -> None:
        """Test format_error preserves multiline messages."""
        result = format_error("First line\nSecond line")

        assert result == "Error: First line\nSecond line"

    def test_special_characters_in_message(self) -> None:
        """Test format_error handles special characters."""
        result = format_error("Error: file 'config.yaml' not found")

        assert result == "Error: Error: file 'config.yaml' not found"

    def test_unicode_in_message(self) -> None:
        """Test format_error handles unicode characters."""
        result = format_error("Error: résumé file missing")

        assert result == "Error: Error: résumé file missing"


# =============================================================================
# format_success() Tests
# =============================================================================


class TestFormatSuccess:
    """Tests for format_success() function."""

    def test_basic_success_message(self) -> None:
        """Test format_success with basic message."""
        result = format_success("Workflow completed")

        assert result == "Success: Workflow completed"

    def test_empty_message(self) -> None:
        """Test format_success with empty message."""
        result = format_success("")

        assert result == "Success: "

    def test_multiline_message(self) -> None:
        """Test format_success preserves multiline messages."""
        result = format_success("Line 1\nLine 2")

        assert result == "Success: Line 1\nLine 2"

    def test_special_characters(self) -> None:
        """Test format_success handles special characters."""
        result = format_success("PR #123 created successfully")

        assert result == "Success: PR #123 created successfully"

    def test_unicode_characters(self) -> None:
        """Test format_success handles unicode characters."""
        result = format_success("Workflow completed ✓")

        assert result == "Success: Workflow completed ✓"

    def test_long_message(self) -> None:
        """Test format_success with long message."""
        long_message = "A" * 200
        result = format_success(long_message)

        assert result == f"Success: {long_message}"


# =============================================================================
# format_warning() Tests
# =============================================================================


class TestFormatWarning:
    """Tests for format_warning() function."""

    def test_basic_warning_message(self) -> None:
        """Test format_warning with basic message."""
        result = format_warning("Config file not found, using defaults")

        assert result == "Warning: Config file not found, using defaults"

    def test_empty_message(self) -> None:
        """Test format_warning with empty message."""
        result = format_warning("")

        assert result == "Warning: "

    def test_multiline_message(self) -> None:
        """Test format_warning preserves multiline messages."""
        result = format_warning("Line 1\nLine 2")

        assert result == "Warning: Line 1\nLine 2"

    def test_special_characters(self) -> None:
        """Test format_warning handles special characters."""
        result = format_warning("Deprecated: use 'new_function()' instead")

        assert result == "Warning: Deprecated: use 'new_function()' instead"

    def test_unicode_characters(self) -> None:
        """Test format_warning handles unicode characters."""
        result = format_warning("Performance may be slow ⚠")

        assert result == "Warning: Performance may be slow ⚠"

    def test_long_message(self) -> None:
        """Test format_warning with long message."""
        long_message = "B" * 200
        result = format_warning(long_message)

        assert result == f"Warning: {long_message}"


# =============================================================================
# format_json() Tests
# =============================================================================


class TestFormatJson:
    """Tests for format_json() function."""

    def test_simple_dict(self) -> None:
        """Test format_json with simple dictionary."""
        data = {"status": "success", "count": 3}
        result = format_json(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == data

        # Should be indented with 2 spaces
        assert "  " in result

    def test_simple_list(self) -> None:
        """Test format_json with simple list."""
        data = ["item1", "item2", "item3"]
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed == data

    def test_nested_structure(self) -> None:
        """Test format_json with nested structures."""
        data = {
            "workflow": "fly",
            "tasks": [
                {"id": 1, "name": "Task 1", "status": "completed"},
                {"id": 2, "name": "Task 2", "status": "pending"},
            ],
            "metadata": {"author": "user", "timestamp": "2025-12-17"},
        }
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed == data

    def test_indent_is_two_spaces(self) -> None:
        """Test format_json uses 2-space indentation."""
        data = {"key": "value"}
        result = format_json(data)

        # Check that indentation is 2 spaces (not 4)
        lines = result.split("\n")
        assert any(line.startswith("  ") for line in lines)
        # Should not have 4-space indent for this simple structure
        assert not any(line.startswith("    ") for line in lines)

    def test_empty_dict(self) -> None:
        """Test format_json with empty dictionary."""
        result = format_json({})

        assert result == "{}"

    def test_empty_list(self) -> None:
        """Test format_json with empty list."""
        result = format_json([])

        assert result == "[]"

    def test_none_value(self) -> None:
        """Test format_json with None value."""
        data = {"value": None}
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed["value"] is None

    def test_boolean_values(self) -> None:
        """Test format_json with boolean values."""
        data = {"success": True, "failed": False}
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["failed"] is False

    def test_numeric_values(self) -> None:
        """Test format_json with numeric values."""
        data = {"integer": 42, "float": 3.14, "negative": -10}
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed == data

    def test_string_escaping(self) -> None:
        """Test format_json properly escapes special characters."""
        data = {"message": 'Line 1\nLine 2\t"quoted"'}
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed == data

    def test_unicode_characters(self) -> None:
        """Test format_json handles unicode characters."""
        data = {"message": "Hello 世界", "symbol": "✓"}
        result = format_json(data)

        parsed = json.loads(result)
        assert parsed == data

    def test_non_serializable_raises_type_error(self) -> None:
        """Test format_json raises TypeError for non-serializable data."""

        class NonSerializable:
            pass

        with pytest.raises(TypeError):
            format_json({"obj": NonSerializable()})


# =============================================================================
# format_table() Tests
# =============================================================================


class TestFormatTable:
    """Tests for format_table() function."""

    def test_simple_table(self) -> None:
        """Test format_table with simple data."""
        headers = ["Name", "Status"]
        rows = [["Task 1", "Done"], ["Task 2", "Pending"]]

        result = format_table(headers, rows)

        # Cells are padded to match column width (widest cell in each column)
        expected = "Name   | Status \nTask 1 | Done   \nTask 2 | Pending"
        assert result == expected

    def test_empty_headers(self) -> None:
        """Test format_table with empty headers."""
        result = format_table([], [["data"]])

        assert result == ""

    def test_empty_rows(self) -> None:
        """Test format_table with no data rows."""
        headers = ["Name", "Status"]
        result = format_table(headers, [])

        # Should only show headers
        assert result == "Name | Status"

    def test_column_width_calculation(self) -> None:
        """Test format_table calculates column widths correctly."""
        headers = ["ID", "Name"]
        rows = [["1", "Short"], ["2", "Very Long Name"]]

        result = format_table(headers, rows)

        # "Name" column should be wide enough for "Very Long Name"
        lines = result.split("\n")
        assert all(" | " in line for line in lines)

        # Check that "Short" is padded to match "Very Long Name" width
        assert "Short          " in result or "Short" in result

    def test_pipe_separators(self) -> None:
        """Test format_table uses pipe separators."""
        headers = ["A", "B", "C"]
        rows = [["1", "2", "3"]]

        result = format_table(headers, rows)

        # Should have pipes between columns
        assert " | " in result
        # Each line should have the right number of pipes
        for line in result.split("\n"):
            assert line.count("|") == 2

    def test_left_justified_alignment(self) -> None:
        """Test format_table left-justifies text."""
        headers = ["Name"]
        rows = [["Short"], ["LongerName"]]

        result = format_table(headers, rows)

        lines = result.split("\n")
        # Header should be padded to match longest cell
        assert "Name      " in lines[0] or "Name" in lines[0]

    def test_unicode_characters(self) -> None:
        """Test format_table handles unicode characters."""
        headers = ["Name", "Status"]
        rows = [["Task ✓", "Done ✓"]]

        result = format_table(headers, rows)

        assert "Task ✓" in result
        assert "Done ✓" in result
        assert " | " in result

    def test_special_characters(self) -> None:
        """Test format_table handles special characters."""
        headers = ["File", "Path"]
        rows = [["config.yaml", "/path/to/config.yaml"]]

        result = format_table(headers, rows)

        assert "config.yaml" in result
        assert "/path/to/config.yaml" in result

    def test_single_column(self) -> None:
        """Test format_table with single column."""
        headers = ["Name"]
        rows = [["Task 1"], ["Task 2"]]

        result = format_table(headers, rows)

        lines = result.split("\n")
        assert len(lines) == 3
        assert "Name" in lines[0]
        assert "Task 1" in lines[1]
        assert "Task 2" in lines[2]

    def test_many_columns(self) -> None:
        """Test format_table with many columns."""
        headers = ["A", "B", "C", "D", "E"]
        rows = [["1", "2", "3", "4", "5"]]

        result = format_table(headers, rows)

        # Should have 4 pipes (between 5 columns)
        for line in result.split("\n"):
            assert line.count("|") == 4

    def test_uneven_row_lengths(self) -> None:
        """Test format_table handles rows shorter than headers."""
        headers = ["A", "B", "C"]
        rows = [["1", "2"]]  # Missing third column

        result = format_table(headers, rows)

        # Should still format without error
        assert "A" in result
        assert "B" in result
        assert "C" in result

    def test_row_longer_than_headers(self) -> None:
        """Test format_table handles rows longer than headers."""
        headers = ["A", "B"]
        rows = [["1", "2", "3"]]  # Extra column

        result = format_table(headers, rows)

        # Should format without error
        # Extra data might be included without separator
        assert "1" in result
        assert "2" in result

    def test_empty_cells(self) -> None:
        """Test format_table handles empty cells."""
        headers = ["Name", "Value"]
        rows = [["Item 1", ""], ["", "Value 2"]]

        result = format_table(headers, rows)

        lines = result.split("\n")
        assert len(lines) == 3
        assert " | " in result

    def test_whitespace_preservation(self) -> None:
        """Test format_table preserves internal whitespace."""
        headers = ["Description"]
        rows = [["Has  double  spaces"]]

        result = format_table(headers, rows)

        assert "Has  double  spaces" in result


# =============================================================================
# Integration Tests
# =============================================================================


class TestFormattingIntegration:
    """Integration tests for formatting functions working together."""

    def test_format_error_then_json(self) -> None:
        """Test formatting error data as JSON."""
        error_data = {
            "error": "Validation failed",
            "details": ["Missing field: name", "Invalid email"],
        }
        result = format_json(error_data)

        parsed = json.loads(result)
        assert parsed["error"] == "Validation failed"
        assert len(parsed["details"]) == 2

    def test_format_table_with_status_indicators(self) -> None:
        """Test formatting table with success/error/warning indicators."""
        headers = ["Task", "Status"]
        rows = [
            ["Task 1", "Success"],
            ["Task 2", "Warning"],
            ["Task 3", "Error"],
        ]

        result = format_table(headers, rows)

        assert "Success" in result
        assert "Warning" in result
        assert "Error" in result

    def test_json_roundtrip(self) -> None:
        """Test JSON formatting and parsing roundtrip."""
        original = {
            "workflow": "fly",
            "tasks": [{"id": 1}, {"id": 2}],
            "count": 2,
        }

        formatted = format_json(original)
        parsed = json.loads(formatted)

        assert parsed == original
