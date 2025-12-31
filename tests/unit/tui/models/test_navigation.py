"""Unit tests for TUI navigation models."""

from __future__ import annotations

from datetime import datetime

import pytest

from maverick.tui.models import (
    LogEntry,
    LogPanelState,
    NavigationItem,
    SidebarMode,
    SidebarState,
    StageState,
)


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating LogEntry with all fields."""
        timestamp = datetime(2025, 1, 1, 12, 0, 0)

        entry = LogEntry(
            timestamp=timestamp,
            source="agent",
            level="info",
            message="Task completed successfully",
        )

        assert entry.timestamp == timestamp
        assert entry.source == "agent"
        assert entry.level == "info"
        assert entry.message == "Task completed successfully"

    def test_different_log_levels(self) -> None:
        """Test LogEntry with different levels."""
        for level in ["info", "success", "warning", "error"]:
            entry = LogEntry(
                timestamp=datetime.now(),
                source="test",
                level=level,
                message="Test message",
            )
            assert entry.level == level

    def test_different_sources(self) -> None:
        """Test LogEntry with different sources."""
        for source in ["agent", "workflow", "tool", "system"]:
            entry = LogEntry(
                timestamp=datetime.now(),
                source=source,
                level="info",
                message="Test message",
            )
            assert entry.source == source

    def test_log_entry_is_frozen(self) -> None:
        """Test LogEntry is immutable (frozen)."""
        entry = LogEntry(
            timestamp=datetime.now(),
            source="test",
            level="info",
            message="Test",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            entry.level = "error"  # type: ignore[misc]


# =============================================================================
# LogPanelState Tests
# =============================================================================


class TestLogPanelState:
    """Tests for LogPanelState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating LogPanelState with default values."""
        state = LogPanelState()

        assert state.visible is False
        assert state.entries == []
        assert state.max_entries == 1000
        assert state.auto_scroll is True

    def test_creation_with_custom_values(self) -> None:
        """Test creating LogPanelState with custom values."""
        entry = LogEntry(
            timestamp=datetime.now(),
            source="test",
            level="info",
            message="Test",
        )

        state = LogPanelState(
            visible=True,
            entries=[entry],
            max_entries=500,
            auto_scroll=False,
        )

        assert state.visible is True
        assert len(state.entries) == 1
        assert state.max_entries == 500
        assert state.auto_scroll is False

    def test_add_entry_method(self) -> None:
        """Test add_entry method adds entries."""
        state = LogPanelState()

        entry1 = LogEntry(
            timestamp=datetime.now(),
            source="test",
            level="info",
            message="First",
        )
        entry2 = LogEntry(
            timestamp=datetime.now(),
            source="test",
            level="info",
            message="Second",
        )

        state.add_entry(entry1)
        state.add_entry(entry2)

        assert len(state.entries) == 2
        assert state.entries[0] == entry1
        assert state.entries[1] == entry2

    def test_add_entry_respects_max_entries(self) -> None:
        """Test add_entry maintains buffer limit."""
        state = LogPanelState(max_entries=3)

        # Add 5 entries
        for i in range(5):
            entry = LogEntry(
                timestamp=datetime.now(),
                source="test",
                level="info",
                message=f"Message {i}",
            )
            state.add_entry(entry)

        # Should keep only last 3
        assert len(state.entries) == 3
        assert state.entries[0].message == "Message 2"
        assert state.entries[1].message == "Message 3"
        assert state.entries[2].message == "Message 4"

    def test_log_panel_state_is_mutable(self) -> None:
        """Test LogPanelState is mutable (not frozen)."""
        state = LogPanelState()

        # Should allow modification
        state.visible = True
        assert state.visible is True

        state.auto_scroll = False
        assert state.auto_scroll is False

    def test_log_panel_state_has_slots(self) -> None:
        """Test LogPanelState uses slots for memory efficiency."""
        state = LogPanelState()

        # Mutable dataclasses with slots raise AttributeError when setting
        # new attributes
        with pytest.raises((AttributeError, TypeError)):
            state.extra_field = "value"  # type: ignore[attr-defined]


# =============================================================================
# NavigationItem Tests
# =============================================================================


class TestNavigationItem:
    """Tests for NavigationItem dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating NavigationItem with required fields."""
        item = NavigationItem(
            id="home",
            label="Home",
            icon="H",
        )

        assert item.id == "home"
        assert item.label == "Home"
        assert item.icon == "H"
        assert item.shortcut is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating NavigationItem with all fields."""
        item = NavigationItem(
            id="settings",
            label="Settings",
            icon="S",
            shortcut="Ctrl+,",
        )

        assert item.id == "settings"
        assert item.label == "Settings"
        assert item.icon == "S"
        assert item.shortcut == "Ctrl+,"

    def test_shortcut_defaults_to_none(self) -> None:
        """Test shortcut defaults to None."""
        item = NavigationItem(id="test", label="Test", icon="T")

        assert item.shortcut is None

    def test_navigation_item_is_frozen(self) -> None:
        """Test NavigationItem is immutable (frozen)."""
        item = NavigationItem(id="test", label="Test", icon="T")

        with pytest.raises(Exception):  # FrozenInstanceError
            item.label = "Modified"  # type: ignore[misc]


# =============================================================================
# SidebarState Tests
# =============================================================================


class TestSidebarState:
    """Tests for SidebarState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating SidebarState with default values."""
        state = SidebarState()

        assert state.mode == SidebarMode.NAVIGATION
        assert len(state.navigation_items) == 3
        assert state.workflow_stages == ()
        assert state.selected_nav_index == 0

    def test_default_navigation_items(self) -> None:
        """Test default navigation items are set correctly."""
        state = SidebarState()

        assert len(state.navigation_items) == 3

        home = state.navigation_items[0]
        assert home.id == "home"
        assert home.label == "Home"
        assert home.icon == "H"
        assert home.shortcut == "Ctrl+H"

        workflows = state.navigation_items[1]
        assert workflows.id == "workflows"
        assert workflows.label == "Workflows"
        assert workflows.icon == "W"
        assert workflows.shortcut is None

        settings = state.navigation_items[2]
        assert settings.id == "settings"
        assert settings.label == "Settings"
        assert settings.icon == "S"
        assert settings.shortcut == "Ctrl+,"

    def test_creation_with_custom_values(self) -> None:
        """Test creating SidebarState with custom values."""
        custom_nav = (
            NavigationItem(id="dashboard", label="Dashboard", icon="D"),
            NavigationItem(id="logs", label="Logs", icon="L"),
        )

        stage = StageState(name="build", display_name="Build")

        state = SidebarState(
            mode=SidebarMode.WORKFLOW,
            navigation_items=custom_nav,
            workflow_stages=(stage,),
            selected_nav_index=1,
        )

        assert state.mode == SidebarMode.WORKFLOW
        assert len(state.navigation_items) == 2
        assert len(state.workflow_stages) == 1
        assert state.selected_nav_index == 1

    def test_workflow_mode(self) -> None:
        """Test SidebarState in workflow mode."""
        stages = (
            StageState(name="setup", display_name="Setup"),
            StageState(name="build", display_name="Build"),
            StageState(name="test", display_name="Test"),
        )

        state = SidebarState(
            mode=SidebarMode.WORKFLOW,
            workflow_stages=stages,
        )

        assert state.mode == SidebarMode.WORKFLOW
        assert len(state.workflow_stages) == 3

    def test_sidebar_state_is_frozen(self) -> None:
        """Test SidebarState is immutable (frozen)."""
        state = SidebarState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.mode = SidebarMode.WORKFLOW  # type: ignore[misc]


# =============================================================================
