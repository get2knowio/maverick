"""Unit tests for IssueList widget.

This test module covers the IssueList and IssueListItem widgets for the
RefuelScreen (013-tui-interactive-screens Phase 6). These widgets provide
GitHub issue display and selection with keyboard navigation.

Test coverage includes:
- IssueListItem rendering and selection
- IssueList initialization and display
- Keyboard navigation (j/k for vim-style)
- Selection toggling (space)
- Bulk selection (select all, deselect all)
- Message posting
"""

from __future__ import annotations

import pytest

from maverick.tui.models import GitHubIssue

# =============================================================================
# Mock IssueList Classes
# =============================================================================
# Note: These are placeholder mocks until the actual widgets are implemented.
# The tests define the expected behavior based on the contracts.


class MockIssueListItem:
    """Mock IssueListItem for testing."""

    def __init__(self, issue_number: int, title: str, labels: tuple[str, ...]) -> None:
        self.issue_number = issue_number
        self.title = title
        self.labels = labels
        self.selected = False
        self._on_toggled = None

    def toggle_selection(self) -> None:
        """Toggle selection state."""
        self.selected = not self.selected
        if self._on_toggled:
            self._on_toggled(self.issue_number, self.selected)

    def set_focus(self, focused: bool) -> None:
        """Set focus state."""
        self.focused = focused


class MockIssueList:
    """Mock IssueList for testing."""

    def __init__(self) -> None:
        self.issues: list[GitHubIssue] = []
        self.items: list[MockIssueListItem] = []
        self.focused_index = 0
        self.selected_count = 0
        self._on_selection_changed = None

    def set_issues(self, issues: list[GitHubIssue]) -> None:
        """Set the list of issues."""
        self.issues = issues
        self.items = [
            MockIssueListItem(issue.number, issue.title, issue.labels)
            for issue in issues
        ]
        for item in self.items:
            item._on_toggled = self._handle_item_toggled

    def _handle_item_toggled(self, issue_number: int, selected: bool) -> None:
        """Handle item selection toggle."""
        self.selected_count = sum(1 for item in self.items if item.selected)
        if self._on_selection_changed:
            self._on_selection_changed(issue_number, selected)

    def move_down(self) -> None:
        """Move focus down."""
        if self.focused_index < len(self.items) - 1:
            self.focused_index += 1

    def move_up(self) -> None:
        """Move focus up."""
        if self.focused_index > 0:
            self.focused_index -= 1

    def toggle_current(self) -> None:
        """Toggle selection of focused item."""
        if 0 <= self.focused_index < len(self.items):
            self.items[self.focused_index].toggle_selection()

    def select_all(self) -> None:
        """Select all items."""
        for item in self.items:
            if not item.selected:
                item.selected = True
        self.selected_count = len(self.items)
        if self._on_selection_changed:
            self._on_selection_changed(-1, True)

    def select_none(self) -> None:
        """Deselect all items."""
        for item in self.items:
            if item.selected:
                item.selected = False
        self.selected_count = 0
        if self._on_selection_changed:
            self._on_selection_changed(-1, False)

    def get_selected_issues(self) -> list[GitHubIssue]:
        """Get all selected issues."""
        return [self.issues[i] for i, item in enumerate(self.items) if item.selected]


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
def issue_list_item() -> MockIssueListItem:
    """Create an IssueListItem instance for testing."""
    return MockIssueListItem(
        issue_number=101,
        title="Fix memory leak",
        labels=("bug", "tech-debt"),
    )


@pytest.fixture
def issue_list() -> MockIssueList:
    """Create an IssueList instance for testing."""
    return MockIssueList()


# =============================================================================
# IssueListItem Tests
# =============================================================================


class TestIssueListItemInitialization:
    """Tests for IssueListItem initialization."""

    def test_init_with_issue_data(self, issue_list_item: MockIssueListItem) -> None:
        """IssueListItem initializes with issue data."""
        assert issue_list_item.issue_number == 101
        assert issue_list_item.title == "Fix memory leak"
        assert issue_list_item.labels == ("bug", "tech-debt")
        assert issue_list_item.selected is False

    def test_init_creates_unselected_item(self) -> None:
        """IssueListItem starts in unselected state."""
        item = MockIssueListItem(123, "Test issue", ("label1",))
        assert item.selected is False


