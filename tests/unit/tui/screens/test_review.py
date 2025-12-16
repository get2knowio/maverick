"""Unit tests for ReviewScreen."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maverick.tui.screens.review import ReviewScreen


# =============================================================================
# ReviewScreen Initialization Tests
# =============================================================================


class TestReviewScreenInitialization:
    """Tests for ReviewScreen initialization."""

    def test_initialization_with_defaults(self) -> None:
        """Test screen creation with default parameters."""
        screen = ReviewScreen()
        assert screen.TITLE == "Review"
        assert screen._issues == []
        assert screen._selected_index == 0
        assert screen._filter_severity is None

    def test_initialization_with_custom_parameters(self) -> None:
        """Test screen creation with custom parameters."""
        screen = ReviewScreen(name="custom-review", id="review-1", classes="custom")
        assert screen.name == "custom-review"
        assert screen.id == "review-1"


# =============================================================================
# ReviewScreen Load Issues Tests
# =============================================================================


class TestReviewScreenLoadIssues:
    """Tests for load_issues method."""

    def test_load_issues_with_empty_list(self) -> None:
        """Test loading an empty list of issues."""
        screen = ReviewScreen()
        mock_issue_list = MagicMock()
        mock_detail = MagicMock()

        with patch.object(screen, "query_one") as mock_query:
            mock_query.return_value = mock_issue_list
            screen.load_issues([])

        assert screen._issues == []
        assert screen._selected_index == -1

    def test_load_issues_with_single_issue(self) -> None:
        """Test loading a single issue."""
        screen = ReviewScreen()
        issues = [
            {
                "file_path": "test.py",
                "line_number": 10,
                "severity": "error",
                "message": "Undefined variable",
                "source": "pylint",
            }
        ]

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.load_issues(issues)

        assert screen._issues == issues
        assert screen._selected_index == 0

    def test_load_issues_with_multiple_issues(self) -> None:
        """Test loading multiple issues."""
        screen = ReviewScreen()
        issues = [
            {
                "file_path": "file1.py",
                "line_number": 5,
                "severity": "error",
                "message": "Error 1",
                "source": "pylint",
            },
            {
                "file_path": "file2.py",
                "line_number": 15,
                "severity": "warning",
                "message": "Warning 1",
                "source": "mypy",
            },
            {
                "file_path": "file3.py",
                "line_number": 25,
                "severity": "info",
                "message": "Info 1",
                "source": "ruff",
            },
        ]

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.load_issues(issues)

        assert screen._issues == issues
        assert screen._selected_index == 0


# =============================================================================
# ReviewScreen Filter Tests
# =============================================================================


class TestReviewScreenFilterBySeverity:
    """Tests for filter_by_severity method."""

    def test_filter_by_severity_errors_only(self) -> None:
        """Test filtering to show only errors."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
            {"severity": "error", "message": "Error 2"},
        ]
        screen._issues = issues

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.filter_by_severity("error")

        assert screen._filter_severity == "error"
        assert screen._selected_index == 0

    def test_filter_by_severity_warnings_only(self) -> None:
        """Test filtering to show only warnings."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
            {"severity": "warning", "message": "Warning 2"},
        ]
        screen._issues = issues

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.filter_by_severity("warning")

        assert screen._filter_severity == "warning"

    def test_filter_by_severity_clear_filter(self) -> None:
        """Test clearing the filter to show all issues."""
        screen = ReviewScreen()
        screen._filter_severity = "error"
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
        ]
        screen._issues = issues

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.filter_by_severity(None)

        assert screen._filter_severity is None

    def test_filter_by_severity_no_matches(self) -> None:
        """Test filtering when no issues match the severity."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "error", "message": "Error 2"},
        ]
        screen._issues = issues

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_clear_detail_view"
        ):
            screen.filter_by_severity("warning")

        assert screen._filter_severity == "warning"


# =============================================================================
# ReviewScreen Navigation Tests
# =============================================================================


