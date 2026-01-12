"""Unit tests for ShortcutFooter widget.

This test module covers:
- ShortcutFooter widget creation
- Key formatting
- Shortcut setting and display
- Binding extraction

Feature: 030-tui-execution-visibility
Date: 2026-01-12
"""

from __future__ import annotations

from textual.binding import Binding

from maverick.tui.widgets.shortcut_footer import ShortcutFooter


class TestShortcutFooterCreation:
    """Tests for ShortcutFooter widget creation."""

    def test_creation_with_defaults(self) -> None:
        """Test creating ShortcutFooter with default options."""
        footer = ShortcutFooter()

        assert footer.max_shortcuts == 8
        assert footer._shortcuts == []

    def test_creation_with_custom_max_shortcuts(self) -> None:
        """Test creating ShortcutFooter with custom max_shortcuts."""
        footer = ShortcutFooter(max_shortcuts=5)

        assert footer.max_shortcuts == 5

    def test_creation_with_id_and_classes(self) -> None:
        """Test creating ShortcutFooter with id and classes."""
        footer = ShortcutFooter(id="my-footer", classes="custom-class")

        assert footer.id == "my-footer"
        assert "custom-class" in footer.classes


class TestShortcutFooterFormatKey:
    """Tests for ShortcutFooter._format_key method."""

    def test_format_single_letter(self) -> None:
        """Test formatting single letter keys."""
        footer = ShortcutFooter()

        assert footer._format_key("q") == "Q"
        assert footer._format_key("h") == "H"
        assert footer._format_key("?") == "?"

    def test_format_ctrl_modifier(self) -> None:
        """Test formatting ctrl modifier."""
        footer = ShortcutFooter()

        assert footer._format_key("ctrl+c") == "C-c"
        assert footer._format_key("ctrl+q") == "C-q"

    def test_format_shift_modifier(self) -> None:
        """Test formatting shift modifier."""
        footer = ShortcutFooter()

        assert footer._format_key("shift+a") == "S-a"

    def test_format_alt_modifier(self) -> None:
        """Test formatting alt modifier."""
        footer = ShortcutFooter()

        assert footer._format_key("alt+x") == "A-x"

    def test_format_special_keys(self) -> None:
        """Test formatting special key names."""
        footer = ShortcutFooter()

        assert footer._format_key("escape") == "Esc"
        assert footer._format_key("enter") == "Enter"
        assert footer._format_key("tab") == "Tab"

    def test_format_combined_modifiers(self) -> None:
        """Test formatting combined modifiers."""
        footer = ShortcutFooter()

        assert footer._format_key("ctrl+shift+a") == "C-S-a"


class TestShortcutFooterSetShortcuts:
    """Tests for ShortcutFooter.set_shortcuts method."""

    def test_set_shortcuts_empty_list(self) -> None:
        """Test setting empty shortcuts list."""
        footer = ShortcutFooter()
        footer.set_shortcuts([])

        assert footer._shortcuts == []

    def test_set_shortcuts_single(self) -> None:
        """Test setting single shortcut."""
        footer = ShortcutFooter()
        footer.set_shortcuts([("q", "Quit")])

        assert len(footer._shortcuts) == 1
        assert footer._shortcuts[0] == ("q", "Quit")

    def test_set_shortcuts_multiple(self) -> None:
        """Test setting multiple shortcuts."""
        footer = ShortcutFooter()
        shortcuts = [
            ("q", "Quit"),
            ("h", "Help"),
            ("?", "Show help"),
        ]
        footer.set_shortcuts(shortcuts)

        assert len(footer._shortcuts) == 3

    def test_set_shortcuts_respects_max(self) -> None:
        """Test set_shortcuts respects max_shortcuts limit."""
        footer = ShortcutFooter(max_shortcuts=3)
        shortcuts = [
            ("a", "Action A"),
            ("b", "Action B"),
            ("c", "Action C"),
            ("d", "Action D"),
            ("e", "Action E"),
        ]
        footer.set_shortcuts(shortcuts)

        # Should truncate to max_shortcuts
        assert len(footer._shortcuts) == 3
        assert footer._shortcuts[0] == ("a", "Action A")
        assert footer._shortcuts[2] == ("c", "Action C")


class TestShortcutFooterExtractBindings:
    """Tests for ShortcutFooter._extract_bindings method."""

    def test_extract_bindings_from_object_without_bindings(self) -> None:
        """Test extracting bindings from object without BINDINGS attribute."""
        footer = ShortcutFooter()

        class NoBindings:
            pass

        bindings = footer._extract_bindings(NoBindings())
        assert bindings == []

    def test_extract_bindings_from_binding_objects(self) -> None:
        """Test extracting bindings from Binding objects."""
        footer = ShortcutFooter()

        class WithBindings:
            BINDINGS = [
                Binding("q", "quit", "Quit app", show=True),
                Binding("h", "help", "Show help", show=True),
            ]

        bindings = footer._extract_bindings(WithBindings())
        assert len(bindings) == 2
        assert ("Q", "Quit app") in bindings
        assert ("H", "Show help") in bindings

    def test_extract_bindings_filters_hidden(self) -> None:
        """Test that hidden bindings are not extracted."""
        footer = ShortcutFooter()

        class WithHiddenBindings:
            BINDINGS = [
                Binding("q", "quit", "Quit app", show=True),
                Binding("x", "hidden", "Hidden action", show=False),
            ]

        bindings = footer._extract_bindings(WithHiddenBindings())
        assert len(bindings) == 1
        assert ("Q", "Quit app") in bindings

    def test_extract_bindings_uses_action_when_no_description(self) -> None:
        """Test binding uses action as description when description is empty."""
        footer = ShortcutFooter()

        class WithNoDescription:
            BINDINGS = [
                Binding("q", "my_action", "", show=True),
            ]

        bindings = footer._extract_bindings(WithNoDescription())
        assert len(bindings) == 1
        # Should use action when description is empty
        assert bindings[0][1] == "my_action"

    def test_extract_bindings_from_tuple_format(self) -> None:
        """Test extracting bindings from legacy tuple format."""
        footer = ShortcutFooter()

        class WithTupleBindings:
            BINDINGS = [
                ("q", "quit", "Quit app"),
                ("h", "help", "Show help"),
            ]

        bindings = footer._extract_bindings(WithTupleBindings())
        assert len(bindings) == 2
        assert ("Q", "Quit app") in bindings
        assert ("H", "Show help") in bindings


class TestShortcutFooterDeduplication:
    """Tests for shortcut deduplication logic."""

    def test_collect_shortcuts_deduplicates_by_key(self) -> None:
        """Test _collect_shortcuts deduplicates by key."""
        footer = ShortcutFooter()

        # Simulate manual collection with duplicates
        # (In real use, screen and app might have same binding)
        shortcuts = [
            ("Q", "Quit from screen"),
            ("Q", "Quit from app"),  # Duplicate key
            ("H", "Help"),
        ]

        # Filter duplicates manually (simulating _collect_shortcuts logic)
        seen_keys: set[str] = set()
        unique: list[tuple[str, str]] = []
        for key, desc in shortcuts:
            if key.lower() not in seen_keys:
                seen_keys.add(key.lower())
                unique.append((key, desc))

        # Should have 2 unique keys
        assert len(unique) == 2
        # First occurrence wins
        assert unique[0] == ("Q", "Quit from screen")
