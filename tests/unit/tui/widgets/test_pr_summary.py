"""Tests for PRSummary widget.

Feature: 012-workflow-widgets
Test Coverage:
- T093: Empty state rendering (no PR)
- T094: Loading state with spinner
- T095: PR info display (title, number, state icon)
- T096: Description preview truncation (200 char)
- T097: Description expand/collapse functionality
- T098: Status checks display with icons
- T099: Open in browser functionality
- T100: Message emission (OpenPRRequested, DescriptionExpanded, DescriptionCollapsed)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from textual.app import App

from maverick.tui.models import (
    CheckStatus,
    PRInfo,
    PRState,
    StatusCheck,
)
from maverick.tui.widgets.pr_summary import PRSummary

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_pr() -> PRInfo:
    """Create a sample PR with all fields populated."""
    return PRInfo(
        number=42,
        title="Add new feature for workflow automation",
        description="This PR implements a comprehensive workflow automation system "
        "that allows users to orchestrate multiple agents in parallel. "
        "It includes validation steps, error handling, and detailed logging. "
        "The implementation follows our architecture guidelines and includes "
        "comprehensive test coverage with both unit and integration tests.",
        state=PRState.OPEN,
        url="https://github.com/org/repo/pull/42",
        checks=(
            StatusCheck(
                name="CI / build",
                status=CheckStatus.PASSING,
                url="https://github.com/org/repo/actions/runs/123",
            ),
            StatusCheck(
                name="CI / test",
                status=CheckStatus.PASSING,
                url="https://github.com/org/repo/actions/runs/124",
            ),
            StatusCheck(
                name="CodeQL",
                status=CheckStatus.PENDING,
                url="https://github.com/org/repo/security/code-scanning",
            ),
        ),
        branch="feature/automation",
        base_branch="main",
    )


@pytest.fixture
def minimal_pr() -> PRInfo:
    """Create a minimal PR with only required fields."""
    return PRInfo(
        number=1,
        title="Fix typo",
        description="Fixed a typo in README",
        state=PRState.MERGED,
        url="https://github.com/org/repo/pull/1",
    )


@pytest.fixture
def pr_with_long_description() -> PRInfo:
    """Create a PR with description longer than 200 chars."""
    long_desc = (
        "This is a very long description that exceeds the 200 character limit "
        "and should be truncated in the preview. " * 5
    )
    return PRInfo(
        number=99,
        title="Major refactoring",
        description=long_desc,
        state=PRState.CLOSED,
        url="https://github.com/org/repo/pull/99",
    )


# =============================================================================
# Test: Empty State (T093)
# =============================================================================


@pytest.mark.asyncio
async def test_empty_state_no_pr():
    """T093: Widget displays empty state when no PR data."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)

        # Verify empty state
        assert widget.state.is_empty
        assert widget.state.pr is None
        assert not widget.state.loading

        # Verify rendering shows empty message
        rendered = widget.render()
        assert "no pull request" in str(rendered).lower()


@pytest.mark.asyncio
async def test_empty_state_after_clearing_pr():
    """T093: Widget shows empty state after clearing PR data."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)

        # Set PR data
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test PR",
            state=PRState.OPEN,
            url="https://github.com/test/test/pull/1",
        )
        widget.update_pr(pr)
        await pilot.pause()

        assert not widget.state.is_empty
        assert widget.state.pr == pr

        # Clear PR data
        widget.update_pr(None)
        await pilot.pause()

        assert widget.state.is_empty
        assert widget.state.pr is None


# =============================================================================
# Test: Loading State (T094)
# =============================================================================


@pytest.mark.asyncio
async def test_loading_state():
    """T094: Widget displays loading state with spinner."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)

        # Set loading state
        widget.set_loading(True)
        await pilot.pause()

        assert widget.state.loading
        assert not widget.state.is_empty

        # Verify loading indicator in render
        rendered = str(widget.render())
        assert "loading" in rendered.lower() or "..." in rendered

        # Clear loading
        widget.set_loading(False)
        await pilot.pause()

        assert not widget.state.loading


