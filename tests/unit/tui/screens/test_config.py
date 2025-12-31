"""Unit tests for ConfigScreen."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

from maverick.tui.screens.config import ConfigScreen

# =============================================================================
# ConfigScreen Initialization Tests
# =============================================================================


class TestConfigScreenInitialization:
    """Tests for ConfigScreen initialization."""

    def test_initialization_with_defaults(self) -> None:
        """Test screen creation with default parameters."""
        screen = ConfigScreen()
        assert screen.TITLE == "Settings"
        assert screen._options == []
        assert screen._selected_index == 0
        assert screen._editing is False
        assert screen._edit_value == ""
        assert screen._editing_key is None

    def test_initialization_with_custom_parameters(self) -> None:
        """Test screen creation with custom parameters."""
        screen = ConfigScreen(name="custom-config", id="config-1", classes="custom")
        assert screen.name == "custom-config"
        assert screen.id == "config-1"


# =============================================================================
# ConfigScreen Load Config Tests
# =============================================================================


class TestConfigScreenLoadConfig:
    """Tests for load_config method."""

    def test_load_config_populates_options(self) -> None:
        """Test that load_config populates sample options."""
        screen = ConfigScreen()

        with patch.object(screen, "_render_options"):
            screen.load_config()

        assert len(screen._options) > 0
        # Check that sample options are present
        assert any(opt["key"] == "notifications_enabled" for opt in screen._options)
        assert any(opt["key"] == "log_level" for opt in screen._options)
        assert any(opt["key"] == "max_parallel_agents" for opt in screen._options)

    def test_load_config_renders_options(self) -> None:
        """Test that load_config calls render."""
        screen = ConfigScreen()

        with patch.object(screen, "_render_options") as mock_render:
            screen.load_config()

        mock_render.assert_called_once()


# =============================================================================
# ConfigScreen Edit Option Tests
# =============================================================================


class TestConfigScreenEditOption:
    """Tests for edit_option method."""

    def test_edit_option_bool_toggles_immediately(self) -> None:
        """Test editing a boolean option toggles it immediately."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_bool",
                "label": "Test Bool",
                "value": True,
                "type": "bool",
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.edit_option("test_bool")

        # Boolean should be toggled
        assert screen._options[0]["value"] is False
        # Should exit edit mode immediately
        assert screen._editing is False
        assert screen._editing_key is None

    def test_edit_option_bool_toggles_from_false_to_true(self) -> None:
        """Test toggling a boolean from False to True."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_bool",
                "label": "Test Bool",
                "value": False,
                "type": "bool",
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.edit_option("test_bool")

        assert screen._options[0]["value"] is True

    def test_edit_option_choice_cycles_to_next(self) -> None:
        """Test editing a choice option cycles to the next choice."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_choice",
                "label": "Test Choice",
                "value": "option1",
                "type": "choice",
                "choices": ["option1", "option2", "option3"],
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.edit_option("test_choice")

        # Should cycle to next choice
        assert screen._options[0]["value"] == "option2"
        # Should exit edit mode immediately
        assert screen._editing is False

    def test_edit_option_choice_wraps_around(self) -> None:
        """Test choice option wraps around to first when at end."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_choice",
                "label": "Test Choice",
                "value": "option3",
                "type": "choice",
                "choices": ["option1", "option2", "option3"],
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.edit_option("test_choice")

        # Should wrap around to first choice
        assert screen._options[0]["value"] == "option1"

    def test_edit_option_int_enters_input_mode(self) -> None:
        """Test editing an int option enters input mode."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_int",
                "label": "Test Int",
                "value": 5,
                "type": "int",
                "min": 1,
                "max": 10,
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.edit_option("test_int")

        # Should enter edit mode
        assert screen._editing is True
        assert screen._editing_key == "test_int"
        assert screen._edit_value == "5"

    def test_edit_option_string_enters_input_mode(self) -> None:
        """Test editing a string option enters input mode."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_string",
                "label": "Test String",
                "value": "hello",
                "type": "string",
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.edit_option("test_string")

        assert screen._editing is True
        assert screen._editing_key == "test_string"
        assert screen._edit_value == "hello"

    def test_edit_option_nonexistent_key(self) -> None:
        """Test editing a nonexistent option key does nothing."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "existing_key",
                "label": "Existing",
                "value": "test",
                "type": "string",
            }
        ]

        with patch.object(screen, "_render_options") as mock_render:
            screen.edit_option("nonexistent_key")

        # Should not enter edit mode
        assert screen._editing is False
        # Should not render
        mock_render.assert_not_called()


# =============================================================================
# ConfigScreen Save Option Tests
# =============================================================================


