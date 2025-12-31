"""GitHub issue list widget for RefuelScreen."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Checkbox, Static

from maverick.tui.models import GitHubIssue

__all__ = ["IssueListItem", "IssueList"]


class IssueListItem(Widget):
    """A single selectable issue in the list.

    Displays an issue with checkbox, number, title, and labels.
    Supports selection toggle and focus state.

    Attributes:
        issue_number: GitHub issue number
        title: Issue title
        labels: Issue labels tuple
        selected: Whether this item is selected
    """

    DEFAULT_CSS = """
    IssueListItem {
        height: auto;
        layout: horizontal;
        padding: 0 1;
        min-height: 3;
    }

    IssueListItem.focused {
        background: $accent 20%;
    }

    IssueListItem Checkbox {
        width: 3;
    }

    IssueListItem .issue-number {
        width: 8;
        color: $text-muted;
        content-align: right middle;
    }

    IssueListItem .issue-title {
        width: 1fr;
        padding: 0 1;
    }

    IssueListItem .issue-labels {
        width: auto;
        color: $text-dim;
        padding: 0 1;
    }
    """

    # Reactive state
    selected: reactive[bool] = reactive(False)

    class Toggled(Message):
        """Posted when selection is toggled.

        Attributes:
            issue_number: The issue number that was toggled
            selected: New selection state
        """

        def __init__(self, issue_number: int, selected: bool) -> None:
            self.issue_number = issue_number
            self.selected = selected
            super().__init__()

    def __init__(
        self, issue_number: int, title: str, labels: tuple[str, ...], **kwargs: Any
    ) -> None:
        """Initialize issue list item.

        Args:
            issue_number: GitHub issue number
            title: Issue title
            labels: Issue labels tuple
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.issue_number = issue_number
        self.title = title
        self.labels = labels

    def compose(self) -> ComposeResult:
        """Compose the item widgets."""
        yield Checkbox("", id=f"check-{self.issue_number}", value=self.selected)
        yield Static(f"#{self.issue_number}", classes="issue-number")
        yield Static(self.title, classes="issue-title")
        if self.labels:
            yield Static(f"[{', '.join(self.labels)}]", classes="issue-labels")

    def toggle_selection(self) -> None:
        """Toggle selection state and post message."""
        self.selected = not self.selected
        # Update checkbox
        try:
            checkbox = self.query_one(f"#check-{self.issue_number}", Checkbox)
            checkbox.value = self.selected
        except Exception:
            pass
        self.post_message(self.Toggled(self.issue_number, self.selected))

    def watch_selected(self, old_selected: bool, selected: bool) -> None:
        """Update checkbox when selected state changes.

        Args:
            old_selected: Previous selected state
            selected: New selected state
        """
        try:
            checkbox = self.query_one(f"#check-{self.issue_number}", Checkbox)
            checkbox.value = selected
        except Exception:
            # Not mounted yet
            pass

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox change events.

        Args:
            event: The checkbox changed event
        """
        if event.checkbox.id == f"check-{self.issue_number}":
            self.selected = event.value
            self.post_message(self.Toggled(self.issue_number, self.selected))


class IssueList(Widget):
    """List of GitHub issues with selection support.

    Displays a scrollable list of issues with keyboard navigation
    and selection. Supports vim-style j/k navigation and bulk operations.

    Attributes:
        focused_index: Index of currently focused item
        items: List of issue list items
    """

    DEFAULT_CSS = """
    IssueList {
        height: 1fr;
        border: solid $primary;
        background: $surface;
    }

    IssueList Vertical {
        height: auto;
    }

    IssueList .empty-message {
        padding: 2;
        color: $text-muted;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("space", "toggle_selection", "Select", show=True),
        Binding("a", "select_all", "Select All", show=True),
        Binding("n", "select_none", "Deselect All", show=True),
    ]

    # Reactive state
    focused_index: reactive[int] = reactive(0)

    class SelectionChanged(Message):
        """Posted when selection changes.

        Attributes:
            issue_number: The issue number that changed (-1 for bulk operations)
            selected: New selection state
            selected_count: Total number of selected issues
        """

        def __init__(
            self, issue_number: int, selected: bool, selected_count: int
        ) -> None:
            self.issue_number = issue_number
            self.selected = selected
            self.selected_count = selected_count
            super().__init__()

    def __init__(self, **kwargs: Any) -> None:
        """Initialize issue list.

        Args:
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.issues: list[GitHubIssue] = []
        self.items: list[IssueListItem] = []

    def compose(self) -> ComposeResult:
        """Compose the list container."""
        with Vertical():
            yield Static("No issues to display", classes="empty-message")

    def set_issues(self, issues: list[GitHubIssue]) -> None:
        """Set the list of issues.

        Args:
            issues: List of GitHub issues to display
        """
        self.issues = issues

        # Clear existing items
        container = self.query_one(Vertical)
        container.remove_children()
        self.items = []

        if not issues:
            container.mount(Static("No issues to display", classes="empty-message"))
            return

        # Create and mount new items
        for issue in issues:
            item = IssueListItem(issue.number, issue.title, issue.labels)
            self.items.append(item)
            container.mount(item)

        # Reset focus
        self.focused_index = 0
        self._update_focus()

    def action_move_down(self) -> None:
        """Move focus down (j key)."""
        if self.focused_index < len(self.items) - 1:
            self.focused_index += 1
            self._update_focus()

    def action_move_up(self) -> None:
        """Move focus up (k key)."""
        if self.focused_index > 0:
            self.focused_index -= 1
            self._update_focus()

    def action_toggle_selection(self) -> None:
        """Toggle selection of focused item (space key)."""
        if 0 <= self.focused_index < len(self.items):
            self.items[self.focused_index].toggle_selection()

    def action_select_all(self) -> None:
        """Select all items (a key)."""
        for item in self.items:
            if not item.selected:
                item.selected = True

        selected_count = len(self.items)
        self.post_message(self.SelectionChanged(-1, True, selected_count))

    def action_select_none(self) -> None:
        """Deselect all items (n key)."""
        for item in self.items:
            if item.selected:
                item.selected = False

        self.post_message(self.SelectionChanged(-1, False, 0))

    def get_selected_issues(self) -> list[GitHubIssue]:
        """Get all selected issues.

        Returns:
            List of selected GitHub issues
        """
        return [self.issues[i] for i, item in enumerate(self.items) if item.selected]

    def get_selected_count(self) -> int:
        """Get count of selected issues.

        Returns:
            Number of selected issues
        """
        return sum(1 for item in self.items if item.selected)

    def _update_focus(self) -> None:
        """Update focus state on items."""
        for i, item in enumerate(self.items):
            if i == self.focused_index:
                item.add_class("focused")
            else:
                item.remove_class("focused")

    def on_issue_list_item_toggled(self, event: IssueListItem.Toggled) -> None:
        """Handle item toggle events.

        Args:
            event: The item toggled event
        """
        selected_count = self.get_selected_count()
        self.post_message(
            self.SelectionChanged(event.issue_number, event.selected, selected_count)
        )
