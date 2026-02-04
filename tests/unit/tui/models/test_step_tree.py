"""Tests for StepTreeState and StepTreeNode."""

from __future__ import annotations

from maverick.tui.models.step_tree import StepTreeState


class TestStepTreeState:
    """Tests for StepTreeState."""

    def test_upsert_creates_node(self) -> None:
        state = StepTreeState()
        node = state.upsert_node("step_a", step_type="python", status="running")

        assert node.path == "step_a"
        assert node.label == "step_a"
        assert node.step_type == "python"
        assert node.status == "running"
        assert node.depth == 0
        assert len(state.roots) == 1

    def test_upsert_creates_intermediate_nodes(self) -> None:
        state = StepTreeState()
        node = state.upsert_node(
            "loop/[0]/validate", step_type="python", status="running"
        )

        assert node.path == "loop/[0]/validate"
        assert node.depth == 2

        # Check intermediate nodes were created
        assert "loop" in state._node_index
        assert "loop/[0]" in state._node_index
        assert len(state.roots) == 1
        assert state.roots[0].path == "loop"
        assert len(state.roots[0].children) == 1
        assert state.roots[0].children[0].path == "loop/[0]"

    def test_upsert_updates_existing_node(self) -> None:
        state = StepTreeState()
        state.upsert_node("step_a", status="running")
        node = state.upsert_node("step_a", status="completed", duration_ms=500)

        assert node.status == "completed"
        assert node.duration_ms == 500
        assert len(state.roots) == 1  # No duplicate

    def test_upsert_with_label(self) -> None:
        state = StepTreeState()
        node = state.upsert_node("[0]", label="Phase 1: Setup")

        assert node.label == "Phase 1: Setup"
        assert node.path == "[0]"

    def test_flatten_visible_basic(self) -> None:
        state = StepTreeState()
        state.upsert_node("step_a", status="completed")
        state.upsert_node("step_b", status="running")
        state.upsert_node("step_c", status="pending")

        visible = state.flatten_visible()
        assert len(visible) == 3
        assert [n.path for n in visible] == ["step_a", "step_b", "step_c"]

    def test_flatten_visible_respects_collapse(self) -> None:
        state = StepTreeState()
        state.upsert_node("loop/[0]/child_a", status="completed")
        state.upsert_node("loop/[1]/child_b", status="completed")

        # Collapse the loop node
        loop_node = state._node_index["loop"]
        loop_node.expanded = False

        visible = state.flatten_visible()
        # Only the root "loop" should be visible
        assert len(visible) == 1
        assert visible[0].path == "loop"

    def test_flatten_visible_with_expanded_children(self) -> None:
        state = StepTreeState()
        state.upsert_node("loop/[0]/child", status="completed")

        visible = state.flatten_visible()
        # loop, [0], child all visible (expanded by default)
        assert len(visible) == 3
        paths = [n.path for n in visible]
        assert paths == ["loop", "loop/[0]", "loop/[0]/child"]

    def test_auto_expand_on_running(self) -> None:
        state = StepTreeState()
        # Create collapsed parent
        state.upsert_node("loop", status="pending")
        state._node_index["loop"].expanded = False

        # Creating a running child should auto-expand
        state.upsert_node("loop/[0]", status="running")

        assert state._node_index["loop"].expanded is True

    def test_auto_expand_does_not_override_user_toggle(self) -> None:
        state = StepTreeState()
        state.upsert_node("loop", status="pending")
        state._node_index["loop"].expanded = False
        state._node_index["loop"].user_toggled = True

        # Creating a running child should NOT auto-expand user-toggled node
        state.upsert_node("loop/[0]", status="running")

        assert state._node_index["loop"].expanded is False

    def test_auto_collapse_when_all_children_complete(self) -> None:
        state = StepTreeState()
        state.upsert_node("loop/[0]", status="completed")
        state.upsert_node("loop/[1]", status="completed")

        state.auto_collapse_completed("loop")
        assert state._node_index["loop"].expanded is False

    def test_auto_collapse_not_when_children_still_running(self) -> None:
        state = StepTreeState()
        state.upsert_node("loop/[0]", status="completed")
        state.upsert_node("loop/[1]", status="running")

        state.auto_collapse_completed("loop")
        assert state._node_index["loop"].expanded is True

    def test_auto_collapse_respects_user_toggle(self) -> None:
        state = StepTreeState()
        state.upsert_node("loop/[0]", status="completed")
        state.upsert_node("loop/[1]", status="completed")
        state._node_index["loop"].user_toggled = True

        state.auto_collapse_completed("loop")
        # Should NOT collapse because user toggled
        assert state._node_index["loop"].expanded is True

    def test_multiple_roots(self) -> None:
        state = StepTreeState()
        state.upsert_node("setup", status="completed")
        state.upsert_node("implement", status="running")
        state.upsert_node("review", status="pending")

        assert len(state.roots) == 3
        assert [r.path for r in state.roots] == [
            "setup",
            "implement",
            "review",
        ]