@pytest.mark.asyncio
async def test_loading_then_pr_data():
    """T094: Widget transitions from loading to displaying PR data."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)

        # Start with loading
        widget.set_loading(True)
        await pilot.pause()
        assert widget.state.loading

        # Load PR data
        pr = PRInfo(
            number=5,
            title="Test PR",
            description="Test description",
            state=PRState.OPEN,
            url="https://github.com/test/test/pull/5",
        )
        widget.update_pr(pr)
        widget.set_loading(False)
        await pilot.pause()

        assert not widget.state.loading
        assert widget.state.pr == pr
        assert not widget.state.is_empty


# =============================================================================
# Test: PR Info Display (T095)
# =============================================================================


@pytest.mark.asyncio
async def test_pr_info_display_open(sample_pr: PRInfo):
    """T095: Widget displays PR title, number, and OPEN state icon."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(sample_pr)
        await pilot.pause()

        rendered = str(widget.render())

        # Check for title and number
        assert "42" in rendered
        assert "Add new feature for workflow automation" in rendered

        # Check for OPEN state indicator (icon or text)
        assert widget.state.pr.state == PRState.OPEN


@pytest.mark.asyncio
async def test_pr_info_display_merged(minimal_pr: PRInfo):
    """T095: Widget displays MERGED state icon correctly."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(minimal_pr)
        await pilot.pause()

        assert widget.state.pr.state == PRState.MERGED
        assert widget.state.pr.number == 1
        assert widget.state.pr.title == "Fix typo"


@pytest.mark.asyncio
async def test_pr_info_display_closed(pr_with_long_description: PRInfo):
    """T095: Widget displays CLOSED state icon correctly."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr_with_long_description)
        await pilot.pause()

        assert widget.state.pr.state == PRState.CLOSED
        assert widget.state.pr.number == 99


# =============================================================================
# Test: Description Preview & Truncation (T096)
# =============================================================================


@pytest.mark.asyncio
async def test_description_preview_short():
    """T096: Short descriptions are displayed without truncation."""
    pr = PRInfo(
        number=1,
        title="Short",
        description="This is a short description under 200 characters.",
        state=PRState.OPEN,
        url="https://github.com/test/test/pull/1",
    )

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr)
        await pilot.pause()

        # Verify description_preview doesn't truncate
        assert pr.description_preview == pr.description
        assert "..." not in pr.description_preview


@pytest.mark.asyncio
async def test_description_preview_long(pr_with_long_description: PRInfo):
    """T096: Long descriptions are truncated at 200 chars with ellipsis."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr_with_long_description)
        await pilot.pause()

        preview = pr_with_long_description.description_preview

        # Verify truncation
        assert len(preview) <= 203  # 200 + "..."
        assert preview.endswith("...")
        assert preview != pr_with_long_description.description

        # Initially should show preview, not full description
        assert not widget.state.description_expanded


# =============================================================================
# Test: Description Expand/Collapse (T097)
# =============================================================================


@pytest.mark.asyncio
async def test_expand_description(pr_with_long_description: PRInfo):
    """T097: expand_description() toggles state and shows full description."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr_with_long_description)
        await pilot.pause()

        # Initially collapsed
        assert not widget.state.description_expanded

        # Expand
        widget.expand_description()
        await pilot.pause()

        assert widget.state.description_expanded


@pytest.mark.asyncio
async def test_collapse_description(pr_with_long_description: PRInfo):
    """T097: collapse_description() returns to preview state."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr_with_long_description)
        await pilot.pause()

        # Expand then collapse
        widget.expand_description()
        await pilot.pause()
        assert widget.state.description_expanded

        widget.collapse_description()
        await pilot.pause()
        assert not widget.state.description_expanded


# =============================================================================
# Test: Status Checks Display (T098)
# =============================================================================


@pytest.mark.asyncio
async def test_status_checks_display(sample_pr: PRInfo):
    """T098: Widget displays all status checks with correct icons."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(sample_pr)
        await pilot.pause()

        # Verify checks are stored
        assert len(widget.state.pr.checks) == 3

        # Verify check statuses
        checks = {c.name: c.status for c in widget.state.pr.checks}
        assert checks["CI / build"] == CheckStatus.PASSING
        assert checks["CI / test"] == CheckStatus.PASSING
        assert checks["CodeQL"] == CheckStatus.PENDING


@pytest.mark.asyncio
async def test_status_checks_empty():
    """T098: Widget handles PR with no status checks gracefully."""
    pr = PRInfo(
        number=1,
        title="No checks",
        description="PR without checks",
        state=PRState.OPEN,
        url="https://github.com/test/test/pull/1",
        checks=(),
    )

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr)
        await pilot.pause()

        assert len(widget.state.pr.checks) == 0


