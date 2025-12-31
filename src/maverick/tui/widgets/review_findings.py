"""ReviewFindings widget for displaying code review findings.

Feature: 012-workflow-widgets
User Story 3: ReviewFindings Widget

Displays code review findings grouped by severity with selection,
expansion, and bulk actions.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Label, Static

from maverick.tui.metrics import widget_metrics
from maverick.tui.models import (
    FindingSeverity,
    ReviewFinding,
    ReviewFindingItem,
    ReviewFindingsState,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class ReviewFindings(Static):
    """Widget for displaying code review findings.

    Displays findings grouped by severity (errors, warnings, suggestions)
    with multi-select checkboxes, expandable details, and bulk actions.

    Messages emitted:
        - FindingExpanded: When a finding is expanded
        - FindingSelected: When a finding selection changes
        - BulkDismissRequested: When bulk dismiss is triggered
        - BulkCreateIssueRequested: When bulk issue creation is triggered
        - FileLocationClicked: When a file:line link is clicked
        - CodeContextRequested: When code context is requested for a finding

    Example usage:
        findings_widget = ReviewFindings()
        findings_widget.update_findings(findings_data)
        findings_widget.select_finding(0, selected=True)
        findings_widget.expand_finding(0)
    """

    BINDINGS = [
        Binding("up", "move_up", "Previous finding", show=False),
        Binding("down", "move_down", "Next finding", show=False),
        Binding("enter", "toggle_expand", "Expand/collapse", show=False),
        Binding("space", "toggle_select", "Toggle selection", show=False),
        Binding("a", "select_all", "Select all", show=False),
        Binding("d", "deselect_all", "Deselect all", show=False),
    ]

    # CSS styling is defined in maverick.tcss for access to theme variables

    # ==========================================================================
    # Messages
    # ==========================================================================

    class FindingExpanded(Message):
        """Emitted when a finding is expanded."""

        def __init__(self, finding_id: str, index: int) -> None:
            """Initialize FindingExpanded message.

            Args:
                finding_id: ID of the expanded finding.
                index: Index of the finding.
            """
            super().__init__()
            self.finding_id = finding_id
            self.index = index

    class FindingSelected(Message):
        """Emitted when finding selection changes."""

        def __init__(self, finding_id: str, index: int, selected: bool) -> None:
            """Initialize FindingSelected message.

            Args:
                finding_id: ID of the finding.
                index: Index of the finding.
                selected: Whether finding is now selected.
            """
            super().__init__()
            self.finding_id = finding_id
            self.index = index
            self.selected = selected

    class BulkDismissRequested(Message):
        """Emitted when bulk dismiss is requested."""

        def __init__(self, finding_ids: tuple[str, ...]) -> None:
            """Initialize BulkDismissRequested message.

            Args:
                finding_ids: IDs of findings to dismiss.
            """
            super().__init__()
            self.finding_ids = finding_ids

    class BulkCreateIssueRequested(Message):
        """Emitted when bulk issue creation is requested."""

        def __init__(self, finding_ids: tuple[str, ...]) -> None:
            """Initialize BulkCreateIssueRequested message.

            Args:
                finding_ids: IDs of findings to create issues for.
            """
            super().__init__()
            self.finding_ids = finding_ids

    class FileLocationClicked(Message):
        """Emitted when a file:line link is clicked."""

        def __init__(self, file_path: str, line_number: int) -> None:
            """Initialize FileLocationClicked message.

            Args:
                file_path: Path to the file.
                line_number: Line number in the file.
            """
            super().__init__()
            self.file_path = file_path
            self.line_number = line_number

    class CodeContextRequested(Message):
        """Emitted when code context is requested for a finding."""

        def __init__(self, file_path: str, line_number: int) -> None:
            """Initialize CodeContextRequested message.

            Args:
                file_path: Path to the file.
                line_number: Line number in the file.
            """
            super().__init__()
            self.file_path = file_path
            self.line_number = line_number

    # ==========================================================================
    # Initialization
    # ==========================================================================

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Initialize ReviewFindings widget.

        Args:
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes for the widget.
            disabled: Whether the widget is disabled or not.
        """
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self._state = ReviewFindingsState()

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        if self._state.is_empty:
            yield Static(
                "No review findings. All clear!",
                classes="empty-state",
            )
        else:
            yield self._render_findings()

    # ==========================================================================
    # Public API (Protocol Implementation)
    # ==========================================================================

    def update_findings(self, findings: Sequence[ReviewFinding]) -> None:
        """Update all findings with new data.

        Findings are automatically grouped by severity.

        Args:
            findings: Sequence of finding data.
        """
        # Track message throughput (finding updates)
        widget_metrics.record_message("ReviewFindings")

        # Convert to ReviewFindingItem with selection state reset
        items = tuple(ReviewFindingItem(finding=f, selected=False) for f in findings)

        # Update state
        self._state = replace(
            self._state,
            findings=items,
            expanded_index=None,
            code_context=None,
            focused_index=0,
        )

        # Re-render
        self._refresh_display()

    def select_finding(self, index: int, *, selected: bool) -> None:
        """Set selection state for a finding.

        Args:
            index: Finding index in the list.
            selected: Whether to select or deselect.
        """
        if not (0 <= index < len(self._state.findings)):
            return

        # Update item selection
        items = list(self._state.findings)
        item = items[index]
        items[index] = replace(item, selected=selected)

        self._state = replace(self._state, findings=tuple(items))

        # Post message
        self.post_message(
            self.FindingSelected(
                finding_id=item.finding.id,
                index=index,
                selected=selected,
            )
        )

        # Update display
        self._refresh_display()

    def select_all(self) -> None:
        """Select all findings."""
        items = [replace(item, selected=True) for item in self._state.findings]
        self._state = replace(self._state, findings=tuple(items))
        self._refresh_display()

    def deselect_all(self) -> None:
        """Deselect all findings."""
        items = [replace(item, selected=False) for item in self._state.findings]
        self._state = replace(self._state, findings=tuple(items))
        self._refresh_display()

    def expand_finding(self, index: int) -> None:
        """Expand a finding to show full details.

        Args:
            index: Finding index to expand.
        """
        if not (0 <= index < len(self._state.findings)):
            return

        finding = self._state.findings[index].finding
        self._state = replace(self._state, expanded_index=index)

        # Post message
        self.post_message(
            self.FindingExpanded(
                finding_id=finding.id,
                index=index,
            )
        )

        # Update display
        self._refresh_display()

    def collapse_finding(self) -> None:
        """Collapse the currently expanded finding."""
        self._state = replace(self._state, expanded_index=None)
        self._refresh_display()

    def show_code_context(self, finding_index: int) -> None:
        """Show code context for a finding.

        Emits a CodeContextRequested message for the parent to handle.

        Args:
            finding_index: Index of finding to show context for.
        """
        if not (0 <= finding_index < len(self._state.findings)):
            return

        finding = self._state.findings[finding_index].finding
        location = finding.location

        # Emit message for parent to handle
        self.post_message(
            self.CodeContextRequested(
                file_path=location.file_path,
                line_number=location.line_number,
            )
        )

    @property
    def selected_findings(self) -> tuple[ReviewFinding, ...]:
        """Get all currently selected findings."""
        return self._state.selected_findings

    # ==========================================================================
    # Actions
    # ==========================================================================

    def action_bulk_dismiss(self) -> None:
        """Bulk dismiss selected findings."""
        if self._state.selected_count == 0:
            return

        finding_ids = tuple(f.id for f in self._state.selected_findings)
        self.post_message(self.BulkDismissRequested(finding_ids=finding_ids))

    def action_bulk_create_issue(self) -> None:
        """Bulk create issues for selected findings."""
        if self._state.selected_count == 0:
            return

        finding_ids = tuple(f.id for f in self._state.selected_findings)
        self.post_message(self.BulkCreateIssueRequested(finding_ids=finding_ids))

    # ==========================================================================
    # Internal Methods
    # ==========================================================================

    def _refresh_display(self) -> None:
        """Refresh the widget display."""
        # Track render time
        start_time = time.perf_counter() if widget_metrics.enabled else 0.0

        # Remove all children and re-compose
        self.remove_children()
        if self._state.is_empty:
            self.mount(
                Static(
                    "No review findings. All clear!",
                    classes="empty-state",
                )
            )
        else:
            self.mount(self._render_findings())

        # Record render time
        if widget_metrics.enabled:
            duration_ms = (time.perf_counter() - start_time) * 1000
            widget_metrics.record_render("ReviewFindings", duration_ms)

    def _render_findings(self) -> Vertical:
        """Render all findings grouped by severity.

        Returns:
            Vertical container with findings.
        """
        # Prepare all child widgets first
        children: list[Widget] = []

        # Header with selection count
        header_text = f"Review Findings ({len(self._state.findings)})"
        if self._state.selected_count > 0:
            header_text += f" - {self._state.selected_count} selected"

        children.append(Horizontal(Label(header_text), classes="findings-header"))

        # Bulk action buttons
        if self._state.selected_count > 0:
            children.append(
                Horizontal(
                    Button(
                        "Dismiss Selected",
                        id="btn-bulk-dismiss",
                        variant="default",
                    ),
                    Button(
                        "Create Issues",
                        id="btn-bulk-create-issue",
                        variant="primary",
                    ),
                    classes="bulk-actions",
                )
            )

        # Render findings grouped by severity
        by_severity = self._state.findings_by_severity

        # Errors first
        if by_severity[FindingSeverity.ERROR]:
            children.append(
                self._render_severity_section(
                    FindingSeverity.ERROR,
                    by_severity[FindingSeverity.ERROR],
                )
            )

        # Then warnings
        if by_severity[FindingSeverity.WARNING]:
            children.append(
                self._render_severity_section(
                    FindingSeverity.WARNING,
                    by_severity[FindingSeverity.WARNING],
                )
            )

        # Then suggestions
        if by_severity[FindingSeverity.SUGGESTION]:
            children.append(
                self._render_severity_section(
                    FindingSeverity.SUGGESTION,
                    by_severity[FindingSeverity.SUGGESTION],
                )
            )

        return Vertical(*children)

    def _render_severity_section(
        self,
        severity: FindingSeverity,
        items: list[ReviewFindingItem],
    ) -> Vertical:
        """Render a section for a specific severity.

        Args:
            severity: The severity level.
            items: Findings with this severity.

        Returns:
            Vertical container with the section.
        """
        # Prepare children first
        children: list[Widget] = []

        # Severity header with icon and count
        severity_icon = self._get_severity_icon(severity)
        severity_color = self._get_severity_color(severity)
        header_text = (
            f"[{severity_color}]{severity_icon} "
            f"{severity.value.title()}s ({len(items)})[/{severity_color}]"
        )
        children.append(Label(header_text, classes="severity-header", markup=True))

        # Render each finding in this section
        for item in items:
            # Find global index
            try:
                global_index = next(
                    i
                    for i, state_item in enumerate(self._state.findings)
                    if state_item.finding.id == item.finding.id
                )
            except StopIteration:
                # Item not found in state, skip
                continue
            children.append(self._render_finding_row(item, global_index))

        return Vertical(*children, classes="severity-section")

    def _render_finding_row(self, item: ReviewFindingItem, index: int) -> Vertical:
        """Render a single finding row.

        Args:
            item: The finding item to render.
            index: Global index of the finding.

        Returns:
            Vertical container with the finding row.
        """
        # Prepare children
        children: list[Widget] = []

        # Summary line with checkbox, title, and file:line
        # Checkbox for selection
        checkbox = Checkbox(
            "",
            value=item.selected,
            id=f"checkbox-{index}",
        )

        # Title
        title_text = f"{item.finding.title}"

        # File location as clickable button styled as link
        location = item.finding.location
        location_text = f"{location.file_path}:{location.line_number}"

        # Check if file exists
        file_exists = Path(location.file_path).exists()

        # Create location button with appropriate styling and tooltip
        button_classes = (
            "file-location-link file-location-broken"
            if not file_exists
            else "file-location-link"
        )
        location_button = Button(
            location_text,
            id=f"location-{index}",
            variant="default",
            classes=button_classes,
        )

        # Set tooltip for broken links
        if not file_exists:
            location_button.tooltip = f"File not found: {location.file_path}"

        children.append(
            Horizontal(
                checkbox,
                Label(title_text),
                location_button,
                classes="finding-summary",
            )
        )

        # Expandable details
        is_expanded = self._state.expanded_index == index
        if is_expanded:
            detail_children: list[Widget] = []

            # Description
            detail_children.append(Label(f"Description: {item.finding.description}"))

            # Suggested fix if available
            if item.finding.suggested_fix:
                detail_children.append(
                    Label(f"Suggested fix: {item.finding.suggested_fix}")
                )

            # Source
            detail_children.append(Label(f"Source: {item.finding.source}"))

            children.append(Vertical(*detail_children, classes="finding-detail"))

        return Vertical(*children, classes="finding-row")

    def _get_severity_icon(self, severity: FindingSeverity) -> str:
        """Get icon for severity level.

        Args:
            severity: The severity level.

        Returns:
            Icon character.
        """
        return {
            FindingSeverity.ERROR: "✗",
            FindingSeverity.WARNING: "⚠",
            FindingSeverity.SUGGESTION: "💡",
        }.get(severity, "•")

    def _get_severity_color(self, severity: FindingSeverity) -> str:
        """Get color for severity level.

        Args:
            severity: The severity level.

        Returns:
            Color name.
        """
        return {
            FindingSeverity.ERROR: "red",
            FindingSeverity.WARNING: "yellow",
            FindingSeverity.SUGGESTION: "cyan",
        }.get(severity, "white")

    def _on_file_location_clicked(self, file_path: str, line_number: int) -> None:
        """Handle file location click.

        Args:
            file_path: Path to the file.
            line_number: Line number in the file.
        """
        self.post_message(
            self.FileLocationClicked(
                file_path=file_path,
                line_number=line_number,
            )
        )

    # ==========================================================================
    # Event Handlers
    # ==========================================================================

    @on(Checkbox.Changed)
    def _on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox state change."""
        # Extract index from checkbox ID
        if not event.checkbox.id or not event.checkbox.id.startswith("checkbox-"):
            return

        try:
            index = int(event.checkbox.id.split("-")[1])
        except (IndexError, ValueError):
            return

        # Update selection
        self.select_finding(index, selected=event.value)

    @on(Button.Pressed, "#btn-bulk-dismiss")
    def _on_bulk_dismiss_pressed(self, event: Button.Pressed) -> None:
        """Handle bulk dismiss button press."""
        event.stop()
        self.action_bulk_dismiss()

    @on(Button.Pressed, "#btn-bulk-create-issue")
    def _on_bulk_create_issue_pressed(self, event: Button.Pressed) -> None:
        """Handle bulk create issue button press."""
        event.stop()
        self.action_bulk_create_issue()

    @on(Button.Pressed)
    def _on_file_location_button_pressed(self, event: Button.Pressed) -> None:
        """Handle file location button press."""
        # Check if this is a file location button
        if not event.button.id or not event.button.id.startswith("location-"):
            return

        event.stop()

        # Extract index from button ID
        try:
            index = int(event.button.id.split("-")[1])
        except (IndexError, ValueError):
            return

        # Get the finding and check if file exists
        if 0 <= index < len(self._state.findings):
            finding = self._state.findings[index].finding
            location = finding.location

            # Check if file exists
            if not Path(location.file_path).exists():
                # Show toast notification for broken links
                self.notify(
                    f"File not found: {location.file_path}",
                    severity="error",
                    title="Broken File Link",
                )
                return

            # Emit message for valid file locations
            self._on_file_location_clicked(location.file_path, location.line_number)

    # ==========================================================================
    # Keyboard Navigation Actions
    # ==========================================================================

    def action_move_up(self) -> None:
        """Move focus to previous finding."""
        if self._state.is_empty:
            return

        findings = self._state.findings
        if not findings:
            return

        # Move focused index up (with wrap-around)
        current = self._state.focused_index
        new_index = len(findings) - 1 if current <= 0 else current - 1

        self._state = replace(self._state, focused_index=new_index)
        self._refresh_display()

    def action_move_down(self) -> None:
        """Move focus to next finding."""
        if self._state.is_empty:
            return

        findings = self._state.findings
        if not findings:
            return

        # Move focused index down (with wrap-around)
        current = self._state.focused_index
        new_index = 0 if current >= len(findings) - 1 else current + 1

        self._state = replace(self._state, focused_index=new_index)
        self._refresh_display()

    def action_toggle_expand(self) -> None:
        """Toggle expansion of the currently focused finding."""
        if self._state.is_empty:
            return

        focused = self._state.focused_index
        if self._state.expanded_index == focused:
            self.collapse_finding()
        else:
            self.expand_finding(focused)

    def action_toggle_select(self) -> None:
        """Toggle selection of the currently focused finding."""
        if self._state.is_empty:
            return

        focused = self._state.focused_index
        if 0 <= focused < len(self._state.findings):
            current_selection = self._state.findings[focused].selected
            self.select_finding(focused, selected=not current_selection)
