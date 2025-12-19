"""Result summary widget for RefuelScreen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from maverick.tui.models import RefuelResultItem

__all__ = ["ResultSummary"]


class ResultSummary(Widget):
    """Summary of refuel workflow results.

    Displays success/failure status for each processed issue with
    PR links for successful fixes and error messages for failures.

    Attributes:
        results: Tuple of result items to display
        expanded_index: Index of expanded result (for error details)
    """

    DEFAULT_CSS = """
    ResultSummary {
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1;
    }

    ResultSummary .title {
        text-align: center;
        color: $text;
        margin-bottom: 1;
    }

    ResultSummary .result-item {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    ResultSummary .result-success {
        color: $success;
    }

    ResultSummary .result-failure {
        color: $error;
    }

    ResultSummary .result-pr-link {
        color: $accent;
        text-style: underline;
    }

    ResultSummary .result-error {
        color: $error;
        padding-left: 2;
    }

    ResultSummary .empty-message {
        padding: 2;
        color: $text-muted;
        text-align: center;
    }

    ResultSummary .summary-stats {
        margin-top: 1;
        padding-top: 1;
        border-top: solid $primary;
        text-align: center;
        color: $text-muted;
    }

    ResultSummary .success-count {
        color: $success;
    }

    ResultSummary .failure-count {
        color: $error;
    }
    """

    BINDINGS = [
        Binding("enter", "open_pr", "Open PR", show=False),
    ]

    # Reactive state
    results: reactive[tuple[RefuelResultItem, ...] | None] = reactive(None)
    expanded_index: reactive[int] = reactive(-1)

    class PRLinkClicked(Message):
        """Posted when a PR link is clicked.

        Attributes:
            pr_url: URL to the pull request
        """

        def __init__(self, pr_url: str) -> None:
            self.pr_url = pr_url
            super().__init__()

    def compose(self) -> ComposeResult:
        """Compose the summary widgets."""
        with Vertical():
            yield Static("[bold]Workflow Results[/bold]", classes="title")
            yield Static("No results yet", classes="empty-message")

    def set_results(self, results: tuple[RefuelResultItem, ...]) -> None:
        """Set the results to display.

        Args:
            results: Tuple of result items
        """
        self.results = results
        self._render_results()

    def _render_results(self) -> None:
        """Render the results display."""
        container = self.query_one(Vertical)
        container.remove_children()

        # Title
        container.mount(Static("[bold]Workflow Results[/bold]", classes="title"))

        if not self.results:
            container.mount(Static("No results yet", classes="empty-message"))
            return

        # Render each result
        for result in self.results:
            result_text = self._format_result(result)
            container.mount(Static(result_text, classes="result-item"))

        # Summary statistics
        success_count = sum(1 for r in self.results if r.success)
        failure_count = len(self.results) - success_count

        stats_text = (
            f"[b]Summary:[/b] "
            f"[.success-count]{success_count} succeeded[/] / "
            f"[.failure-count]{failure_count} failed[/]"
        )
        container.mount(Static(stats_text, classes="summary-stats"))

    def _format_result(self, result: RefuelResultItem) -> str:
        """Format a single result item.

        Args:
            result: Result item to format

        Returns:
            Formatted result string with markup
        """
        if result.success:
            status = f"[.result-success]✓[/] Issue #{result.issue_number}"
            if result.pr_url:
                status += f"\n  [.result-pr-link]{result.pr_url}[/]"
            return status
        else:
            status = f"[.result-failure]✗[/] Issue #{result.issue_number}"
            if result.error_message:
                status += f"\n  [.result-error]{result.error_message}[/]"
            return status

    def get_success_count(self) -> int:
        """Get count of successful results.

        Returns:
            Number of successful results
        """
        if not self.results:
            return 0
        return sum(1 for r in self.results if r.success)

    def get_failure_count(self) -> int:
        """Get count of failed results.

        Returns:
            Number of failed results
        """
        if not self.results:
            return 0
        return sum(1 for r in self.results if not r.success)

    def watch_results(
        self,
        old_results: tuple[RefuelResultItem, ...] | None,
        new_results: tuple[RefuelResultItem, ...] | None,
    ) -> None:
        """Update display when results change.

        Args:
            old_results: Previous results
            new_results: New results
        """
        self._render_results()

    def action_open_pr(self) -> None:
        """Open PR link for focused result."""
        # This would be implemented with focus tracking
        # For now, just a placeholder action
        pass
