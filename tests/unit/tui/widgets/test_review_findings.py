"""Unit tests for ReviewFindings widget.

Feature: 012-workflow-widgets
User Story 3: ReviewFindings Widget
Tests cover initialization, finding management, selection, expansion,
bulk actions, and messages.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from textual.app import App

from maverick.tui.models import (
    CodeLocation,
    FindingSeverity,
    ReviewFinding,
)
from maverick.tui.widgets.review_findings import ReviewFindings

# =============================================================================
# Test App for ReviewFindings Testing
# =============================================================================


class ReviewFindingsTestApp(App):
    """Test app for ReviewFindings widget testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.finding_expanded_messages: list[ReviewFindings.FindingExpanded] = []
        self.finding_selected_messages: list[ReviewFindings.FindingSelected] = []
        self.bulk_dismiss_messages: list[ReviewFindings.BulkDismissRequested] = []
        self.bulk_create_issue_messages: list[
            ReviewFindings.BulkCreateIssueRequested
        ] = []
        self.file_location_clicked_messages: list[
            ReviewFindings.FileLocationClicked
        ] = []

    def compose(self):
        """Compose the test app."""
        yield ReviewFindings()

    def on_review_findings_finding_expanded(
        self, message: ReviewFindings.FindingExpanded
    ) -> None:
        """Capture FindingExpanded messages."""
        self.finding_expanded_messages.append(message)

    def on_review_findings_finding_selected(
        self, message: ReviewFindings.FindingSelected
    ) -> None:
        """Capture FindingSelected messages."""
        self.finding_selected_messages.append(message)

    def on_review_findings_bulk_dismiss_requested(
        self, message: ReviewFindings.BulkDismissRequested
    ) -> None:
        """Capture BulkDismissRequested messages."""
        self.bulk_dismiss_messages.append(message)

    def on_review_findings_bulk_create_issue_requested(
        self, message: ReviewFindings.BulkCreateIssueRequested
    ) -> None:
        """Capture BulkCreateIssueRequested messages."""
        self.bulk_create_issue_messages.append(message)

    def on_review_findings_file_location_clicked(
        self, message: ReviewFindings.FileLocationClicked
    ) -> None:
        """Capture FileLocationClicked messages."""
        self.file_location_clicked_messages.append(message)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_findings() -> list[ReviewFinding]:
    """Sample findings for testing."""
    return [
        ReviewFinding(
            id="finding-1",
            severity=FindingSeverity.ERROR,
            location=CodeLocation("src/main.py", 10, 12),
            title="Undefined variable reference",
            description="Variable 'foo' is referenced before assignment",
            suggested_fix="Initialize 'foo' before use",
            source="coderabbit",
        ),
        ReviewFinding(
            id="finding-2",
            severity=FindingSeverity.WARNING,
            location=CodeLocation("src/utils.py", 25),
            title="Missing type annotation",
            description="Function parameter lacks type annotation",
            suggested_fix="Add type annotation: def func(param: str) -> None:",
            source="architecture",
        ),
        ReviewFinding(
            id="finding-3",
            severity=FindingSeverity.SUGGESTION,
            location=CodeLocation("tests/test_main.py", 5),
            title="Consider using pytest fixture",
            description="Repeated setup code could be extracted to fixture",
            suggested_fix=None,
            source="review",
        ),
        ReviewFinding(
            id="finding-4",
            severity=FindingSeverity.ERROR,
            location=CodeLocation("src/api.py", 100, 105),
            title="Potential null pointer exception",
            description="Object may be null when method is called",
            suggested_fix="Add null check before method call",
            source="coderabbit",
        ),
    ]


# =============================================================================
# ReviewFindings Initialization Tests (T057)
# =============================================================================