class TestSelectNextVisible:
    """Tests for select_next_visible navigation."""

    def test_empty_tree_returns_none(self) -> None:
        state = StepTreeState()
        assert state.select_next_visible() is None

    def test_no_selection_selects_first(self) -> None:
        state = StepTreeState()
        state.upsert_node("a")
        state.upsert_node("b")

        result = state.select_next_visible()
        assert result == "a"
        assert state.selected_path == "a"

    def test_advances_to_next(self) -> None:
        state = StepTreeState()
        state.upsert_node("a")
        state.upsert_node("b")
        state.upsert_node("c")
        state.selected_path = "a"

        assert state.select_next_visible() == "b"
        assert state.select_next_visible() == "c"

    def test_wraps_around(self) -> None:
        state = StepTreeState()
        state.upsert_node("a")
        state.upsert_node("b")
        state.selected_path = "b"

        assert state.select_next_visible() == "a"

    def test_stale_selection_resets_to_first(self) -> None:
        state = StepTreeState()
        state.upsert_node("a")
        state.selected_path = "nonexistent"

        assert state.select_next_visible() == "a"


class TestSelectPrevVisible:
    """Tests for select_prev_visible navigation."""

    def test_empty_tree_returns_none(self) -> None:
        state = StepTreeState()
        assert state.select_prev_visible() is None

    def test_no_selection_selects_last(self) -> None:
        state = StepTreeState()
        state.upsert_node("a")
        state.upsert_node("b")

        result = state.select_prev_visible()
        assert result == "b"
        assert state.selected_path == "b"

    def test_moves_to_previous(self) -> None:
        state = StepTreeState()
        state.upsert_node("a")
        state.upsert_node("b")
        state.upsert_node("c")
        state.selected_path = "c"

        assert state.select_prev_visible() == "b"
        assert state.select_prev_visible() == "a"

    def test_wraps_around(self) -> None:
        state = StepTreeState()
        state.upsert_node("a")
        state.upsert_node("b")
        state.selected_path = "a"

        assert state.select_prev_visible() == "b"

    def test_stale_selection_resets_to_last(self) -> None:
        state = StepTreeState()
        state.upsert_node("a")
        state.upsert_node("b")
        state.selected_path = "nonexistent"

        assert state.select_prev_visible() == "b"


class TestToggleExpanded:
    """Tests for toggle_expanded method."""

    def test_toggle_node_with_children(self) -> None:
        state = StepTreeState()
        state.upsert_node("loop/[0]", status="running")

        # "loop" has children, should toggle
        assert state._node_index["loop"].expanded is True
        assert state.toggle_expanded("loop") is True
        assert state._node_index["loop"].expanded is False
        assert state._node_index["loop"].user_toggled is True

    def test_toggle_again_expands(self) -> None:
        state = StepTreeState()
        state.upsert_node("loop/[0]", status="running")
        state.toggle_expanded("loop")  # collapse
        state.toggle_expanded("loop")  # expand

        assert state._node_index["loop"].expanded is True

    def test_toggle_leaf_returns_false(self) -> None:
        state = StepTreeState()
        state.upsert_node("step_a", status="running")

        assert state.toggle_expanded("step_a") is False

    def test_toggle_nonexistent_returns_false(self) -> None:
        state = StepTreeState()
        assert state.toggle_expanded("nope") is False


class TestFilterPrefixMatching:
    """Tests for stream filter prefix matching logic."""

    def test_matches_filter_prefix(self) -> None:
        """'a/b' matches 'a/b/c' but not 'a/bc'."""

        # Simulate the matching logic from UnifiedStreamWidget
        def matches(filter_path: str | None, entry_path: str | None) -> bool:
            if filter_path is None:
                return True
            if entry_path is None:
                return True
            return entry_path == filter_path or entry_path.startswith(filter_path + "/")

        assert matches("a/b", "a/b/c") is True
        assert matches("a/b", "a/bc") is False
        assert matches("a/b", "a/b") is True
        assert matches("a", "a/b/c") is True

    def test_matches_filter_exact(self) -> None:
        def matches(filter_path: str, entry_path: str) -> bool:
            return entry_path == filter_path or entry_path.startswith(filter_path + "/")

        assert matches("a/b", "a/b") is True

    def test_matches_filter_none_shows_all(self) -> None:
        def matches(filter_path: str | None, entry_path: str | None) -> bool:
            if filter_path is None:
                return True
            if entry_path is None:
                return True
            return entry_path == filter_path or entry_path.startswith(filter_path + "/")

        assert matches(None, "anything") is True
        assert matches(None, None) is True

    def test_global_events_always_shown(self) -> None:
        def matches(filter_path: str | None, entry_path: str | None) -> bool:
            if filter_path is None:
                return True
            if entry_path is None:
                return True
            return entry_path == filter_path or entry_path.startswith(filter_path + "/")

        # Global events (path=None) pass through any filter
        assert matches("some/filter", None) is True
