"""Unit tests for RefuelScreen.

This test module covers the RefuelScreen for tech debt issue processing
(013-tui-interactive-screens Phase 6).

Test coverage includes:
- Screen initialization
- Label filtering
- Issue fetching
- Issue selection
- Configuration (limit, parallel mode)
- Start button state
- Results display
- Error handling
"""

from __future__ import annotations

import pytest

from maverick.tui.models import (
    GitHubIssue,
    IssueSelectionItem,
    ProcessingMode,
    RefuelResultItem,
    RefuelScreenState,
)

# =============================================================================
# Mock RefuelScreen
# =============================================================================


class MockRefuelScreen:
    """Mock RefuelScreen for testing."""

    def __init__(self) -> None:
        self.state = RefuelScreenState()
        self._fetch_callback = None
        self._start_callback = None

    def set_label_filter(self, label: str) -> None:
        """Set the label filter."""
        self.state = RefuelScreenState(
            label_filter=label,
            issue_limit=self.state.issue_limit,
            processing_mode=self.state.processing_mode,
            issues=self.state.issues,
            focused_index=self.state.focused_index,
            is_fetching=self.state.is_fetching,
            is_processing=self.state.is_processing,
            results=self.state.results,
            error_message=self.state.error_message,
        )

    def set_issue_limit(self, limit: int) -> None:
        """Set the issue limit."""
        self.state = RefuelScreenState(
            label_filter=self.state.label_filter,
            issue_limit=limit,
            processing_mode=self.state.processing_mode,
            issues=self.state.issues,
            focused_index=self.state.focused_index,
            is_fetching=self.state.is_fetching,
            is_processing=self.state.is_processing,
            results=self.state.results,
            error_message=self.state.error_message,
        )

    def set_processing_mode(self, mode: ProcessingMode) -> None:
        """Set the processing mode."""
        self.state = RefuelScreenState(
            label_filter=self.state.label_filter,
            issue_limit=self.state.issue_limit,
            processing_mode=mode,
            issues=self.state.issues,
            focused_index=self.state.focused_index,
            is_fetching=self.state.is_fetching,
            is_processing=self.state.is_processing,
            results=self.state.results,
            error_message=self.state.error_message,
        )

    def toggle_selection(self, index: int) -> None:
        """Toggle issue selection."""
        if 0 <= index < len(self.state.issues):
            items = list(self.state.issues)
            item = items[index]
            items[index] = IssueSelectionItem(
                issue=item.issue,
                selected=not item.selected,
            )
            self.state = RefuelScreenState(
                label_filter=self.state.label_filter,
                issue_limit=self.state.issue_limit,
                processing_mode=self.state.processing_mode,
                issues=tuple(items),
                focused_index=self.state.focused_index,
                is_fetching=self.state.is_fetching,
                is_processing=self.state.is_processing,
                results=self.state.results,
                error_message=self.state.error_message,
            )

    async def fetch_issues(self, label: str) -> None:
        """Fetch issues from GitHub."""
        self.state = RefuelScreenState(
            label_filter=self.state.label_filter,
            issue_limit=self.state.issue_limit,
            processing_mode=self.state.processing_mode,
            issues=self.state.issues,
            focused_index=self.state.focused_index,
            is_fetching=True,
            is_processing=self.state.is_processing,
            results=self.state.results,
            error_message=self.state.error_message,
        )

        if self._fetch_callback:
            issues = await self._fetch_callback(label)
            self.state = RefuelScreenState(
                label_filter=self.state.label_filter,
                issue_limit=self.state.issue_limit,
                processing_mode=self.state.processing_mode,
                issues=tuple(IssueSelectionItem(issue=issue) for issue in issues),
                focused_index=self.state.focused_index,
                is_fetching=False,
                is_processing=self.state.is_processing,
                results=self.state.results,
                error_message=self.state.error_message,
            )

    async def start_workflow(self) -> None:
        """Start the refuel workflow."""
        if not self.state.can_start:
            return

        self.state = RefuelScreenState(
            label_filter=self.state.label_filter,
            issue_limit=self.state.issue_limit,
            processing_mode=self.state.processing_mode,
            issues=self.state.issues,
            focused_index=self.state.focused_index,
            is_fetching=self.state.is_fetching,
            is_processing=True,
            results=self.state.results,
            error_message=self.state.error_message,
        )

        if self._start_callback:
            results = await self._start_callback()
            self.state = RefuelScreenState(
                label_filter=self.state.label_filter,
                issue_limit=self.state.issue_limit,
                processing_mode=self.state.processing_mode,
                issues=self.state.issues,
                focused_index=self.state.focused_index,
                is_fetching=self.state.is_fetching,
                is_processing=False,
                results=tuple(results),
                error_message=self.state.error_message,
            )


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_issues() -> list[GitHubIssue]:
    """Create sample GitHub issues for testing."""
    return [
        GitHubIssue(
            number=101,
            title="Fix memory leak in agent cleanup",
            labels=("bug", "tech-debt"),
            url="https://github.com/test/repo/issues/101",
            state="open",
        ),
        GitHubIssue(
            number=102,
            title="Refactor validation workflow",
            labels=("tech-debt", "refactor"),
            url="https://github.com/test/repo/issues/102",
            state="open",
        ),
        GitHubIssue(
            number=103,
            title="Update deprecated API calls",
            labels=("tech-debt",),
            url="https://github.com/test/repo/issues/103",
            state="open",
        ),
    ]