class TestConfigScreenSaveOption:
    """Tests for save_option method."""

    def test_save_option_int_valid_value(self) -> None:
        """Test saving a valid integer value."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_int",
                "label": "Test Int",
                "value": 5,
                "type": "int",
                "min": 1,
                "max": 10,
            }
        ]
        screen._editing = True
        screen._editing_key = "test_int"

        with patch.object(screen, "_render_options"):
            screen.save_option("test_int", "7")

        assert screen._options[0]["value"] == 7
        assert screen._editing is False
        assert screen._editing_key is None

    def test_save_option_int_enforces_min(self) -> None:
        """Test saving an int below minimum clamps to min."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_int",
                "label": "Test Int",
                "value": 5,
                "type": "int",
                "min": 1,
                "max": 10,
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.save_option("test_int", "0")

        # Should clamp to minimum
        assert screen._options[0]["value"] == 1

    def test_save_option_int_enforces_max(self) -> None:
        """Test saving an int above maximum clamps to max."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_int",
                "label": "Test Int",
                "value": 5,
                "type": "int",
                "min": 1,
                "max": 10,
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.save_option("test_int", "15")

        # Should clamp to maximum
        assert screen._options[0]["value"] == 10

    def test_save_option_int_invalid_value(self) -> None:
        """Test saving an invalid int value doesn't change option."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_int",
                "label": "Test Int",
                "value": 5,
                "type": "int",
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.save_option("test_int", "not_a_number")

        # Value should remain unchanged
        assert screen._options[0]["value"] == 5
        # Should exit edit mode anyway
        assert screen._editing is False

    def test_save_option_choice_valid_choice(self) -> None:
        """Test saving a valid choice value."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_choice",
                "label": "Test Choice",
                "value": "option1",
                "type": "choice",
                "choices": ["option1", "option2", "option3"],
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.save_option("test_choice", "option2")

        assert screen._options[0]["value"] == "option2"

    def test_save_option_choice_invalid_choice(self) -> None:
        """Test saving an invalid choice doesn't change option."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_choice",
                "label": "Test Choice",
                "value": "option1",
                "type": "choice",
                "choices": ["option1", "option2", "option3"],
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.save_option("test_choice", "invalid_option")

        # Value should remain unchanged
        assert screen._options[0]["value"] == "option1"

    def test_save_option_bool(self) -> None:
        """Test saving a boolean value."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "test_bool",
                "label": "Test Bool",
                "value": True,
                "type": "bool",
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.save_option("test_bool", False)

        assert screen._options[0]["value"] is False

    def test_save_option_nonexistent_key(self) -> None:
        """Test saving to a nonexistent key does nothing."""
        screen = ConfigScreen()
        screen._options = [
            {
                "key": "existing_key",
                "label": "Existing",
                "value": "test",
                "type": "string",
            }
        ]

        with patch.object(screen, "_render_options"):
            screen.save_option("nonexistent_key", "value")

        # Should exit edit mode
        assert screen._editing is False


# =============================================================================
# ConfigScreen Cancel Edit Tests
# =============================================================================


class TestConfigScreenCancelEdit:
    """Tests for cancel_edit method."""

    def test_cancel_edit_resets_state(self) -> None:
        """Test that cancel_edit resets editing state."""
        screen = ConfigScreen()
        screen._editing = True
        screen._editing_key = "test_key"
        screen._edit_value = "test_value"

        with patch.object(screen, "_render_options"):
            screen.cancel_edit()

        assert screen._editing is False
        assert screen._editing_key is None
        assert screen._edit_value == ""

    def test_cancel_edit_renders_options(self) -> None:
        """Test that cancel_edit re-renders options."""
        screen = ConfigScreen()
        screen._editing = True

        with patch.object(screen, "_render_options") as mock_render:
            screen.cancel_edit()

        mock_render.assert_called_once()


# =============================================================================
# ConfigScreen Actions Tests
# =============================================================================


class TestConfigScreenActions:
    """Tests for ConfigScreen action methods."""

    def test_action_cancel_or_back_while_editing(self) -> None:
        """Test action_cancel_or_back cancels edit when editing."""
        screen = ConfigScreen()
        screen._editing = True

        with patch.object(screen, "cancel_edit") as mock_cancel:
            screen.action_cancel_or_back()

        mock_cancel.assert_called_once()

    def test_action_cancel_or_back_while_not_editing(self) -> None:
        """Test action_cancel_or_back pops screen when not editing."""
        screen = ConfigScreen()
        screen._editing = False
        mock_app = MagicMock()

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            screen.action_cancel_or_back()

        mock_app.pop_screen.assert_called_once()

    def test_action_edit_selected(self) -> None:
        """Test action_edit_selected edits the selected option."""
        screen = ConfigScreen()
        screen._options = [
            {"key": "option1", "label": "Option 1", "value": True, "type": "bool"},
            {"key": "option2", "label": "Option 2", "value": 5, "type": "int"},
        ]
        screen._selected_index = 1
        screen._editing = False

        with patch.object(screen, "edit_option") as mock_edit:
            screen.action_edit_selected()

        mock_edit.assert_called_once_with("option2")

    def test_action_edit_selected_while_editing(self) -> None:
        """Test action_edit_selected does nothing when already editing."""
        screen = ConfigScreen()
        screen._options = [
            {"key": "option1", "label": "Option 1", "value": True, "type": "bool"}
        ]
        screen._editing = True

        with patch.object(screen, "edit_option") as mock_edit:
            screen.action_edit_selected()

        mock_edit.assert_not_called()

    def test_action_move_down(self) -> None:
        """Test moving selection down."""
        screen = ConfigScreen()
        screen._options = [
            {"key": "option1", "label": "Option 1", "value": True, "type": "bool"},
            {"key": "option2", "label": "Option 2", "value": 5, "type": "int"},
        ]
        screen._selected_index = 0
        screen._editing = False

        with patch.object(screen, "_render_options"):
            screen.action_move_down()

        assert screen._selected_index == 1

    def test_action_move_down_at_end(self) -> None:
        """Test that move down doesn't go beyond last option."""
        screen = ConfigScreen()
        screen._options = [
            {"key": "option1", "label": "Option 1", "value": True, "type": "bool"},
            {"key": "option2", "label": "Option 2", "value": 5, "type": "int"},
        ]
        screen._selected_index = 1
        screen._editing = False

        with patch.object(screen, "_render_options"):
            screen.action_move_down()

        assert screen._selected_index == 1

    def test_action_move_down_while_editing(self) -> None:
        """Test that move down does nothing when editing."""
        screen = ConfigScreen()
        screen._options = [
            {"key": "option1", "label": "Option 1", "value": True, "type": "bool"}
        ]
        screen._selected_index = 0
        screen._editing = True

        with patch.object(screen, "_render_options") as mock_render:
            screen.action_move_down()

        # Should not move or render
        assert screen._selected_index == 0
        mock_render.assert_not_called()

    def test_action_move_up(self) -> None:
        """Test moving selection up."""
        screen = ConfigScreen()
        screen._options = [
            {"key": "option1", "label": "Option 1", "value": True, "type": "bool"},
            {"key": "option2", "label": "Option 2", "value": 5, "type": "int"},
        ]
        screen._selected_index = 1
        screen._editing = False

        with patch.object(screen, "_render_options"):
            screen.action_move_up()

        assert screen._selected_index == 0

    def test_action_move_up_at_start(self) -> None:
        """Test that move up doesn't go below zero."""
        screen = ConfigScreen()
        screen._options = [
            {"key": "option1", "label": "Option 1", "value": True, "type": "bool"}
        ]
        screen._selected_index = 0
        screen._editing = False

        with patch.object(screen, "_render_options"):
            screen.action_move_up()

        assert screen._selected_index == 0