class TestReviewScreenNavigateToIssue:
    """Tests for navigate_to_issue method."""

    def test_navigate_to_valid_index(self) -> None:
        """Test navigating to a valid issue index."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
            {"severity": "info", "message": "Info 1"},
        ]
        screen._issues = issues

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.navigate_to_issue(1)

        assert screen._selected_index == 1

    def test_navigate_to_first_issue(self) -> None:
        """Test navigating to the first issue."""
        screen = ReviewScreen()
        issues = [{"severity": "error", "message": "Error 1"}]
        screen._issues = issues

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.navigate_to_issue(0)

        assert screen._selected_index == 0

    def test_navigate_to_invalid_index_negative(self) -> None:
        """Test navigating to an invalid negative index."""
        screen = ReviewScreen()
        screen._issues = [{"severity": "error", "message": "Error 1"}]
        screen._selected_index = 0

        with patch.object(screen, "_update_issue_list") as mock_update_list:
            screen.navigate_to_issue(-1)

        # Should not update if index is invalid
        mock_update_list.assert_not_called()
        assert screen._selected_index == 0

    def test_navigate_to_invalid_index_too_large(self) -> None:
        """Test navigating to an index beyond the list."""
        screen = ReviewScreen()
        screen._issues = [{"severity": "error", "message": "Error 1"}]
        screen._selected_index = 0

        with patch.object(screen, "_update_issue_list") as mock_update_list:
            screen.navigate_to_issue(10)

        # Should not update if index is invalid
        mock_update_list.assert_not_called()
        assert screen._selected_index == 0


# =============================================================================
# ReviewScreen Actions Tests
# =============================================================================


class TestReviewScreenActions:
    """Tests for ReviewScreen action methods."""

    def test_action_next_issue(self) -> None:
        """Test moving to the next issue."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
            {"severity": "info", "message": "Info 1"},
        ]
        screen._issues = issues
        screen._selected_index = 0

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.action_next_issue()

        assert screen._selected_index == 1

    def test_action_next_issue_at_end(self) -> None:
        """Test that next issue doesn't go beyond the last issue."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
        ]
        screen._issues = issues
        screen._selected_index = 1

        with patch.object(screen, "_update_issue_list") as mock_update:
            screen.action_next_issue()

        # Should not advance beyond last issue
        mock_update.assert_not_called()
        assert screen._selected_index == 1

    def test_action_prev_issue(self) -> None:
        """Test moving to the previous issue."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
        ]
        screen._issues = issues
        screen._selected_index = 1

        with patch.object(screen, "_update_issue_list"), patch.object(
            screen, "_update_detail_view"
        ):
            screen.action_prev_issue()

        assert screen._selected_index == 0

    def test_action_prev_issue_at_start(self) -> None:
        """Test that prev issue doesn't go below zero."""
        screen = ReviewScreen()
        issues = [{"severity": "error", "message": "Error 1"}]
        screen._issues = issues
        screen._selected_index = 0

        with patch.object(screen, "_update_issue_list") as mock_update:
            screen.action_prev_issue()

        # Should not go below 0
        mock_update.assert_not_called()
        assert screen._selected_index == 0

    def test_action_filter_errors(self) -> None:
        """Test filtering to show only errors."""
        screen = ReviewScreen()
        screen._issues = [{"severity": "error", "message": "Error 1"}]

        with patch.object(screen, "filter_by_severity") as mock_filter:
            screen.action_filter_errors()

        mock_filter.assert_called_once_with("error")

    def test_action_filter_warnings(self) -> None:
        """Test filtering to show only warnings."""
        screen = ReviewScreen()
        screen._issues = [{"severity": "warning", "message": "Warning 1"}]

        with patch.object(screen, "filter_by_severity") as mock_filter:
            screen.action_filter_warnings()

        mock_filter.assert_called_once_with("warning")

    def test_action_filter_all(self) -> None:
        """Test clearing the filter to show all issues."""
        screen = ReviewScreen()

        with patch.object(screen, "filter_by_severity") as mock_filter:
            screen.action_filter_all()

        mock_filter.assert_called_once_with(None)


# =============================================================================
# ReviewScreen Helper Methods Tests
# =============================================================================


class TestReviewScreenHelperMethods:
    """Tests for ReviewScreen private helper methods."""

    def test_get_filtered_issues_no_filter(self) -> None:
        """Test getting issues when no filter is applied."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
        ]
        screen._issues = issues
        screen._filter_severity = None

        filtered = screen._get_filtered_issues()

        assert filtered == issues

    def test_get_filtered_issues_with_filter(self) -> None:
        """Test getting issues filtered by severity."""
        screen = ReviewScreen()
        issues = [
            {"severity": "error", "message": "Error 1"},
            {"severity": "warning", "message": "Warning 1"},
            {"severity": "error", "message": "Error 2"},
        ]
        screen._issues = issues
        screen._filter_severity = "error"

        filtered = screen._get_filtered_issues()

        assert len(filtered) == 2
        assert all(issue["severity"] == "error" for issue in filtered)

    def test_get_severity_icon(self) -> None:
        """Test getting severity icons."""
        screen = ReviewScreen()

        assert screen._get_severity_icon("error") == "✗"
        assert screen._get_severity_icon("warning") == "⚠"
        assert screen._get_severity_icon("info") == "ℹ"
        assert screen._get_severity_icon("suggestion") == "💡"
        assert screen._get_severity_icon("unknown") == "○"