@pytest.fixture
def refuel_screen() -> MockRefuelScreen:
    """Create a RefuelScreen instance for testing."""
    return MockRefuelScreen()


# =============================================================================
# RefuelScreen Initialization Tests
# =============================================================================


class TestRefuelScreenInitialization:
    """Tests for RefuelScreen initialization."""

    def test_init_with_defaults(self, refuel_screen: MockRefuelScreen) -> None:
        """RefuelScreen initializes with default state."""
        assert refuel_screen.state.label_filter == ""
        assert refuel_screen.state.issue_limit == 3
        assert refuel_screen.state.processing_mode == ProcessingMode.PARALLEL
        assert len(refuel_screen.state.issues) == 0
        assert refuel_screen.state.focused_index == 0
        assert refuel_screen.state.is_fetching is False
        assert refuel_screen.state.is_processing is False
        assert refuel_screen.state.results is None
        assert refuel_screen.state.error_message is None

    def test_initial_state_cannot_start(self, refuel_screen: MockRefuelScreen) -> None:
        """Initial state has Start button disabled."""
        assert refuel_screen.state.can_start is False
        assert refuel_screen.state.selected_count == 0


# =============================================================================
# RefuelScreen Configuration Tests
# =============================================================================


class TestRefuelScreenConfiguration:
    """Tests for RefuelScreen configuration."""

    def test_set_label_filter(self, refuel_screen: MockRefuelScreen) -> None:
        """Setting label filter updates state."""
        refuel_screen.set_label_filter("tech-debt")
        assert refuel_screen.state.label_filter == "tech-debt"

    def test_set_issue_limit(self, refuel_screen: MockRefuelScreen) -> None:
        """Setting issue limit updates state."""
        refuel_screen.set_issue_limit(5)
        assert refuel_screen.state.issue_limit == 5

    def test_issue_limit_bounds(self, refuel_screen: MockRefuelScreen) -> None:
        """Issue limit respects 1-10 bounds."""
        refuel_screen.set_issue_limit(1)
        assert refuel_screen.state.issue_limit == 1

        refuel_screen.set_issue_limit(10)
        assert refuel_screen.state.issue_limit == 10

    def test_set_processing_mode_parallel(
        self, refuel_screen: MockRefuelScreen
    ) -> None:
        """Setting processing mode to parallel."""
        refuel_screen.set_processing_mode(ProcessingMode.PARALLEL)
        assert refuel_screen.state.processing_mode == ProcessingMode.PARALLEL

    def test_set_processing_mode_sequential(
        self, refuel_screen: MockRefuelScreen
    ) -> None:
        """Setting processing mode to sequential."""
        refuel_screen.set_processing_mode(ProcessingMode.SEQUENTIAL)
        assert refuel_screen.state.processing_mode == ProcessingMode.SEQUENTIAL

    def test_toggle_processing_mode(self, refuel_screen: MockRefuelScreen) -> None:
        """Toggling between parallel and sequential modes."""
        # Start with parallel
        assert refuel_screen.state.processing_mode == ProcessingMode.PARALLEL

        # Toggle to sequential
        refuel_screen.set_processing_mode(ProcessingMode.SEQUENTIAL)
        assert refuel_screen.state.processing_mode == ProcessingMode.SEQUENTIAL

        # Toggle back to parallel
        refuel_screen.set_processing_mode(ProcessingMode.PARALLEL)
        assert refuel_screen.state.processing_mode == ProcessingMode.PARALLEL


