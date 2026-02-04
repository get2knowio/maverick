"""StepTreeWidget for hierarchical step display in the left panel.

Renders StepTreeState as a collapsible tree with status icons,
duration info, and click-to-filter behavior.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.css.query import NoMatches
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from maverick.tui.models.step_tree import StepTreeNode, StepTreeState

# Status icons
_STATUS_ICONS: dict[str, str] = {
    "pending": "\u25cb",  # ○
    "running": "\u25cf",  # ●
    "completed": "\u2713",  # ✓
    "failed": "\u2717",  # ✗
    "skipped": "\u2014",  # —
}

# Status colors for Rich markup
_STATUS_COLORS: dict[str, str] = {
    "pending": "grey50",
    "running": "dodger_blue1",
    "completed": "green3",
    "failed": "red1",
    "skipped": "grey50",
}

# Expand/collapse icons
_EXPAND_ICON = "\u25bc"  # ▼
_COLLAPSE_ICON = "\u25b7"  # ▷


class StepTreeWidget(Widget):
    """Widget displaying workflow steps as a collapsible tree.

    Posts ``StepTreeNodeSelected`` when a node is clicked or selected via keyboard.
    """

    can_focus = True

    BINDINGS = [
        Binding("up", "move_up", "Previous step", show=False),
        Binding("down", "move_down", "Next step", show=False),
        Binding("enter", "toggle_expand", "Toggle expand", show=False),
    ]

    class StepTreeNodeSelected(Message):
        """Posted when a tree node is clicked or selected via keyboard."""

        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    DEFAULT_CSS = """
    StepTreeWidget {
        height: 100%;
        width: 100%;
    }

    StepTreeWidget .tree-content {
        height: 1fr;
        padding: 0;
    }

    StepTreeWidget .tree-node {
        height: 1;
        width: 100%;
        padding: 0 1;
    }

    StepTreeWidget .tree-node.selected {
        background: $accent 20%;
        border-left: thick $accent;
    }

    StepTreeWidget .tree-node.running {
        color: $accent;
    }

    StepTreeWidget .tree-node.completed {
        color: $text;
    }

    StepTreeWidget .tree-node.failed {
        color: $error;
    }

    StepTreeWidget .tree-node.pending {
        color: $text-muted;
    }

    StepTreeWidget .tree-node.skipped {
        color: $text-disabled;
    }
    """

    def __init__(
        self,
        state: StepTreeState,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._state = state
        self._node_widgets: dict[str, Static] = {}

    def compose(self) -> ComposeResult:
        with ScrollableContainer(classes="tree-content", id="tree-content"):
            for node in self._state.flatten_visible():
                widget = self._create_node_widget(node)
                self._node_widgets[node.path] = widget
                yield widget

    def refresh_tree(self) -> None:
        """Re-render the entire tree from current state."""
        if not self.is_mounted:
            return

        try:
            content = self.query_one("#tree-content", ScrollableContainer)
        except NoMatches:
            return

        # Clear existing
        for child in list(content.children):
            child.remove()
        self._node_widgets.clear()

        # Re-render
        for node in self._state.flatten_visible():
            widget = self._create_node_widget(node)
            self._node_widgets[node.path] = widget
            content.mount(widget)

    def _create_node_widget(self, node: StepTreeNode) -> Static:
        """Create a Static widget for a single tree node."""
        # Build indentation
        indent = "  " * node.depth

        # Expand/collapse icon
        if node.children:
            expand_icon = _EXPAND_ICON if node.expanded else _COLLAPSE_ICON
            expand_str = f"{expand_icon} "
        else:
            expand_str = "  "

        # Status icon with color
        status_icon = _STATUS_ICONS.get(node.status, "?")
        status_color = _STATUS_COLORS.get(node.status, "white")

        # Duration
        duration_str = ""
        if node.duration_ms is not None:
            duration_sec = node.duration_ms / 1000
            if duration_sec >= 60:
                minutes = int(duration_sec) // 60
                seconds = int(duration_sec) % 60
                duration_str = f" {minutes}m {seconds}s"
            else:
                duration_str = f" {duration_sec:.1f}s"

        # Selected highlight
        selected = node.path == self._state.selected_path
        css_classes = f"tree-node {node.status}"
        if selected:
            css_classes += " selected"

        line = (
            f"{indent}{expand_str}{node.label}"
            f"  [{status_color}]{status_icon}[/]"
            f"[dim]{duration_str}[/]"
        )

        widget = Static(line, classes=css_classes)
        widget._step_tree_path = node.path  # type: ignore[attr-defined]
        return widget

    def on_click(self, event: object) -> None:
        """Handle click on tree nodes."""
        from textual.events import Click

        if not isinstance(event, Click):
            return

        # Find the clicked widget using screen coordinates for reliability.
        # event.widget may not reference the child Static when the Click
        # event bubbles up from a child to this parent widget.
        clicked_widget = None
        try:
            clicked_widget, _offset = self.screen.get_widget_at(
                event.screen_x, event.screen_y
            )
        except (AttributeError, Exception):
            # Fallback: try event.widget (may work in some Textual versions)
            clicked_widget = getattr(event, "widget", None)

        if clicked_widget is None:
            return

        # Walk up the widget tree to find the node with a path attribute
        widget = clicked_widget
        path: str | None = None
        while widget is not None and widget is not self:
            path = getattr(widget, "_step_tree_path", None)
            if path is not None:
                break
            widget = widget.parent  # type: ignore[assignment]

        if path is None:
            return

        # Toggle expand/collapse if clicking an already-selected parent node
        node = self._state._node_index.get(path)
        if node and node.children and path == self._state.selected_path:
            node.expanded = not node.expanded
            node.user_toggled = True
            self.refresh_tree()
            return

        self.post_message(self.StepTreeNodeSelected(path))

    def action_move_down(self) -> None:
        """Move selection down to the next visible node."""
        new_path = self._state.select_next_visible()
        if new_path is not None:
            self.refresh_tree()
            self.post_message(self.StepTreeNodeSelected(new_path))

    def action_move_up(self) -> None:
        """Move selection up to the previous visible node."""
        new_path = self._state.select_prev_visible()
        if new_path is not None:
            self.refresh_tree()
            self.post_message(self.StepTreeNodeSelected(new_path))

    def action_toggle_expand(self) -> None:
        """Toggle expand/collapse on the currently selected node."""
        if self._state.selected_path is not None and self._state.toggle_expanded(
            self._state.selected_path
        ):
            self.refresh_tree()
