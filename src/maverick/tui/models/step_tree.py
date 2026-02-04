"""Step tree model for hierarchical workflow step display.

This module provides the data model for rendering workflow steps as a
collapsible tree in the TUI. Nodes are keyed by their ``step_path``
(e.g., "implement_by_phase/[0]/validate_phase").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StepTreeNode:
    """A single node in the step tree.

    Attributes:
        path: Full hierarchical path (e.g., "loop/[0]/validate").
        label: Display label (last segment, or item_label for iterations).
        step_type: Step type string ("python", "agent", etc.), None for iterations.
        status: Execution status.
        duration_ms: Duration in milliseconds when completed.
        children: Ordered child nodes.
        expanded: Whether children are visible.
        depth: Nesting depth (0 = root).
        user_toggled: True if user explicitly toggled expand/collapse.
    """

    path: str
    label: str
    step_type: str | None = None
    status: str = "pending"  # pending | running | completed | failed | skipped
    duration_ms: int | None = None
    children: list[StepTreeNode] = field(default_factory=list)
    expanded: bool = True
    depth: int = 0
    user_toggled: bool = False


@dataclass(slots=True)
class StepTreeState:
    """Manages the full step tree and selection state.

    Attributes:
        roots: Top-level tree nodes.
        selected_path: Currently selected path for stream filtering.
    """

    roots: list[StepTreeNode] = field(default_factory=list)
    selected_path: str | None = None
    _node_index: dict[str, StepTreeNode] = field(default_factory=dict)

    def upsert_node(
        self,
        path: str,
        *,
        label: str | None = None,
        step_type: str | None = None,
        status: str | None = None,
        duration_ms: int | None = None,
    ) -> StepTreeNode:
        """Create or update a node, creating intermediate parents as needed.

        Args:
            path: Full step path (e.g., "loop/[0]/validate").
            label: Display label override. Defaults to last path segment.
            step_type: Step type string.
            status: Execution status.
            duration_ms: Duration in milliseconds.

        Returns:
            The created or updated node.
        """
        if path in self._node_index:
            node = self._node_index[path]
            if label is not None:
                node.label = label
            if step_type is not None:
                node.step_type = step_type
            if status is not None:
                old_status = node.status
                node.status = status
                # Auto-expand ancestors when a node starts running
                if status == "running" and old_status != "running":
                    self._auto_expand_ancestors(path)
            if duration_ms is not None:
                node.duration_ms = duration_ms
            return node

        # Split path and ensure all parent nodes exist
        segments = self._split_path(path)
        parent_children = self.roots
        parent_path = ""

        for i, segment in enumerate(segments):
            current_path = f"{parent_path}/{segment}" if parent_path else segment
            if current_path in self._node_index:
                parent_node = self._node_index[current_path]
                parent_children = parent_node.children
                parent_path = current_path
                continue

            # Create intermediate or final node
            is_final = i == len(segments) - 1
            node_label = label if is_final and label else segment
            node = StepTreeNode(
                path=current_path,
                label=node_label,
                step_type=step_type if is_final else None,
                status=status or "pending" if is_final else "pending",
                duration_ms=duration_ms if is_final else None,
                depth=i,
            )
            parent_children.append(node)
            self._node_index[current_path] = node

            if is_final and status == "running":
                self._auto_expand_ancestors(current_path)

            parent_children = node.children
            parent_path = current_path

        return self._node_index[path]

    def flatten_visible(self) -> list[StepTreeNode]:
        """Return a flat list of nodes respecting collapse state.

        Returns:
            List of visible nodes in depth-first order.
        """
        result: list[StepTreeNode] = []
        self._flatten(self.roots, result)
        return result

    def auto_collapse_completed(self, path: str) -> None:
        """Auto-collapse a node if all children are completed/skipped.

        Only collapses if the user hasn't explicitly toggled the node.

        Args:
            path: Path of the node to check.
        """
        node = self._node_index.get(path)
        if node is None or node.user_toggled:
            return
        if not node.children:
            return
        if all(c.status in ("completed", "skipped", "failed") for c in node.children):
            node.expanded = False

    def _auto_expand_ancestors(self, path: str) -> None:
        """Expand all ancestors of a path (unless user-toggled closed)."""
        segments = self._split_path(path)
        ancestor_path = ""
        for segment in segments[:-1]:
            ancestor_path = f"{ancestor_path}/{segment}" if ancestor_path else segment
            ancestor = self._node_index.get(ancestor_path)
            if ancestor and not ancestor.user_toggled:
                ancestor.expanded = True

    def select_next_visible(self) -> str | None:
        """Move selection down in the flattened visible list (wrap-around).

        Returns:
            The newly selected path, or None if the tree is empty.
        """
        visible = self.flatten_visible()
        if not visible:
            return None

        if self.selected_path is None:
            self.selected_path = visible[0].path
            return self.selected_path

        for i, node in enumerate(visible):
            if node.path == self.selected_path:
                next_index = (i + 1) % len(visible)
                self.selected_path = visible[next_index].path
                return self.selected_path

        # Selected path not in visible list; select first
        self.selected_path = visible[0].path
        return self.selected_path

    def select_prev_visible(self) -> str | None:
        """Move selection up in the flattened visible list (wrap-around).

        Returns:
            The newly selected path, or None if the tree is empty.
        """
        visible = self.flatten_visible()
        if not visible:
            return None

        if self.selected_path is None:
            self.selected_path = visible[-1].path
            return self.selected_path

        for i, node in enumerate(visible):
            if node.path == self.selected_path:
                prev_index = (i - 1) % len(visible)
                self.selected_path = visible[prev_index].path
                return self.selected_path

        # Selected path not in visible list; select last
        self.selected_path = visible[-1].path
        return self.selected_path

    def toggle_expanded(self, path: str) -> bool:
        """Toggle expand/collapse for a node with children.

        Args:
            path: Path of the node to toggle.

        Returns:
            True if the node was toggled, False if not found or has no children.
        """
        node = self._node_index.get(path)
        if node is None or not node.children:
            return False
        node.expanded = not node.expanded
        node.user_toggled = True
        return True

    def _flatten(
        self,
        nodes: list[StepTreeNode],
        result: list[StepTreeNode],
    ) -> None:
        for node in nodes:
            result.append(node)
            if node.expanded and node.children:
                self._flatten(node.children, result)

    @staticmethod
    def _split_path(path: str) -> list[str]:
        """Split a step path into segments.

        Handles both regular segments and bracket segments:
        "loop/[0]/step" -> ["loop", "[0]", "step"]
        """
        return path.split("/")