class TestIssueListItemSelection:
    """Tests for IssueListItem selection."""

    def test_toggle_selection_from_unselected(
        self, issue_list_item: MockIssueListItem
    ) -> None:
        """Toggle changes from unselected to selected."""
        assert issue_list_item.selected is False
        issue_list_item.toggle_selection()
        assert issue_list_item.selected is True

    def test_toggle_selection_from_selected(self) -> None:
        """Toggle changes from selected to unselected."""
        item = MockIssueListItem(123, "Test", ())
        item.selected = True
        item.toggle_selection()
        assert item.selected is False

    def test_toggle_posts_message(self, issue_list_item: MockIssueListItem) -> None:
        """Toggle selection posts Toggled message."""
        messages = []

        def capture_message(issue_number: int, selected: bool) -> None:
            messages.append((issue_number, selected))

        issue_list_item._on_toggled = capture_message
        issue_list_item.toggle_selection()

        assert len(messages) == 1
        assert messages[0] == (101, True)


# =============================================================================
# IssueList Tests
# =============================================================================


class TestIssueListInitialization:
    """Tests for IssueList initialization."""

    def test_init_with_defaults(self, issue_list: MockIssueList) -> None:
        """IssueList initializes empty."""
        assert len(issue_list.issues) == 0
        assert len(issue_list.items) == 0
        assert issue_list.focused_index == 0
        assert issue_list.selected_count == 0

    def test_set_issues_creates_items(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """set_issues creates IssueListItem for each issue."""
        issue_list.set_issues(sample_issues)
        assert len(issue_list.items) == 3
        assert issue_list.items[0].issue_number == 101
        assert issue_list.items[1].issue_number == 102
        assert issue_list.items[2].issue_number == 103


class TestIssueListNavigation:
    """Tests for IssueList keyboard navigation."""

    def test_move_down_increases_index(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """j key (move_down) increases focused_index."""
        issue_list.set_issues(sample_issues)
        assert issue_list.focused_index == 0
        issue_list.move_down()
        assert issue_list.focused_index == 1

    def test_move_down_at_end_no_change(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """move_down at end does not go beyond bounds."""
        issue_list.set_issues(sample_issues)
        issue_list.focused_index = 2  # Last item
        issue_list.move_down()
        assert issue_list.focused_index == 2

    def test_move_up_decreases_index(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """k key (move_up) decreases focused_index."""
        issue_list.set_issues(sample_issues)
        issue_list.focused_index = 1
        issue_list.move_up()
        assert issue_list.focused_index == 0

    def test_move_up_at_start_no_change(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """move_up at start does not go below zero."""
        issue_list.set_issues(sample_issues)
        issue_list.focused_index = 0
        issue_list.move_up()
        assert issue_list.focused_index == 0

    def test_navigate_through_all_items(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """Navigate down through all items."""
        issue_list.set_issues(sample_issues)

        # Navigate down
        assert issue_list.focused_index == 0
        issue_list.move_down()
        assert issue_list.focused_index == 1
        issue_list.move_down()
        assert issue_list.focused_index == 2

        # Navigate back up
        issue_list.move_up()
        assert issue_list.focused_index == 1
        issue_list.move_up()
        assert issue_list.focused_index == 0


class TestIssueListSelection:
    """Tests for IssueList selection operations."""

    def test_toggle_current_item(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """space key toggles current item selection."""
        issue_list.set_issues(sample_issues)
        issue_list.focused_index = 0

        assert issue_list.items[0].selected is False
        issue_list.toggle_current()
        assert issue_list.items[0].selected is True

    def test_toggle_updates_selected_count(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """Toggling updates selected_count."""
        issue_list.set_issues(sample_issues)
        assert issue_list.selected_count == 0

        issue_list.toggle_current()
        assert issue_list.selected_count == 1

        issue_list.focused_index = 1
        issue_list.toggle_current()
        assert issue_list.selected_count == 2

    def test_select_all(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """'a' key selects all items."""
        issue_list.set_issues(sample_issues)
        issue_list.select_all()

        assert issue_list.selected_count == 3
        assert all(item.selected for item in issue_list.items)

    def test_select_none(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """'n' key deselects all items."""
        issue_list.set_issues(sample_issues)
        issue_list.select_all()
        assert issue_list.selected_count == 3

        issue_list.select_none()
        assert issue_list.selected_count == 0
        assert not any(item.selected for item in issue_list.items)

    def test_get_selected_issues(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """get_selected_issues returns only selected issues."""
        issue_list.set_issues(sample_issues)

        # Select first and third issues
        issue_list.items[0].selected = True
        issue_list.items[2].selected = True

        selected = issue_list.get_selected_issues()
        assert len(selected) == 2
        assert selected[0].number == 101
        assert selected[1].number == 103


class TestIssueListSelectionMessages:
    """Tests for IssueList selection change messages."""

    def test_selection_changed_message_on_toggle(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """Selection change posts message with issue number and state."""
        issue_list.set_issues(sample_issues)
        messages = []

        def capture_message(issue_number: int, selected: bool) -> None:
            messages.append((issue_number, selected))

        issue_list._on_selection_changed = capture_message
        issue_list.toggle_current()

        assert len(messages) == 1
        assert messages[0] == (101, True)

    def test_select_all_posts_message(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """select_all posts selection changed message."""
        issue_list.set_issues(sample_issues)
        messages = []

        def capture_message(issue_number: int, selected: bool) -> None:
            messages.append((issue_number, selected))

        issue_list._on_selection_changed = capture_message
        issue_list.select_all()

        assert len(messages) == 1
        assert messages[0] == (-1, True)  # -1 indicates all items

    def test_select_none_posts_message(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """select_none posts selection changed message."""
        issue_list.set_issues(sample_issues)
        issue_list.select_all()
        messages = []

        def capture_message(issue_number: int, selected: bool) -> None:
            messages.append((issue_number, selected))

        issue_list._on_selection_changed = capture_message
        issue_list.select_none()

        assert len(messages) == 1
        assert messages[0] == (-1, False)  # -1 indicates all items


# =============================================================================
# Integration Scenarios
# =============================================================================


class TestIssueListScenarios:
    """Integration test scenarios for IssueList."""

    def test_user_selects_multiple_issues(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """User navigates and selects multiple issues."""
        issue_list.set_issues(sample_issues)

        # Select first issue
        issue_list.toggle_current()
        assert issue_list.selected_count == 1

        # Navigate and select third issue
        issue_list.move_down()
        issue_list.move_down()
        issue_list.toggle_current()
        assert issue_list.selected_count == 2

        # Get selected issues
        selected = issue_list.get_selected_issues()
        assert len(selected) == 2
        assert selected[0].number == 101
        assert selected[1].number == 103

    def test_user_selects_all_then_deselects_one(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """User selects all, then deselects specific issue."""
        issue_list.set_issues(sample_issues)

        # Select all
        issue_list.select_all()
        assert issue_list.selected_count == 3

        # Deselect second issue
        issue_list.focused_index = 1
        issue_list.toggle_current()
        assert issue_list.selected_count == 2

        # Verify selection state
        selected = issue_list.get_selected_issues()
        assert len(selected) == 2
        assert selected[0].number == 101
        assert selected[1].number == 103

    def test_user_changes_selection_multiple_times(
        self, issue_list: MockIssueList, sample_issues: list[GitHubIssue]
    ) -> None:
        """User toggles selection on same item multiple times."""
        issue_list.set_issues(sample_issues)

        # Toggle on
        issue_list.toggle_current()
        assert issue_list.selected_count == 1
        assert issue_list.items[0].selected is True

        # Toggle off
        issue_list.toggle_current()
        assert issue_list.selected_count == 0
        assert issue_list.items[0].selected is False

        # Toggle on again
        issue_list.toggle_current()
        assert issue_list.selected_count == 1
        assert issue_list.items[0].selected is True

    def test_empty_list_handles_navigation(self, issue_list: MockIssueList) -> None:
        """Empty list handles navigation gracefully."""
        # No issues loaded
        assert len(issue_list.items) == 0

        # Navigation should not raise errors
        issue_list.move_down()
        issue_list.move_up()
        issue_list.toggle_current()

        assert issue_list.focused_index == 0
        assert issue_list.selected_count == 0