# =============================================================================
# ConfigScreen Event Handling Tests
# =============================================================================


class TestConfigScreenEventHandling:
    """Tests for ConfigScreen event handling."""

    def test_on_input_submitted_while_editing(self) -> None:
        """Test handling input submission while editing."""
        screen = ConfigScreen()
        screen._editing = True
        screen._editing_key = "test_key"
        screen._options = [
            {"key": "test_key", "label": "Test", "value": "old", "type": "string"}
        ]

        # Create a mock event
        from textual.widgets import Input

        mock_event = MagicMock(spec=Input.Submitted)
        mock_event.value = "new_value"

        with patch.object(screen, "save_option") as mock_save:
            screen.on_input_submitted(mock_event)

        mock_save.assert_called_once_with("test_key", "new_value")

    def test_on_input_submitted_while_not_editing(self) -> None:
        """Test that input submission does nothing when not editing."""
        screen = ConfigScreen()
        screen._editing = False

        from textual.widgets import Input

        mock_event = MagicMock(spec=Input.Submitted)
        mock_event.value = "new_value"

        with patch.object(screen, "save_option") as mock_save:
            screen.on_input_submitted(mock_event)

        mock_save.assert_not_called()


# =============================================================================
# ConfigScreen Helper Methods Tests
# =============================================================================


class TestConfigScreenHelperMethods:
    """Tests for ConfigScreen private helper methods."""

    def test_format_value_bool_true(self) -> None:
        """Test formatting a true boolean value."""
        screen = ConfigScreen()
        option = {"value": True, "type": "bool"}

        result = screen._format_value(option)

        assert "enabled" in result
        assert "green" in result

    def test_format_value_bool_false(self) -> None:
        """Test formatting a false boolean value."""
        screen = ConfigScreen()
        option = {"value": False, "type": "bool"}

        result = screen._format_value(option)

        assert "disabled" in result
        assert "red" in result

    def test_format_value_choice(self) -> None:
        """Test formatting a choice value."""
        screen = ConfigScreen()
        option = {"value": "option1", "type": "choice"}

        result = screen._format_value(option)

        assert "option1" in result
        assert "cyan" in result

    def test_format_value_int(self) -> None:
        """Test formatting an integer value."""
        screen = ConfigScreen()
        option = {"value": 42, "type": "int"}

        result = screen._format_value(option)

        assert "42" in result
        assert "yellow" in result

    def test_format_value_string(self) -> None:
        """Test formatting a string value."""
        screen = ConfigScreen()
        option = {"value": "test_value", "type": "string"}

        result = screen._format_value(option)

        assert result == "test_value"