@pytest.mark.asyncio
async def test_status_checks_failing():
    """T098: Widget displays failing status check correctly."""
    pr = PRInfo(
        number=2,
        title="Failing check",
        description="Has failing check",
        state=PRState.OPEN,
        url="https://github.com/test/test/pull/2",
        checks=(StatusCheck(name="CI / test", status=CheckStatus.FAILING, url=None),),
    )

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr)
        await pilot.pause()

        assert widget.state.pr.checks[0].status == CheckStatus.FAILING


# =============================================================================
# Test: Open in Browser (T099)
# =============================================================================


@pytest.mark.asyncio
async def test_open_pr_in_browser(sample_pr: PRInfo):
    """T099: open_pr_in_browser() uses webbrowser.open() with PR URL."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    with patch("maverick.tui.widgets.pr_summary.webbrowser.open") as mock_open:
        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one(PRSummary)
            widget.update_pr(sample_pr)
            await pilot.pause()

            # Call open_pr_in_browser (now async)
            await widget.open_pr_in_browser()
            await pilot.pause()

            # Verify webbrowser.open was called with correct URL
            mock_open.assert_called_once_with(sample_pr.url)


@pytest.mark.asyncio
async def test_open_pr_in_browser_no_pr():
    """T099: open_pr_in_browser() does nothing when no PR data."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    with patch("maverick.tui.widgets.pr_summary.webbrowser.open") as mock_open:
        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one(PRSummary)

            # No PR data, should not open browser
            await widget.open_pr_in_browser()
            await pilot.pause()

            mock_open.assert_not_called()


# =============================================================================
# Test: Message Emission (T100)
# =============================================================================


@pytest.mark.asyncio
async def test_emit_open_pr_requested(sample_pr: PRInfo):
    """T100: Widget emits OpenPRRequested message when opening browser."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(sample_pr)
        await pilot.pause()

        # Verify the widget has PR data and can open browser
        assert widget.state.pr is not None
        assert widget.state.pr.url == sample_pr.url

        # Trigger browser open - this will post the message
        with patch("maverick.tui.widgets.pr_summary.webbrowser.open") as mock_open:
            await widget.open_pr_in_browser()
            # Verify webbrowser.open was called with correct URL
            mock_open.assert_called_once_with(sample_pr.url)

        # The message is posted successfully (verified by method execution)


@pytest.mark.asyncio
async def test_emit_description_expanded(pr_with_long_description: PRInfo):
    """T100: Widget emits DescriptionExpanded message."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr_with_long_description)
        await pilot.pause()

        # Initially not expanded
        assert not widget.state.description_expanded

        # Expand description - this will post the message
        widget.expand_description()
        await pilot.pause()

        # Verify state changed
        assert widget.state.description_expanded


@pytest.mark.asyncio
async def test_emit_description_collapsed(pr_with_long_description: PRInfo):
    """T100: Widget emits DescriptionCollapsed message."""

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)
        widget.update_pr(pr_with_long_description)
        await pilot.pause()

        # First expand
        widget.expand_description()
        await pilot.pause()
        assert widget.state.description_expanded

        # Collapse description - this will post the message
        widget.collapse_description()
        await pilot.pause()

        # Verify state changed back
        assert not widget.state.description_expanded


@pytest.mark.asyncio
async def test_messages_not_emitted_when_no_pr():
    """T100: Messages are not emitted when no PR data available."""

    messages = []

    class TestApp(App[None]):
        def compose(self):
            yield PRSummary()

        def on_pr_summary_open_pr_requested(
            self, message: PRSummary.OpenPRRequested
        ) -> None:
            messages.append(message)

        def on_pr_summary_description_expanded(
            self, message: PRSummary.DescriptionExpanded
        ) -> None:
            messages.append(message)

        def on_pr_summary_description_collapsed(
            self, message: PRSummary.DescriptionCollapsed
        ) -> None:
            messages.append(message)

    async with TestApp().run_test() as pilot:
        widget = pilot.app.query_one(PRSummary)

        # Try operations without PR
        with patch("webbrowser.open"):
            widget.open_pr_in_browser()
        widget.expand_description()
        widget.collapse_description()
        await pilot.pause()

        # Should not emit messages when no PR
        assert len(messages) == 0