# =============================================================================
# RefuelScreen Issue Fetching Tests
# =============================================================================


class TestRefuelScreenIssueFetching:
    """Tests for RefuelScreen issue fetching."""

    @pytest.mark.asyncio
    async def test_fetch_issues_sets_fetching_flag(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Fetching issues sets is_fetching flag during fetch operation."""
        fetch_started = False
        fetch_done = False

        async def mock_fetch(label: str) -> list[GitHubIssue]:
            nonlocal fetch_started, fetch_done
            fetch_started = True
            # At this point in the fetch, is_fetching should be True
            assert refuel_screen.state.is_fetching is True
            fetch_done = True
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch

        # Complete fetching
        await refuel_screen.fetch_issues("tech-debt")
        assert fetch_started is True
        assert fetch_done is True
        assert refuel_screen.state.is_fetching is False

    @pytest.mark.asyncio
    async def test_fetch_issues_populates_list(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Fetching issues populates the issue list."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        await refuel_screen.fetch_issues("tech-debt")

        assert len(refuel_screen.state.issues) == 3
        assert refuel_screen.state.issues[0].issue.number == 101
        assert refuel_screen.state.issues[1].issue.number == 102
        assert refuel_screen.state.issues[2].issue.number == 103

    @pytest.mark.asyncio
    async def test_fetch_issues_with_label_filter(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Fetch issues passes label filter to gh CLI."""
        calls = []

        async def mock_fetch(label: str) -> list[GitHubIssue]:
            calls.append(label)
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen.set_label_filter("tech-debt")
        await refuel_screen.fetch_issues("tech-debt")

        assert "tech-debt" in calls

    @pytest.mark.asyncio
    async def test_fetch_empty_results(self, refuel_screen: MockRefuelScreen) -> None:
        """Fetching with no matching issues returns empty list."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return []

        refuel_screen._fetch_callback = mock_fetch
        await refuel_screen.fetch_issues("nonexistent-label")

        assert len(refuel_screen.state.issues) == 0
        assert refuel_screen.state.is_empty is True


# =============================================================================
# RefuelScreen Issue Selection Tests
# =============================================================================


class TestRefuelScreenIssueSelection:
    """Tests for RefuelScreen issue selection."""

    @pytest.mark.asyncio
    async def test_toggle_selection(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Toggling issue selection updates state."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        await refuel_screen.fetch_issues("tech-debt")

        # Initially unselected
        assert refuel_screen.state.issues[0].selected is False
        assert refuel_screen.state.selected_count == 0

        # Toggle on
        refuel_screen.toggle_selection(0)
        assert refuel_screen.state.issues[0].selected is True
        assert refuel_screen.state.selected_count == 1

    @pytest.mark.asyncio
    async def test_toggle_multiple_selections(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Selecting multiple issues updates selected_count."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        await refuel_screen.fetch_issues("tech-debt")

        # Select first and third issues
        refuel_screen.toggle_selection(0)
        refuel_screen.toggle_selection(2)

        assert refuel_screen.state.selected_count == 2
        assert refuel_screen.state.issues[0].selected is True
        assert refuel_screen.state.issues[1].selected is False
        assert refuel_screen.state.issues[2].selected is True

    @pytest.mark.asyncio
    async def test_deselect_issue(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Toggling selected issue deselects it."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        await refuel_screen.fetch_issues("tech-debt")

        # Select then deselect
        refuel_screen.toggle_selection(0)
        assert refuel_screen.state.selected_count == 1

        refuel_screen.toggle_selection(0)
        assert refuel_screen.state.selected_count == 0
        assert refuel_screen.state.issues[0].selected is False

    @pytest.mark.asyncio
    async def test_selected_issues_property(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """selected_issues property returns selected issues."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        await refuel_screen.fetch_issues("tech-debt")

        # Select first and third
        refuel_screen.toggle_selection(0)
        refuel_screen.toggle_selection(2)

        selected = refuel_screen.state.selected_issues
        assert len(selected) == 2
        assert selected[0].number == 101
        assert selected[1].number == 103


# =============================================================================
# RefuelScreen Start Button Tests
# =============================================================================


class TestRefuelScreenStartButton:
    """Tests for RefuelScreen start button state."""

    def test_start_button_disabled_no_selection(
        self, refuel_screen: MockRefuelScreen
    ) -> None:
        """Start button disabled when no issues selected."""
        assert refuel_screen.state.can_start is False

    @pytest.mark.asyncio
    async def test_start_button_enabled_with_selection(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Start button enabled when issues are selected."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        await refuel_screen.fetch_issues("tech-debt")
        refuel_screen.toggle_selection(0)

        assert refuel_screen.state.can_start is True

    @pytest.mark.asyncio
    async def test_start_button_disabled_while_fetching(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Start button disabled during issue fetching."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen.toggle_selection(0)

        # During fetching
        fetch_task = refuel_screen.fetch_issues("tech-debt")
        assert refuel_screen.state.can_start is False

        await fetch_task

    @pytest.mark.asyncio
    async def test_start_button_disabled_while_processing(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Start button disabled during workflow processing."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        async def mock_start() -> list[RefuelResultItem]:
            # During processing, can_start should be False
            assert refuel_screen.state.is_processing is True
            assert refuel_screen.state.can_start is False
            return []

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen._start_callback = mock_start

        await refuel_screen.fetch_issues("tech-debt")
        refuel_screen.toggle_selection(0)

        # Execute workflow
        await refuel_screen.start_workflow()


# =============================================================================
# RefuelScreen Workflow Execution Tests
# =============================================================================


class TestRefuelScreenWorkflowExecution:
    """Tests for RefuelScreen workflow execution."""

    @pytest.mark.asyncio
    async def test_start_workflow_sets_processing_flag(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Starting workflow sets is_processing flag during execution."""
        processing_started = False

        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        async def mock_start() -> list[RefuelResultItem]:
            nonlocal processing_started
            processing_started = True
            # During processing, is_processing should be True
            assert refuel_screen.state.is_processing is True
            return [
                RefuelResultItem(
                    issue_number=101,
                    success=True,
                    pr_url="https://github.com/test/repo/pull/1",
                )
            ]

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen._start_callback = mock_start

        await refuel_screen.fetch_issues("tech-debt")
        refuel_screen.toggle_selection(0)

        # Execute workflow
        await refuel_screen.start_workflow()
        assert processing_started is True
        assert refuel_screen.state.is_processing is False

    @pytest.mark.asyncio
    async def test_workflow_results_stored(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Workflow results are stored in state."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        async def mock_start() -> list[RefuelResultItem]:
            return [
                RefuelResultItem(
                    issue_number=101,
                    success=True,
                    pr_url="https://github.com/test/repo/pull/1",
                ),
                RefuelResultItem(
                    issue_number=102,
                    success=False,
                    error_message="Failed to apply fix",
                ),
            ]

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen._start_callback = mock_start

        await refuel_screen.fetch_issues("tech-debt")
        refuel_screen.toggle_selection(0)
        refuel_screen.toggle_selection(1)

        await refuel_screen.start_workflow()

        assert refuel_screen.state.results is not None
        assert len(refuel_screen.state.results) == 2
        assert refuel_screen.state.results[0].success is True
        assert refuel_screen.state.results[1].success is False

    @pytest.mark.asyncio
    async def test_successful_workflow_with_pr_links(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Successful workflow includes PR links."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        async def mock_start() -> list[RefuelResultItem]:
            return [
                RefuelResultItem(
                    issue_number=101,
                    success=True,
                    pr_url="https://github.com/test/repo/pull/1",
                )
            ]

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen._start_callback = mock_start

        await refuel_screen.fetch_issues("tech-debt")
        refuel_screen.toggle_selection(0)
        await refuel_screen.start_workflow()

        assert refuel_screen.state.results[0].pr_url is not None
        assert "pull/1" in refuel_screen.state.results[0].pr_url

    @pytest.mark.asyncio
    async def test_failed_workflow_with_error_message(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Failed workflow includes error message."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        async def mock_start() -> list[RefuelResultItem]:
            return [
                RefuelResultItem(
                    issue_number=101,
                    success=False,
                    error_message="Failed to create branch",
                )
            ]

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen._start_callback = mock_start

        await refuel_screen.fetch_issues("tech-debt")
        refuel_screen.toggle_selection(0)
        await refuel_screen.start_workflow()

        assert refuel_screen.state.results[0].error_message is not None
        assert "Failed to create branch" in refuel_screen.state.results[0].error_message


# =============================================================================
# RefuelScreen State Properties Tests
# =============================================================================


class TestRefuelScreenStateProperties:
    """Tests for RefuelScreenState computed properties."""

    def test_is_empty_no_issues(self, refuel_screen: MockRefuelScreen) -> None:
        """is_empty is True when no issues loaded."""
        assert refuel_screen.state.is_empty is True

    @pytest.mark.asyncio
    async def test_is_empty_with_issues(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """is_empty is False when issues are loaded."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        refuel_screen._fetch_callback = mock_fetch
        await refuel_screen.fetch_issues("tech-debt")

        assert refuel_screen.state.is_empty is False

    def test_has_results_no_results(self, refuel_screen: MockRefuelScreen) -> None:
        """has_results is False when no results."""
        assert refuel_screen.state.has_results is False

    @pytest.mark.asyncio
    async def test_has_results_with_results(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """has_results is True after workflow completion."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        async def mock_start() -> list[RefuelResultItem]:
            return [
                RefuelResultItem(issue_number=101, success=True)
            ]

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen._start_callback = mock_start

        await refuel_screen.fetch_issues("tech-debt")
        refuel_screen.toggle_selection(0)
        await refuel_screen.start_workflow()

        assert refuel_screen.state.has_results is True


# =============================================================================
# Integration Scenarios
# =============================================================================


class TestRefuelScreenScenarios:
    """Integration test scenarios for RefuelScreen."""

    @pytest.mark.asyncio
    async def test_complete_refuel_workflow(
        self, refuel_screen: MockRefuelScreen, sample_issues: list[GitHubIssue]
    ) -> None:
        """Complete refuel workflow from configuration to results."""
        async def mock_fetch(label: str) -> list[GitHubIssue]:
            return sample_issues

        async def mock_start() -> list[RefuelResultItem]:
            return [
                RefuelResultItem(
                    issue_number=101,
                    success=True,
                    pr_url="https://github.com/test/repo/pull/1",
                ),
                RefuelResultItem(
                    issue_number=103,
                    success=True,
                    pr_url="https://github.com/test/repo/pull/2",
                ),
            ]

        refuel_screen._fetch_callback = mock_fetch
        refuel_screen._start_callback = mock_start

        # 1. Configure
        refuel_screen.set_label_filter("tech-debt")
        refuel_screen.set_issue_limit(5)
        refuel_screen.set_processing_mode(ProcessingMode.PARALLEL)

        # 2. Fetch issues
        await refuel_screen.fetch_issues("tech-debt")
        assert len(refuel_screen.state.issues) == 3

        # 3. Select issues
        refuel_screen.toggle_selection(0)
        refuel_screen.toggle_selection(2)
        assert refuel_screen.state.selected_count == 2

        # 4. Start workflow
        assert refuel_screen.state.can_start is True
        await refuel_screen.start_workflow()

        # 5. Verify results
        assert refuel_screen.state.has_results is True
        assert len(refuel_screen.state.results) == 2
        assert all(r.success for r in refuel_screen.state.results)