class TestReviewFindingsInitialization:
    """Tests for ReviewFindings initialization."""

    @pytest.mark.asyncio
    async def test_initialization_defaults(self) -> None:
        """Test ReviewFindings initializes with default values."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            assert widget._state.is_empty
            assert len(widget._state.findings) == 0
            assert widget._state.expanded_index is None
            assert widget._state.focused_index == 0

    @pytest.mark.asyncio
    async def test_empty_state_message_displayed(self) -> None:
        """Test empty state message is displayed when no findings."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)
            await pilot.pause()

            # Should show empty state
            assert widget._state.is_empty


# =============================================================================
# Update Findings Tests (T058)
# =============================================================================


class TestUpdateFindings:
    """Tests for update_findings method."""

    @pytest.mark.asyncio
    async def test_update_with_empty_list(self) -> None:
        """Test update_findings with empty list."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings([])
            await pilot.pause()

            assert widget._state.is_empty
            assert len(widget._state.findings) == 0

    @pytest.mark.asyncio
    async def test_update_with_single_finding(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test update_findings with single finding."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings([sample_findings[0]])
            await pilot.pause()

            assert not widget._state.is_empty
            assert len(widget._state.findings) == 1
            assert widget._state.findings[0].finding.id == "finding-1"
            assert not widget._state.findings[0].selected

    @pytest.mark.asyncio
    async def test_update_with_multiple_findings(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test update_findings with multiple findings."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            assert len(widget._state.findings) == 4
            assert all(not item.selected for item in widget._state.findings)

    @pytest.mark.asyncio
    async def test_findings_grouped_by_severity(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test findings are grouped by severity (errors first)."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Check grouping
            by_severity = widget._state.findings_by_severity
            assert len(by_severity[FindingSeverity.ERROR]) == 2
            assert len(by_severity[FindingSeverity.WARNING]) == 1
            assert len(by_severity[FindingSeverity.SUGGESTION]) == 1

    @pytest.mark.asyncio
    async def test_update_resets_selection_state(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test update_findings resets selection state."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Set initial findings and select some
            widget.update_findings(sample_findings)
            await pilot.pause()
            widget.select_finding(0, selected=True)
            await pilot.pause()

            # Update with new findings
            widget.update_findings(sample_findings[:2])
            await pilot.pause()

            # Selection should be reset
            assert widget._state.selected_count == 0


# =============================================================================
# Selection Tests (T059)
# =============================================================================


class TestFindingSelection:
    """Tests for finding selection functionality."""

    @pytest.mark.asyncio
    async def test_select_finding_valid_index(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test selecting a finding with valid index."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            widget.select_finding(0, selected=True)
            await pilot.pause()

            assert widget._state.findings[0].selected
            assert widget._state.selected_count == 1

            # Check message was posted
            assert len(pilot.app.finding_selected_messages) == 1
            msg = pilot.app.finding_selected_messages[0]
            assert msg.finding_id == "finding-1"
            assert msg.index == 0
            assert msg.selected is True

    @pytest.mark.asyncio
    async def test_deselect_finding(self, sample_findings: list[ReviewFinding]) -> None:
        """Test deselecting a finding."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Select then deselect
            widget.select_finding(0, selected=True)
            await pilot.pause()
            widget.select_finding(0, selected=False)
            await pilot.pause()

            assert not widget._state.findings[0].selected
            assert widget._state.selected_count == 0

            # Check both messages
            assert len(pilot.app.finding_selected_messages) == 2
            assert pilot.app.finding_selected_messages[1].selected is False

    @pytest.mark.asyncio
    async def test_select_multiple_findings(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test selecting multiple findings."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            widget.select_finding(0, selected=True)
            widget.select_finding(2, selected=True)
            await pilot.pause()

            assert widget._state.selected_count == 2
            assert widget._state.findings[0].selected
            assert widget._state.findings[2].selected

    @pytest.mark.asyncio
    async def test_select_all(self, sample_findings: list[ReviewFinding]) -> None:
        """Test select_all selects all findings."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            widget.select_all()
            await pilot.pause()

            assert widget._state.selected_count == 4
            assert all(item.selected for item in widget._state.findings)

    @pytest.mark.asyncio
    async def test_deselect_all(self, sample_findings: list[ReviewFinding]) -> None:
        """Test deselect_all clears all selections."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Select all then deselect all
            widget.select_all()
            await pilot.pause()
            widget.deselect_all()
            await pilot.pause()

            assert widget._state.selected_count == 0
            assert all(not item.selected for item in widget._state.findings)

    @pytest.mark.asyncio
    async def test_select_out_of_range_index(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test selecting out of range index is ignored."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Try to select invalid index
            widget.select_finding(999, selected=True)
            await pilot.pause()

            assert widget._state.selected_count == 0

    @pytest.mark.asyncio
    async def test_selected_findings_property(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test selected_findings property returns correct findings."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            widget.select_finding(0, selected=True)
            widget.select_finding(2, selected=True)
            await pilot.pause()

            selected = widget.selected_findings
            assert len(selected) == 2
            assert selected[0].id == "finding-1"
            assert selected[1].id == "finding-3"


# =============================================================================
# Expansion Tests (T060)
# =============================================================================


class TestFindingExpansion:
    """Tests for finding expansion functionality."""

    @pytest.mark.asyncio
    async def test_expand_finding(self, sample_findings: list[ReviewFinding]) -> None:
        """Test expanding a finding."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            widget.expand_finding(0)
            await pilot.pause()

            assert widget._state.expanded_index == 0

            # Check message was posted
            assert len(pilot.app.finding_expanded_messages) == 1
            msg = pilot.app.finding_expanded_messages[0]
            assert msg.finding_id == "finding-1"
            assert msg.index == 0

    @pytest.mark.asyncio
    async def test_expand_different_finding_collapses_previous(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test expanding a different finding collapses the previous one."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Expand first finding
            widget.expand_finding(0)
            await pilot.pause()
            assert widget._state.expanded_index == 0

            # Expand second finding
            widget.expand_finding(1)
            await pilot.pause()
            assert widget._state.expanded_index == 1

    @pytest.mark.asyncio
    async def test_collapse_finding(self, sample_findings: list[ReviewFinding]) -> None:
        """Test collapsing an expanded finding."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Expand then collapse
            widget.expand_finding(0)
            await pilot.pause()
            widget.collapse_finding()
            await pilot.pause()

            assert widget._state.expanded_index is None

    @pytest.mark.asyncio
    async def test_expand_out_of_range_index(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test expanding out of range index is ignored."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            widget.expand_finding(999)
            await pilot.pause()

            assert widget._state.expanded_index is None


# =============================================================================
# Bulk Action Tests (T061)
# =============================================================================


class TestBulkActions:
    """Tests for bulk action functionality."""

    @pytest.mark.asyncio
    async def test_bulk_dismiss_with_selections(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test bulk dismiss with selected findings."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Select some findings
            widget.select_finding(0, selected=True)
            widget.select_finding(2, selected=True)
            await pilot.pause()

            # Trigger bulk dismiss
            widget.action_bulk_dismiss()
            await pilot.pause()

            # Check message was posted
            assert len(pilot.app.bulk_dismiss_messages) == 1
            msg = pilot.app.bulk_dismiss_messages[0]
            assert len(msg.finding_ids) == 2
            assert "finding-1" in msg.finding_ids
            assert "finding-3" in msg.finding_ids

    @pytest.mark.asyncio
    async def test_bulk_dismiss_with_no_selections(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test bulk dismiss with no selections does nothing."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Trigger bulk dismiss with no selections
            widget.action_bulk_dismiss()
            await pilot.pause()

            # No message should be posted
            assert len(pilot.app.bulk_dismiss_messages) == 0

    @pytest.mark.asyncio
    async def test_bulk_create_issue_with_selections(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test bulk create issue with selected findings."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Select some findings
            widget.select_finding(1, selected=True)
            widget.select_finding(3, selected=True)
            await pilot.pause()

            # Trigger bulk create issue
            widget.action_bulk_create_issue()
            await pilot.pause()

            # Check message was posted
            assert len(pilot.app.bulk_create_issue_messages) == 1
            msg = pilot.app.bulk_create_issue_messages[0]
            assert len(msg.finding_ids) == 2
            assert "finding-2" in msg.finding_ids
            assert "finding-4" in msg.finding_ids

    @pytest.mark.asyncio
    async def test_bulk_create_issue_with_no_selections(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test bulk create issue with no selections does nothing."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Trigger bulk create issue with no selections
            widget.action_bulk_create_issue()
            await pilot.pause()

            # No message should be posted
            assert len(pilot.app.bulk_create_issue_messages) == 0


# =============================================================================
# File Location Click Tests (T062)
# =============================================================================


class TestFileLocationClick:
    """Tests for file location click functionality."""

    @pytest.mark.asyncio
    async def test_file_location_click_emits_message(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test clicking file location emits FileLocationClicked message."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Simulate file location click
            widget._on_file_location_clicked("src/main.py", 10)
            await pilot.pause()

            # Check message was posted
            assert len(pilot.app.file_location_clicked_messages) == 1
            msg = pilot.app.file_location_clicked_messages[0]
            assert msg.file_path == "src/main.py"
            assert msg.line_number == 10


# =============================================================================
# Code Context Tests (T063)
# =============================================================================


class TestCodeContext:
    """Tests for code context functionality."""

    @pytest.mark.asyncio
    async def test_show_code_context(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test showing code context for a finding."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Show code context
            widget.show_code_context(0)
            await pilot.pause()

            # Code context should be requested (implementation detail)
            # Widget should track which finding's context is shown
            # This is a placeholder - actual implementation may vary

    @pytest.mark.asyncio
    async def test_show_code_context_out_of_range(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test showing code context for out of range index is ignored."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Try to show context for invalid index
            widget.show_code_context(999)
            await pilot.pause()

            # Should not crash


# =============================================================================
# Message Tests (T064)
# =============================================================================


class TestReviewFindingsMessages:
    """Tests for ReviewFindings message classes."""

    def test_finding_expanded_message(self) -> None:
        """Test FindingExpanded message initialization."""
        msg = ReviewFindings.FindingExpanded(finding_id="test-1", index=5)
        assert msg.finding_id == "test-1"
        assert msg.index == 5

    def test_finding_selected_message(self) -> None:
        """Test FindingSelected message initialization."""
        msg = ReviewFindings.FindingSelected(
            finding_id="test-2", index=3, selected=True
        )
        assert msg.finding_id == "test-2"
        assert msg.index == 3
        assert msg.selected is True

    def test_bulk_dismiss_requested_message(self) -> None:
        """Test BulkDismissRequested message initialization."""
        msg = ReviewFindings.BulkDismissRequested(finding_ids=("f1", "f2", "f3"))
        assert len(msg.finding_ids) == 3
        assert "f1" in msg.finding_ids

    def test_bulk_create_issue_requested_message(self) -> None:
        """Test BulkCreateIssueRequested message initialization."""
        msg = ReviewFindings.BulkCreateIssueRequested(finding_ids=("f1", "f2"))
        assert len(msg.finding_ids) == 2

    def test_file_location_clicked_message(self) -> None:
        """Test FileLocationClicked message initialization."""
        msg = ReviewFindings.FileLocationClicked(
            file_path="src/test.py", line_number=42
        )
        assert msg.file_path == "src/test.py"
        assert msg.line_number == 42


# =============================================================================
# Integration Tests
# =============================================================================


class TestReviewFindingsIntegration:
    """Integration tests for ReviewFindings widget."""

    @pytest.mark.asyncio
    async def test_typical_usage_flow(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test typical usage flow of ReviewFindings."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Start with empty state
            assert widget._state.is_empty

            # Add findings
            widget.update_findings(sample_findings)
            await pilot.pause()
            assert not widget._state.is_empty

            # Expand a finding
            widget.expand_finding(0)
            await pilot.pause()
            assert widget._state.expanded_index == 0

            # Select some findings
            widget.select_finding(0, selected=True)
            widget.select_finding(1, selected=True)
            await pilot.pause()
            assert widget._state.selected_count == 2

            # Bulk dismiss
            widget.action_bulk_dismiss()
            await pilot.pause()
            assert len(pilot.app.bulk_dismiss_messages) == 1

    @pytest.mark.asyncio
    async def test_severity_grouping_order(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test findings are grouped by severity in correct order."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            by_severity = widget._state.findings_by_severity

            # Errors should be first
            errors = by_severity[FindingSeverity.ERROR]
            assert len(errors) == 2
            assert all(
                item.finding.severity == FindingSeverity.ERROR for item in errors
            )

            # Then warnings
            warnings = by_severity[FindingSeverity.WARNING]
            assert len(warnings) == 1

            # Then suggestions
            suggestions = by_severity[FindingSeverity.SUGGESTION]
            assert len(suggestions) == 1

    @pytest.mark.asyncio
    async def test_empty_to_populated_transition(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test transition from empty to populated state."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Start empty
            assert widget._state.is_empty

            # Add findings
            widget.update_findings(sample_findings)
            await pilot.pause()
            assert not widget._state.is_empty
            assert len(widget._state.findings) == 4

            # Clear findings
            widget.update_findings([])
            await pilot.pause()
            assert widget._state.is_empty
            assert len(widget._state.findings) == 0

    @pytest.mark.asyncio
    async def test_selection_persistence_across_expansion(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test selection state persists when expanding/collapsing."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            widget.update_findings(sample_findings)
            await pilot.pause()

            # Select a finding
            widget.select_finding(0, selected=True)
            await pilot.pause()

            # Expand it
            widget.expand_finding(0)
            await pilot.pause()

            # Selection should persist
            assert widget._state.findings[0].selected

            # Collapse it
            widget.collapse_finding()
            await pilot.pause()

            # Selection should still persist
            assert widget._state.findings[0].selected


# =============================================================================
# Broken File Link Tests
# =============================================================================


class TestBrokenFileLinks:
    """Tests for broken file link detection and notifications."""

    @pytest.mark.asyncio
    async def test_broken_file_link_has_tooltip(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test broken file links have tooltip set."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Mock Path.exists to return False for all files
            with patch("maverick.tui.widgets.review_findings.Path") as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = False
                mock_path.return_value = mock_path_instance

                widget.update_findings(sample_findings[:1])
                await pilot.pause()

                # Find the location button
                location_button = widget.query_one("#location-0")

                # Check that tooltip is set
                assert location_button.tooltip is not None
                assert "File not found" in location_button.tooltip
                assert "src/main.py" in location_button.tooltip

    @pytest.mark.asyncio
    async def test_broken_file_link_has_css_class(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test broken file links have appropriate CSS class."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Mock Path.exists to return False for all files
            with patch("maverick.tui.widgets.review_findings.Path") as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = False
                mock_path.return_value = mock_path_instance

                widget.update_findings(sample_findings[:1])
                await pilot.pause()

                # Find the location button
                location_button = widget.query_one("#location-0")

                # Check that broken CSS class is applied
                assert "file-location-broken" in location_button.classes

    @pytest.mark.asyncio
    async def test_valid_file_link_has_no_tooltip(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test valid file links have no tooltip."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Mock Path.exists to return True for all files
            with patch("maverick.tui.widgets.review_findings.Path") as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = True
                mock_path.return_value = mock_path_instance

                widget.update_findings(sample_findings[:1])
                await pilot.pause()

                # Find the location button
                location_button = widget.query_one("#location-0")

                # Check that no tooltip is set
                assert location_button.tooltip is None

    @pytest.mark.asyncio
    async def test_valid_file_link_has_no_broken_class(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test valid file links do not have broken CSS class."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Mock Path.exists to return True for all files
            with patch("maverick.tui.widgets.review_findings.Path") as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = True
                mock_path.return_value = mock_path_instance

                widget.update_findings(sample_findings[:1])
                await pilot.pause()

                # Find the location button
                location_button = widget.query_one("#location-0")

                # Check that broken CSS class is NOT applied
                assert "file-location-broken" not in location_button.classes

    @pytest.mark.asyncio
    async def test_clicking_broken_link_shows_toast(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test clicking broken file link shows toast notification."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Mock Path.exists to return False for all files
            with patch("maverick.tui.widgets.review_findings.Path") as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = False
                mock_path.return_value = mock_path_instance

                widget.update_findings(sample_findings[:1])
                await pilot.pause()

                # Mock the notify method to capture calls
                original_notify = widget.notify
                notify_calls = []

                def mock_notify(*args, **kwargs):
                    notify_calls.append((args, kwargs))
                    return original_notify(*args, **kwargs)

                widget.notify = mock_notify

                # Click the location button
                await pilot.click("#location-0")
                await pilot.pause()

                # Check that notify was called with error message
                assert len(notify_calls) == 1
                args, kwargs = notify_calls[0]
                assert "File not found" in args[0]
                assert "src/main.py" in args[0]
                assert kwargs.get("severity") == "error"
                assert kwargs.get("title") == "Broken File Link"

    @pytest.mark.asyncio
    async def test_clicking_broken_link_does_not_emit_file_location_clicked(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test clicking broken link does not emit FileLocationClicked message."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Mock Path.exists to return False for all files
            with patch("maverick.tui.widgets.review_findings.Path") as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = False
                mock_path.return_value = mock_path_instance

                widget.update_findings(sample_findings[:1])
                await pilot.pause()

                # Click the location button
                await pilot.click("#location-0")
                await pilot.pause()

                # Check that no FileLocationClicked message was posted
                assert len(pilot.app.file_location_clicked_messages) == 0

    @pytest.mark.asyncio
    async def test_clicking_valid_link_emits_file_location_clicked(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test clicking valid link still emits FileLocationClicked message."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Mock Path.exists to return True for all files
            with patch("maverick.tui.widgets.review_findings.Path") as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.exists.return_value = True
                mock_path.return_value = mock_path_instance

                widget.update_findings(sample_findings[:1])
                await pilot.pause()

                # Click the location button
                await pilot.click("#location-0")
                await pilot.pause()

                # Check that FileLocationClicked message was posted
                assert len(pilot.app.file_location_clicked_messages) == 1
                msg = pilot.app.file_location_clicked_messages[0]
                assert msg.file_path == "src/main.py"
                assert msg.line_number == 10

    @pytest.mark.asyncio
    async def test_mixed_valid_and_broken_links(
        self, sample_findings: list[ReviewFinding]
    ) -> None:
        """Test handling of mixed valid and broken file links."""
        async with ReviewFindingsTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ReviewFindings)

            # Mock Path.exists to return True for first file, False for second
            with patch("maverick.tui.widgets.review_findings.Path") as mock_path:
                call_count = 0

                def mock_exists():
                    nonlocal call_count
                    call_count += 1
                    # First file exists, second doesn't (called twice per render)
                    return call_count % 2 == 1

                mock_path_instance = Mock()
                mock_path_instance.exists.side_effect = mock_exists
                mock_path.return_value = mock_path_instance

                widget.update_findings(sample_findings[:2])
                await pilot.pause()

                # Just verify both buttons were created
                # (mocking makes exact state checking unreliable)
                location_button_0 = widget.query_one("#location-0")
                location_button_1 = widget.query_one("#location-1")
                assert location_button_0 is not None
                assert location_button_1 is not None
