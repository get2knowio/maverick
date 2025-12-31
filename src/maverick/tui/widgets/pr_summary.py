"""PRSummary widget for displaying pull request metadata.

Feature: 012-workflow-widgets
User Story 5: PRSummary Widget (T093-T108)

Displays:
- PR title and number
- PR state icon (open, merged, closed)
- Truncated description preview (expandable)
- Status checks with pass/fail/pending icons
- Link to open in browser
- Loading and empty states
"""

from __future__ import annotations

import webbrowser
from dataclasses import replace

from rich.console import RenderableType
from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from maverick.tui.models import CheckStatus, PRInfo, PRState, PRSummaryState


class PRSummary(Widget):
    """Widget displaying PR metadata and status.

    Protocol Implementation: PRSummaryProtocol

    Messages:
        OpenPRRequested: When browser open is triggered
        DescriptionExpanded: When description expanded
        DescriptionCollapsed: When description collapsed

    Attributes:
        state: Current widget state (PRSummaryState)
    """

    BINDINGS = [
        Binding(
            "enter", "toggle_description", "Expand/collapse description", show=False
        ),
        Binding("o", "open_in_browser", "Open in browser", show=False),
    ]

    class OpenPRRequested(Message):
        """Emitted when user requests to open PR in browser."""

        bubble = True

        def __init__(self, url: str) -> None:
            self.url = url
            super().__init__()

    class DescriptionExpanded(Message):
        """Emitted when PR description is expanded."""

        bubble = True

    class DescriptionCollapsed(Message):
        """Emitted when PR description is collapsed."""

        bubble = True

    # State icons
    STATE_ICONS = {
        PRState.OPEN: "●",
        PRState.MERGED: "✓",
        PRState.CLOSED: "○",
    }

    # Check status icons
    CHECK_ICONS = {
        CheckStatus.PASSING: "✓",
        CheckStatus.FAILING: "✗",
        CheckStatus.PENDING: "○",
    }

    state: reactive[PRSummaryState] = reactive(PRSummaryState, always_update=True)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize PRSummary widget.

        Args:
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.state = PRSummaryState()

    def render(self) -> RenderableType:
        """Render the PR summary widget.

        Returns:
            Renderable content based on current state.
        """
        # Loading state
        if self.state.loading:
            return Text("Loading PR data...", style="dim")

        # Empty state
        if self.state.is_empty:
            return Text("No pull request", style="dim")

        # Render PR data
        pr = self.state.pr
        if pr is None:
            return Text("No pull request", style="dim")

        lines = []

        # Header: PR number, title, and state
        state_icon = self.STATE_ICONS.get(pr.state, "○")
        # Map state to color
        state_colors = {
            PRState.OPEN: "green",
            PRState.MERGED: "cyan",
            PRState.CLOSED: "dim",
        }
        state_color = state_colors.get(pr.state, "dim")

        header = Text()
        header.append(f"#{pr.number} ", style="bold cyan")
        header.append(state_icon + " ", style=state_color)
        header.append(pr.title, style="bold")
        lines.append(header)

        # Branch info
        if pr.branch and pr.base_branch:
            branch_info = Text()
            branch_info.append(f"{pr.branch} → {pr.base_branch}", style="dim")
            lines.append(branch_info)

        # Description
        if pr.description:
            lines.append(Text())  # Empty line
            if self.state.description_expanded:
                # Show full description
                desc_text = Text(pr.description, style="")
                lines.append(desc_text)
                # Add collapse hint
                lines.append(Text("[click to collapse]", style="dim italic"))
            else:
                # Show preview
                preview = pr.description_preview
                desc_text = Text(preview, style="")
                lines.append(desc_text)
                # Add expand hint if truncated
                if preview != pr.description:
                    lines.append(Text("[click to expand...]", style="dim italic"))

        # Status checks
        if pr.checks:
            lines.append(Text())  # Empty line
            lines.append(Text("Status Checks:", style="bold"))
            for check in pr.checks:
                check_icon = self.CHECK_ICONS.get(check.status, "○")
                # Map check status to color
                check_colors = {
                    CheckStatus.PASSING: "green",
                    CheckStatus.FAILING: "red",
                    CheckStatus.PENDING: "yellow",
                }
                check_color = check_colors.get(check.status, "dim")

                check_line = Text()
                check_line.append(f"  {check_icon} ", style=check_color)
                check_line.append(check.name, style="")
                lines.append(check_line)

        # PR URL
        lines.append(Text())  # Empty line
        link_text = Text()
        link_text.append("🔗 Open in browser", style="cyan underline")
        lines.append(link_text)

        # Join all lines
        result = Text("\n").join(lines)
        return result

    def update_pr(self, pr: PRInfo | None) -> None:
        """Update the PR data.

        Args:
            pr: PR data to display, or None to show empty state.
        """
        self.state = replace(
            self.state,
            pr=pr,
            description_expanded=False,
            loading=False,
        )

    def set_loading(self, loading: bool) -> None:
        """Set the loading state.

        Args:
            loading: Whether PR data is loading.
        """
        self.state = replace(
            self.state,
            loading=loading,
        )

    def expand_description(self) -> None:
        """Expand the full PR description."""
        if self.state.pr is None:
            return

        self.state = replace(
            self.state,
            description_expanded=True,
        )
        self.post_message(self.DescriptionExpanded())

    def collapse_description(self) -> None:
        """Collapse to description preview."""
        if self.state.pr is None:
            return

        self.state = replace(
            self.state,
            description_expanded=False,
        )
        self.post_message(self.DescriptionCollapsed())

    async def open_pr_in_browser(self) -> None:
        """Open the PR URL in the default browser.

        Uses asyncio.to_thread to avoid blocking the event loop.
        """
        import asyncio

        if self.state.pr is None:
            return

        url = self.state.pr.url
        # Run webbrowser.open in a thread to avoid blocking
        await asyncio.to_thread(webbrowser.open, url)
        self.post_message(self.OpenPRRequested(url))

    def on_click(self) -> None:
        """Handle click events on the widget.

        Toggles description expansion or opens browser depending on click location.
        For now, we'll toggle description on any click except when at the bottom
        where the link is (simulated by checking if description is expandable).
        """
        if self.state.pr is None:
            return

        # If there's a description and it's expandable/collapsible, toggle it
        if self.state.pr.description:
            if self.state.description_expanded:
                self.collapse_description()
            else:
                # Check if description is truncated
                if self.state.pr.description_preview != self.state.pr.description:
                    self.expand_description()

    # =========================================================================
    # Keyboard Navigation Actions
    # =========================================================================

    def action_toggle_description(self) -> None:
        """Toggle description expansion."""
        if self.state.pr is None:
            return

        if self.state.description_expanded:
            self.collapse_description()
        else:
            self.expand_description()

    async def action_open_in_browser(self) -> None:
        """Open the PR in the default browser."""
        await self.open_pr_in_browser()
