"""Unit tests for FlyScreen."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

from textual.widgets import Button, Input

from maverick.tui.screens.fly import FlyScreen
from maverick.tui.widgets.form import BranchInputField

# =============================================================================
# FlyScreen Initialization Tests
# =============================================================================


class TestFlyScreenInitialization:
    """Tests for FlyScreen initialization."""

    def test_initialization_with_defaults(self) -> None:
        """Test screen creation with default parameters."""
        screen = FlyScreen()
        assert screen.TITLE == "Start Fly Workflow"
        assert len(screen.BINDINGS) > 0

    def test_initialization_with_custom_parameters(self) -> None:
        """Test screen creation with custom parameters."""
        screen = FlyScreen(name="custom-fly", id="fly-1", classes="custom")
        assert screen.name == "custom-fly"
        assert screen.id == "fly-1"

    def test_reactive_attributes_default_values(self) -> None:
        """Test that reactive attributes have correct default values."""
        screen = FlyScreen()
        assert screen.branch_name == ""
        assert screen.branch_error == ""
        assert screen.is_valid is False
        assert screen.is_starting is False
        assert screen.task_file is None


# =============================================================================
# FlyScreen Branch Validation Tests (T022)
# =============================================================================


class TestFlyScreenBranchValidation:
    """Tests for branch name validation functionality."""

    def test_empty_branch_name_is_invalid(self) -> None:
        """Test that empty branch name is marked as invalid."""
        screen = FlyScreen()
        event = BranchInputField.Changed(value="", is_valid=False)

        screen.on_branch_input_field_changed(event)

        assert screen.branch_name == ""
        assert screen.is_valid is False

    def test_valid_branch_name_accepted(self) -> None:
        """Test that valid branch name is accepted."""
        screen = FlyScreen()
        event = BranchInputField.Changed(value="feature/my-feature", is_valid=True)

        screen.on_branch_input_field_changed(event)

        assert screen.branch_name == "feature/my-feature"
        assert screen.is_valid is True

    def test_invalid_characters_rejected(self) -> None:
        """Test that branch name with invalid characters is rejected."""
        screen = FlyScreen()
        event = BranchInputField.Changed(value="feature@#$", is_valid=False)

        screen.on_branch_input_field_changed(event)

        assert screen.branch_name == "feature@#$"
        assert screen.is_valid is False

    def test_valid_branch_names_with_various_formats(self) -> None:
        """Test various valid branch name formats."""
        screen = FlyScreen()
        valid_names = [
            "feature/test",
            "fix/bug-123",
            "release/v1.0.0",
            "feat-new-feature",
            "user_branch",
            "dev.test",
        ]

        for name in valid_names:
            event = BranchInputField.Changed(value=name, is_valid=True)
            screen.on_branch_input_field_changed(event)
            assert screen.branch_name == name
            assert screen.is_valid is True


# =============================================================================
# FlyScreen State Management Tests (T023)
# =============================================================================


class TestFlyScreenStateManagement:
    """Tests for FlyScreen state management."""

    def test_start_button_disabled_when_invalid(self) -> None:
        """Test that start button is disabled when validation fails."""
        screen = FlyScreen()
        mock_button = MagicMock(spec=Button)

        with patch.object(screen, "query_one", return_value=mock_button):
            screen.is_valid = False
            screen._update_start_button()

        assert mock_button.disabled is True

    def test_start_button_enabled_when_valid(self) -> None:
        """Test that start button is enabled when validation passes."""
        screen = FlyScreen()
        mock_button = MagicMock(spec=Button)

        with patch.object(screen, "query_one", return_value=mock_button):
            screen.is_valid = True
            screen.is_starting = False
            screen._update_start_button()

        assert mock_button.disabled is False

    def test_start_button_disabled_when_starting(self) -> None:
        """Test that start button is disabled when workflow is starting."""
        screen = FlyScreen()
        mock_button = MagicMock(spec=Button)

        with patch.object(screen, "query_one", return_value=mock_button):
            screen.is_valid = True
            screen.is_starting = True
            screen._update_start_button()

        assert mock_button.disabled is True

    def test_task_file_input_updates_state(self) -> None:
        """Test that task file input updates the task_file state."""
        screen = FlyScreen()
        mock_input = MagicMock(spec=Input)
        mock_input.id = "task-file-input"

        event = Input.Changed(mock_input, "path/to/tasks.md")
        screen.on_input_changed(event)

        assert screen.task_file is not None
        assert str(screen.task_file) == "path/to/tasks.md"

    def test_task_file_cleared_when_empty(self) -> None:
        """Test that task_file is cleared when input is empty."""
        screen = FlyScreen()
        mock_input = MagicMock(spec=Input)
        mock_input.id = "task-file-input"

        event = Input.Changed(mock_input, "")
        screen.on_input_changed(event)

        assert screen.task_file is None

    def test_task_file_handles_whitespace(self) -> None:
        """Test that task_file input handles whitespace correctly."""
        screen = FlyScreen()
        mock_input = MagicMock(spec=Input)
        mock_input.id = "task-file-input"

        event = Input.Changed(mock_input, "  ")
        screen.on_input_changed(event)

        assert screen.task_file is None


# =============================================================================
# FlyScreen Workflow Start and Transition Tests (T024)
# =============================================================================


class TestFlyScreenWorkflowStartAndTransition:
    """Tests for workflow start functionality and screen transitions."""

    def test_action_start_does_nothing_when_invalid(self) -> None:
        """Test that action_start does nothing when validation fails."""
        screen = FlyScreen()
        screen.is_valid = False
        screen.is_starting = False

        mock_app = MagicMock()
        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            screen.action_start()

        mock_app.push_screen.assert_not_called()

    def test_action_start_does_nothing_when_already_starting(self) -> None:
        """Test that action_start does nothing when already starting."""
        screen = FlyScreen()
        screen.is_valid = True
        screen.is_starting = True

        mock_app = MagicMock()
        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            screen.action_start()

        mock_app.push_screen.assert_not_called()

    def test_action_start_transitions_to_workflow_screen(self) -> None:
        """Test that action_start transitions to WorkflowScreen."""
        screen = FlyScreen()
        screen.branch_name = "feature/test"
        screen.is_valid = True
        screen.is_starting = False

        mock_app = MagicMock()
        mock_workflow_screen = MagicMock()
        mock_button = MagicMock(spec=Button)

        with (
            patch.object(
                type(screen), "app", new_callable=PropertyMock, return_value=mock_app
            ),
            patch(
                "maverick.tui.screens.workflow.WorkflowScreen",
                return_value=mock_workflow_screen,
            ) as mock_workflow_class,
            patch.object(screen, "query_one", return_value=mock_button),
        ):
            screen.action_start()

        assert screen.is_starting is True
        mock_workflow_class.assert_called_once_with(
            workflow_name="Fly", branch_name="feature/test"
        )
        mock_app.push_screen.assert_called_once_with(mock_workflow_screen)

    def test_action_start_strips_whitespace_from_branch_name(self) -> None:
        """Test that action_start strips whitespace from branch name."""
        screen = FlyScreen()
        screen.branch_name = "  feature/test  "
        screen.is_valid = True
        screen.is_starting = False

        mock_app = MagicMock()
        mock_workflow_screen = MagicMock()
        mock_button = MagicMock(spec=Button)

        with (
            patch.object(
                type(screen), "app", new_callable=PropertyMock, return_value=mock_app
            ),
            patch(
                "maverick.tui.screens.workflow.WorkflowScreen",
                return_value=mock_workflow_screen,
            ) as mock_workflow_class,
            patch.object(screen, "query_one", return_value=mock_button),
        ):
            screen.action_start()

        mock_workflow_class.assert_called_once_with(
            workflow_name="Fly", branch_name="feature/test"
        )

    def test_start_button_pressed_calls_action_start(self) -> None:
        """Test that pressing start button calls action_start."""
        screen = FlyScreen()
        mock_button = MagicMock(spec=Button)
        mock_button.id = "start-btn"

        with patch.object(screen, "action_start") as mock_action_start:
            event = Button.Pressed(mock_button)
            screen.on_button_pressed(event)

        mock_action_start.assert_called_once()

    def test_cancel_button_calls_go_back(self) -> None:
        """Test that pressing cancel button calls go_back."""
        screen = FlyScreen()
        mock_button = MagicMock(spec=Button)
        mock_button.id = "cancel-btn"

        with patch.object(screen, "go_back") as mock_go_back:
            event = Button.Pressed(mock_button)
            screen.on_button_pressed(event)

        mock_go_back.assert_called_once()

    def test_other_button_presses_ignored(self) -> None:
        """Test that other button presses are ignored."""
        screen = FlyScreen()
        mock_button = MagicMock(spec=Button)
        mock_button.id = "unknown-btn"

        with (
            patch.object(screen, "action_start") as mock_action_start,
            patch.object(screen, "go_back") as mock_go_back,
        ):
            event = Button.Pressed(mock_button)
            screen.on_button_pressed(event)

        mock_action_start.assert_not_called()
        mock_go_back.assert_not_called()


# =============================================================================
# FlyScreen Component Integration Tests
# =============================================================================


class TestFlyScreenComponentIntegration:
    """Tests for FlyScreen component integration."""

    def test_on_mount_focuses_branch_input(self) -> None:
        """Test that on_mount focuses the branch input field."""
        screen = FlyScreen()
        mock_field = MagicMock(spec=BranchInputField)

        with patch.object(screen, "query_one", return_value=mock_field):
            screen.on_mount()

        mock_field.focus_input.assert_called_once()

    def test_on_mount_handles_missing_branch_input_gracefully(self) -> None:
        """Test that on_mount handles missing branch input gracefully."""
        screen = FlyScreen()

        with patch.object(screen, "query_one", side_effect=Exception("Not found")):
            # Should not raise exception
            screen.on_mount()

    def test_compose_method_exists(self) -> None:
        """Test that compose method exists and is callable."""
        screen = FlyScreen()

        # Verify compose method exists
        assert hasattr(screen, "compose")
        assert callable(screen.compose)

    def test_bindings_include_escape_and_ctrl_enter(self) -> None:
        """Test that bindings include escape and ctrl+enter."""
        screen = FlyScreen()
        binding_keys = [binding.key for binding in screen.BINDINGS]

        assert "escape" in binding_keys
        assert "ctrl+enter" in binding_keys
