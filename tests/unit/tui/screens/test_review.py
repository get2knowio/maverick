"""Unit tests for ReviewScreen."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.tui.models import ReviewAction, ReviewScreenActionState
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
        assert isinstance(screen.action_state, ReviewScreenActionState)
        assert screen.has_new_findings is False

    def test_initialization_with_custom_parameters(self) -> None:
        """Test screen creation with custom parameters."""
        screen = ReviewScreen(name="custom-review", id="review-1", classes="custom")
        assert screen.name == "custom-review"
        assert screen.id == "review-1"

    def test_default_action_state(self) -> None:
        """Test that default action state is properly initialized."""
        screen = ReviewScreen()
        assert screen.action_state.pending_action is None
        assert screen.action_state.is_approving is False
        assert screen.action_state.is_fixing is False
        assert screen.action_state.fix_results is None


# =============================================================================
# ReviewScreen Load Issues Tests
# =============================================================================


class TestReviewScreenLoadIssues:
    """Tests for load_issues method."""

    def test_load_issues_with_empty_list(self) -> None:
        """Test loading an empty list of issues."""
        screen = ReviewScreen()
        mock_issue_list = MagicMock()
        MagicMock()

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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_clear_detail_view"),
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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
        ):
            screen.navigate_to_issue(1)

        assert screen._selected_index == 1

    def test_navigate_to_first_issue(self) -> None:
        """Test navigating to the first issue."""
        screen = ReviewScreen()
        issues = [{"severity": "error", "message": "Error 1"}]
        screen._issues = issues

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
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

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
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
# ReviewScreen Review Action Tests (T033-T035)
# =============================================================================


class TestReviewScreenApproveAction:
    """Tests for action_approve method (T033)."""

    @pytest.mark.asyncio
    async def test_action_approve_confirmed(self) -> None:
        """Test approve action when user confirms."""
        screen = ReviewScreen()

        with (
            patch.object(screen, "confirm", new=AsyncMock(return_value=True)),
            patch.object(screen, "_submit_approval") as mock_submit,
        ):
            await screen.action_approve()

        mock_submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_action_approve_cancelled(self) -> None:
        """Test approve action when user cancels."""
        screen = ReviewScreen()

        with (
            patch.object(screen, "confirm", new=AsyncMock(return_value=False)),
            patch.object(screen, "_submit_approval") as mock_submit,
        ):
            await screen.action_approve()

        mock_submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_approve_confirmation_message(self) -> None:
        """Test that approve shows appropriate confirmation message."""
        screen = ReviewScreen()
        mock_confirm = AsyncMock(return_value=False)

        with (
            patch.object(screen, "confirm", new=mock_confirm),
            patch.object(screen, "_submit_approval"),
        ):
            await screen.action_approve()

        mock_confirm.assert_called_once_with(
            "Approve Review", "Are you sure you want to approve this review?"
        )


class TestReviewScreenRequestChangesAction:
    """Tests for action_request_changes method (T033)."""

    @pytest.mark.asyncio
    async def test_action_request_changes_with_comment(self) -> None:
        """Test request changes action when user provides comment."""
        screen = ReviewScreen()
        test_comment = "Please fix the issues"

        with (
            patch.object(
                screen, "prompt_input", new=AsyncMock(return_value=test_comment)
            ),
            patch.object(screen, "_submit_request_changes") as mock_submit,
        ):
            await screen.action_request_changes()

        mock_submit.assert_called_once_with(test_comment)

    @pytest.mark.asyncio
    async def test_action_request_changes_cancelled(self) -> None:
        """Test request changes action when user cancels."""
        screen = ReviewScreen()

        with (
            patch.object(screen, "prompt_input", new=AsyncMock(return_value=None)),
            patch.object(screen, "_submit_request_changes") as mock_submit,
        ):
            await screen.action_request_changes()

        mock_submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_request_changes_empty_comment(self) -> None:
        """Test request changes action when user provides empty comment."""
        screen = ReviewScreen()

        with (
            patch.object(screen, "prompt_input", new=AsyncMock(return_value="")),
            patch.object(screen, "_submit_request_changes") as mock_submit,
        ):
            await screen.action_request_changes()

        mock_submit.assert_not_called()


class TestReviewScreenDismissAction:
    """Tests for action_dismiss method (T034)."""

    @pytest.mark.asyncio
    async def test_action_dismiss_with_selected_issue(self) -> None:
        """Test dismiss action with a selected issue."""
        screen = ReviewScreen()
        issues = [
            {"id": "1", "severity": "error", "message": "Error 1"},
            {"id": "2", "severity": "warning", "message": "Warning 1"},
            {"id": "3", "severity": "info", "message": "Info 1"},
        ]
        screen._issues = issues
        screen._selected_index = 1

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
        ):
            await screen.action_dismiss()

        # Should remove the second issue
        assert len(screen._issues) == 2
        assert screen._issues[0]["id"] == "1"
        assert screen._issues[1]["id"] == "3"

    @pytest.mark.asyncio
    async def test_action_dismiss_updates_selection(self) -> None:
        """Test that dismiss updates selection index correctly."""
        screen = ReviewScreen()
        issues = [
            {"id": "1", "severity": "error", "message": "Error 1"},
            {"id": "2", "severity": "warning", "message": "Warning 1"},
        ]
        screen._issues = issues
        screen._selected_index = 1

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_update_detail_view"),
        ):
            await screen.action_dismiss()

        # Selection should move back if we're at the end
        assert screen._selected_index == 0

    @pytest.mark.asyncio
    async def test_action_dismiss_no_issues(self) -> None:
        """Test dismiss action when no issues are loaded."""
        screen = ReviewScreen()
        screen._issues = []
        screen._selected_index = -1

        with patch.object(screen, "_update_issue_list") as mock_update:
            await screen.action_dismiss()

        # Should not crash or update anything
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_dismiss_last_issue(self) -> None:
        """Test dismissing the last remaining issue."""
        screen = ReviewScreen()
        issues = [{"id": "1", "severity": "error", "message": "Error 1"}]
        screen._issues = issues
        screen._selected_index = 0

        with (
            patch.object(screen, "_update_issue_list"),
            patch.object(screen, "_clear_detail_view"),
        ):
            await screen.action_dismiss()

        assert len(screen._issues) == 0
        assert screen._selected_index == -1


class TestReviewScreenFixAllAction:
    """Tests for action_fix_all method (T035)."""

    @pytest.mark.asyncio
    async def test_action_fix_all_confirmed(self) -> None:
        """Test fix all action when user confirms."""
        screen = ReviewScreen()
        screen._issues = [
            {"id": "1", "severity": "error", "message": "Error 1"},
            {"id": "2", "severity": "warning", "message": "Warning 1"},
        ]

        with (
            patch.object(screen, "confirm", new=AsyncMock(return_value=True)),
            patch.object(screen, "_execute_fix_all") as mock_execute,
        ):
            await screen.action_fix_all()

        mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_action_fix_all_cancelled(self) -> None:
        """Test fix all action when user cancels."""
        screen = ReviewScreen()

        with (
            patch.object(screen, "confirm", new=AsyncMock(return_value=False)),
            patch.object(screen, "_execute_fix_all") as mock_execute,
        ):
            await screen.action_fix_all()

        mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_fix_all_no_issues(self) -> None:
        """Test fix all action when no issues are present."""
        screen = ReviewScreen()
        screen._issues = []

        with patch.object(screen, "confirm", new=AsyncMock()) as mock_confirm:
            await screen.action_fix_all()

        # Should not show confirmation if no issues
        mock_confirm.assert_not_called()


# =============================================================================
# ReviewScreen Internal Action Implementation Tests (T036-T042a)
# =============================================================================


class TestReviewScreenSubmitApproval:
    """Tests for _submit_approval method (T037)."""

    def test_submit_approval_updates_action_state(self) -> None:
        """Test that submit approval updates action state."""
        screen = ReviewScreen()
        screen.action_state = ReviewScreenActionState()

        with patch.object(screen, "_log_action") as mock_log:
            screen._submit_approval()

        # Should update state to show approval in progress
        assert screen.action_state.is_approving
        mock_log.assert_called_once()

    def test_submit_approval_logs_action(self) -> None:
        """Test that approval is logged correctly."""
        screen = ReviewScreen()

        with patch.object(screen, "_log_action") as mock_log:
            screen._submit_approval()

        mock_log.assert_called_once_with(ReviewAction.APPROVE)


class TestReviewScreenSubmitRequestChanges:
    """Tests for _submit_request_changes method (T038)."""

    def test_submit_request_changes_with_comment(self) -> None:
        """Test submit request changes with a comment."""
        screen = ReviewScreen()
        test_comment = "Fix the issues"

        with patch.object(screen, "_log_action") as mock_log:
            screen._submit_request_changes(test_comment)

        # Should update action state with comment
        assert screen.action_state.request_changes_comment == test_comment
        mock_log.assert_called_once_with(ReviewAction.REQUEST_CHANGES)

    def test_submit_request_changes_empty_comment(self) -> None:
        """Test submit request changes with empty comment."""
        screen = ReviewScreen()

        with patch.object(screen, "_log_action") as mock_log:
            screen._submit_request_changes("")

        mock_log.assert_called_once()


class TestReviewScreenExecuteFixAll:
    """Tests for _execute_fix_all method (T039)."""

    @pytest.mark.asyncio
    async def test_execute_fix_all_updates_state(self) -> None:
        """Test that execute fix all updates action state."""
        from maverick.models.issue_fix import FixResult as AgentFixResult

        screen = ReviewScreen()
        screen._issues = [
            {"id": "1", "severity": "error", "message": "Error 1"},
            {"id": "2", "severity": "warning", "message": "Warning 1"},
        ]

        # Mock IssueFixerAgent to avoid real agent execution
        mock_agent = AsyncMock()
        mock_result = AgentFixResult(
            success=True,
            issue_number=1000001,
            issue_title="Fix error finding",
        )
        mock_agent.execute.return_value = mock_result

        with patch(
            "maverick.tui.screens.review.IssueFixerAgent", return_value=mock_agent
        ):
            await screen._execute_fix_all()

        # Should complete and update state
        assert not screen.action_state.is_fixing
        assert screen.action_state.fix_results is not None

    @pytest.mark.asyncio
    async def test_execute_fix_all_creates_results(self) -> None:
        """Test that execute fix all creates fix results for each issue."""
        from maverick.models.issue_fix import FixResult as AgentFixResult

        screen = ReviewScreen()
        screen._issues = [
            {"id": "1", "severity": "error", "message": "Error 1"},
            {"id": "2", "severity": "warning", "message": "Warning 1"},
        ]

        # Mock IssueFixerAgent to avoid real agent execution
        mock_agent = AsyncMock()
        mock_result = AgentFixResult(
            success=True,
            issue_number=1000001,
            issue_title="Fix error finding",
        )
        mock_agent.execute.return_value = mock_result

        with patch(
            "maverick.tui.screens.review.IssueFixerAgent", return_value=mock_agent
        ):
            await screen._execute_fix_all()

        # Should have results for both issues
        assert screen.action_state.fix_results is not None
        assert len(screen.action_state.fix_results) == 2

    @pytest.mark.asyncio
    async def test_execute_fix_all_empty_issues(self) -> None:
        """Test execute fix all with no issues."""
        screen = ReviewScreen()
        screen._issues = []

        await screen._execute_fix_all()

        # Should complete with empty results
        assert screen.action_state.fix_results == ()

    @pytest.mark.asyncio
    async def test_execute_fix_all_with_agent_integration(self) -> None:
        """Test execute fix all with IssueFixerAgent integration."""
        screen = ReviewScreen()
        screen._issues = [
            {
                "id": "test-1",
                "file_path": "test.py",
                "line_number": 10,
                "severity": "error",
                "message": "Test error",
                "source": "pylint",
            }
        ]

        # Mock IssueFixerAgent
        from unittest.mock import AsyncMock, patch

        from maverick.models.issue_fix import FixResult as AgentFixResult

        mock_agent = AsyncMock()
        mock_result = AgentFixResult(
            success=True,
            issue_number=1000001,
            issue_title="Fix error finding in test.py",
        )
        mock_agent.execute.return_value = mock_result

        with patch(
            "maverick.tui.screens.review.IssueFixerAgent", return_value=mock_agent
        ):
            await screen._execute_fix_all()

        # Verify agent was called
        mock_agent.execute.assert_called_once()

        # Verify results
        assert screen.action_state.fix_results is not None
        assert len(screen.action_state.fix_results) == 1
        assert screen.action_state.fix_results[0].success is True
        assert screen.action_state.fix_results[0].finding_id == "test-1"

    @pytest.mark.asyncio
    async def test_execute_fix_all_handles_agent_failure(self) -> None:
        """Test execute fix all handles agent failures gracefully."""
        screen = ReviewScreen()
        screen._issues = [
            {
                "id": "test-1",
                "file_path": "test.py",
                "line_number": 10,
                "severity": "error",
                "message": "Test error",
                "source": "pylint",
            }
        ]

        # Mock IssueFixerAgent to return failure
        from unittest.mock import AsyncMock, patch

        from maverick.models.issue_fix import FixResult as AgentFixResult

        mock_agent = AsyncMock()
        mock_result = AgentFixResult(
            success=False,
            issue_number=1000001,
            issue_title="Fix error finding in test.py",
            errors=["Failed to apply fix", "Syntax error"],
        )
        mock_agent.execute.return_value = mock_result

        with patch(
            "maverick.tui.screens.review.IssueFixerAgent", return_value=mock_agent
        ):
            await screen._execute_fix_all()

        # Verify results show failure
        assert screen.action_state.fix_results is not None
        assert len(screen.action_state.fix_results) == 1
        assert screen.action_state.fix_results[0].success is False
        assert screen.action_state.fix_results[0].error_message is not None
        assert "Failed to apply fix" in screen.action_state.fix_results[0].error_message

    @pytest.mark.asyncio
    async def test_execute_fix_all_handles_exception(self) -> None:
        """Test execute fix all handles exceptions during agent execution."""
        screen = ReviewScreen()
        screen._issues = [
            {
                "id": "test-1",
                "file_path": "test.py",
                "line_number": 10,
                "severity": "error",
                "message": "Test error",
                "source": "pylint",
            }
        ]

        # Mock IssueFixerAgent to raise exception
        from unittest.mock import AsyncMock, patch

        mock_agent = AsyncMock()
        mock_agent.execute.side_effect = RuntimeError("Agent crashed")

        with patch(
            "maverick.tui.screens.review.IssueFixerAgent", return_value=mock_agent
        ):
            await screen._execute_fix_all()

        # Verify error is captured
        assert screen.action_state.fix_results is not None
        assert len(screen.action_state.fix_results) == 1
        assert screen.action_state.fix_results[0].success is False
        assert "Agent crashed" in screen.action_state.fix_results[0].error_message


class TestReviewScreenLogAction:
    """Tests for _log_action helper method (T040)."""

    def test_log_action_approve(self) -> None:
        """Test logging approve action."""
        screen = ReviewScreen()

        screen._log_action(ReviewAction.APPROVE)

        # Should update pending action
        assert screen.action_state.pending_action == ReviewAction.APPROVE

    def test_log_action_request_changes(self) -> None:
        """Test logging request changes action."""
        screen = ReviewScreen()

        screen._log_action(ReviewAction.REQUEST_CHANGES)

        assert screen.action_state.pending_action == ReviewAction.REQUEST_CHANGES

    def test_log_action_dismiss(self) -> None:
        """Test logging dismiss action."""
        screen = ReviewScreen()

        screen._log_action(ReviewAction.DISMISS)

        assert screen.action_state.pending_action == ReviewAction.DISMISS

    def test_log_action_fix_all(self) -> None:
        """Test logging fix all action."""
        screen = ReviewScreen()

        screen._log_action(ReviewAction.FIX_ALL)

        assert screen.action_state.pending_action == ReviewAction.FIX_ALL


class TestReviewScreenRefreshFindings:
    """Tests for refresh_findings method (T041)."""

    def test_refresh_findings_updates_banner(self) -> None:
        """Test that refresh_findings updates has_new_findings flag."""
        screen = ReviewScreen()
        screen.has_new_findings = False

        with (
            patch.object(screen, "_fetch_new_findings", return_value=[]),
            patch.object(screen, "_update_issue_list"),
        ):
            screen.refresh_findings()

        # Banner state should be updated
        assert isinstance(screen.has_new_findings, bool)

    def test_refresh_findings_with_new_findings(self) -> None:
        """Test refresh with new findings available."""
        screen = ReviewScreen()
        screen._issues = [{"id": "1", "severity": "error", "message": "Error 1"}]
        new_findings = [{"id": "2", "severity": "warning", "message": "Warning 1"}]

        with (
            patch.object(screen, "_fetch_new_findings", return_value=new_findings),
            patch.object(screen, "_update_issue_list"),
        ):
            screen.refresh_findings()

        # Should set banner flag when new findings exist
        assert screen.has_new_findings

    def test_refresh_findings_no_new_findings(self) -> None:
        """Test refresh when no new findings are available."""
        screen = ReviewScreen()
        screen._issues = [{"id": "1", "severity": "error", "message": "Error 1"}]

        with (
            patch.object(screen, "_fetch_new_findings", return_value=[]),
            patch.object(screen, "_update_issue_list"),
        ):
            screen.refresh_findings()

        # Should not set banner flag when no new findings
        assert not screen.has_new_findings


class TestReviewScreenFetchNewFindings:
    """Tests for _fetch_new_findings helper method (T042a)."""

    def test_fetch_new_findings_returns_list(self) -> None:
        """Test that _fetch_new_findings returns a list."""
        screen = ReviewScreen()

        result = screen._fetch_new_findings()

        assert isinstance(result, list)

    def test_fetch_new_findings_empty_when_no_new(self) -> None:
        """Test fetch returns empty list when no new findings."""
        screen = ReviewScreen()

        # Mock scenario where no new findings exist
        result = screen._fetch_new_findings()

        # For now, should return empty list (placeholder implementation)
        assert result == []


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


# =============================================================================
# ReviewScreen Grouped Findings Tests
# =============================================================================


class TestReviewScreenDiffPanel:
    """Tests for diff panel integration."""

    def test_update_detail_view_updates_diff_panel(self) -> None:
        """Test that _update_detail_view also updates the diff panel."""
        screen = ReviewScreen()
        issues = [
            {
                "file_path": "test.py",
                "line_number": 42,
                "severity": "error",
                "message": "Test error",
                "source": "pylint",
            }
        ]
        screen._issues = issues
        screen._selected_index = 0

        with (
            patch.object(screen, "query_one") as mock_query,
            patch.object(screen, "_update_diff_panel") as mock_diff,
        ):
            # Mock the detail widget
            mock_detail = MagicMock()
            mock_query.return_value = mock_detail

            screen._update_detail_view()

        # Should call _update_diff_panel with file and line
        mock_diff.assert_called_once_with("test.py", 42)

    def test_clear_detail_view_clears_diff_panel(self) -> None:
        """Test that _clear_detail_view also clears the diff panel."""
        screen = ReviewScreen()

        with patch.object(screen, "query_one") as mock_query:
            # Mock both the detail widget and diff panel
            mock_detail = MagicMock()
            mock_diff_panel = MagicMock()

            def query_side_effect(selector, widget_type=None):
                if selector == "#issue-detail-content":
                    return mock_detail
                elif selector == "#diff-panel":
                    return mock_diff_panel
                return MagicMock()

            mock_query.side_effect = query_side_effect

            screen._clear_detail_view()

        # Should clear the diff panel
        mock_diff_panel.update_diff.assert_called_once_with()

    def test_update_diff_panel_with_valid_file(self) -> None:
        """Test _update_diff_panel with valid file and line number."""
        screen = ReviewScreen()

        with patch.object(screen, "query_one") as mock_query:
            mock_diff_panel = MagicMock()
            mock_query.return_value = mock_diff_panel

            screen._update_diff_panel("test.py", 42)

        # Should call update_diff on the panel
        mock_diff_panel.update_diff.assert_called_once()
        call_args = mock_diff_panel.update_diff.call_args
        assert call_args.kwargs["file_path"] == "test.py"
        assert call_args.kwargs["line_number"] == 42

    def test_update_diff_panel_with_string_line_number(self) -> None:
        """Test _update_diff_panel converts string line numbers to int."""
        screen = ReviewScreen()

        with patch.object(screen, "query_one") as mock_query:
            mock_diff_panel = MagicMock()
            mock_query.return_value = mock_diff_panel

            screen._update_diff_panel("test.py", "42")

        # Should convert string to int
        call_args = mock_diff_panel.update_diff.call_args
        assert call_args.kwargs["line_number"] == 42

    def test_update_diff_panel_handles_exception(self) -> None:
        """Test _update_diff_panel handles exceptions gracefully."""
        screen = ReviewScreen()

        with patch.object(screen, "query_one") as mock_query:
            mock_query.side_effect = Exception("Widget not found")

            # Should not raise exception
            screen._update_diff_panel("test.py", 42)


class TestReviewScreenGroupedFindings:
    """Tests for grouped findings display by severity."""

    def test_update_issue_list_groups_by_severity(self) -> None:
        """Test that _update_issue_list groups issues by severity."""
        screen = ReviewScreen()
        issues = [
            {
                "severity": "warning",
                "message": "Warning 1",
                "file_path": "a.py",
                "line_number": 1,
            },
            {
                "severity": "error",
                "message": "Error 1",
                "file_path": "b.py",
                "line_number": 2,
            },
            {
                "severity": "info",
                "message": "Info 1",
                "file_path": "c.py",
                "line_number": 3,
            },
            {
                "severity": "error",
                "message": "Error 2",
                "file_path": "d.py",
                "line_number": 4,
            },
            {
                "severity": "suggestion",
                "message": "Suggestion 1",
                "file_path": "e.py",
                "line_number": 5,
            },
        ]
        screen._issues = issues

        mock_issue_list = MagicMock()
        mounted_widgets = []
        mock_issue_list.mount = lambda w: mounted_widgets.append(w)
        mock_issue_list.remove_children = MagicMock()

        with patch.object(screen, "query_one", return_value=mock_issue_list):
            screen._update_issue_list()

        # Should have mounted: 4 headers + 5 issue items = 9 widgets total
        assert len(mounted_widgets) == 9

        # Verify headers are present by checking IDs
        header_ids = [
            w.id
            for w in mounted_widgets
            if hasattr(w, "id") and w.id and "severity-header" in w.id
        ]
        assert len(header_ids) == 4  # error, warning, suggestion, info

    def test_update_issue_list_severity_order(self) -> None:
        """Test that severities are displayed in correct order: errors,
        warnings, suggestions, info.
        """
        screen = ReviewScreen()
        issues = [
            {
                "severity": "info",
                "message": "Info 1",
                "file_path": "a.py",
                "line_number": 1,
            },
            {
                "severity": "suggestion",
                "message": "Suggestion 1",
                "file_path": "b.py",
                "line_number": 2,
            },
            {
                "severity": "warning",
                "message": "Warning 1",
                "file_path": "c.py",
                "line_number": 3,
            },
            {
                "severity": "error",
                "message": "Error 1",
                "file_path": "d.py",
                "line_number": 4,
            },
        ]
        screen._issues = issues

        mock_issue_list = MagicMock()
        mounted_widgets = []
        mock_issue_list.mount = lambda w: mounted_widgets.append(w)
        mock_issue_list.remove_children = MagicMock()

        with patch.object(screen, "query_one", return_value=mock_issue_list):
            screen._update_issue_list()

        # Check that headers appear in correct order
        header_ids = [
            w.id
            for w in mounted_widgets
            if hasattr(w, "id") and w.id and "severity-header" in w.id
        ]
        assert header_ids == [
            "severity-header-error",
            "severity-header-warning",
            "severity-header-suggestion",
            "severity-header-info",
        ]

    def test_update_issue_list_skips_empty_severity_groups(self) -> None:
        """Test that severity groups with no issues are not displayed."""
        screen = ReviewScreen()
        issues = [
            {
                "severity": "error",
                "message": "Error 1",
                "file_path": "a.py",
                "line_number": 1,
            },
            {
                "severity": "error",
                "message": "Error 2",
                "file_path": "b.py",
                "line_number": 2,
            },
        ]
        screen._issues = issues

        mock_issue_list = MagicMock()
        mounted_widgets = []
        mock_issue_list.mount = lambda w: mounted_widgets.append(w)
        mock_issue_list.remove_children = MagicMock()

        with patch.object(screen, "query_one", return_value=mock_issue_list):
            screen._update_issue_list()

        # Should only have 1 header (error) + 2 issue items = 3 widgets
        assert len(mounted_widgets) == 3
        header_ids = [
            w.id
            for w in mounted_widgets
            if hasattr(w, "id") and w.id and "severity-header" in w.id
        ]
        assert header_ids == ["severity-header-error"]

    def test_update_issue_list_global_index_across_groups(self) -> None:
        """Test that issue indices continue across severity groups."""
        screen = ReviewScreen()
        issues = [
            {
                "severity": "error",
                "message": "Error 1",
                "file_path": "a.py",
                "line_number": 1,
            },
            {
                "severity": "warning",
                "message": "Warning 1",
                "file_path": "b.py",
                "line_number": 2,
            },
        ]
        screen._issues = issues

        mock_issue_list = MagicMock()
        mounted_widgets = []
        mock_issue_list.mount = lambda w: mounted_widgets.append(w)
        mock_issue_list.remove_children = MagicMock()

        with patch.object(screen, "query_one", return_value=mock_issue_list):
            screen._update_issue_list()

        # Check that issue items have sequential IDs
        issue_ids = [
            w.id
            for w in mounted_widgets
            if hasattr(w, "id") and w.id and "issue-item" in w.id
        ]
        assert issue_ids == ["issue-item-0", "issue-item-1"]
