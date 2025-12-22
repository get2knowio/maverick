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
        """Test that action_start starts workflow execution."""
        screen = FlyScreen()
        screen.branch_name = "feature/test"
        screen.is_valid = True
        screen.is_starting = False

        mock_button = MagicMock(spec=Button)

        with (
            patch.object(screen, "query_one", return_value=mock_button),
            patch.object(screen, "_toggle_workflow_view") as mock_toggle,
            patch.object(screen, "_start_workflow_execution") as mock_start,
        ):
            screen.action_start()

        assert screen.is_starting is True
        assert screen.is_workflow_running is True
        mock_toggle.assert_called_once_with(show=True)
        mock_start.assert_called_once()

    def test_action_start_strips_whitespace_from_branch_name(self) -> None:
        """Test that action_start strips whitespace from branch name."""
        screen = FlyScreen()
        screen.branch_name = "  feature/test  "
        screen.is_valid = True
        screen.is_starting = False

        mock_button = MagicMock(spec=Button)

        with (
            patch.object(screen, "query_one", return_value=mock_button),
            patch.object(screen, "_toggle_workflow_view"),
            patch.object(screen, "_start_workflow_execution"),
        ):
            screen.action_start()

        # Verify state was updated correctly
        assert screen.is_starting is True

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


# =============================================================================
# FlyScreen WorkflowProgress Integration Tests (Issue #48)
# =============================================================================


class TestFlyScreenWorkflowProgressIntegration:
    """Tests for WorkflowProgress widget integration."""

    def test_toggle_workflow_view_shows_workflow_container(self) -> None:
        """Test that _toggle_workflow_view shows workflow container."""
        screen = FlyScreen()
        mock_form = MagicMock()
        mock_workflow = MagicMock()

        def mock_query(selector: str, widget_type: type | None = None) -> MagicMock:
            if selector == "#form-container":
                return mock_form
            elif selector == "#workflow-container":
                return mock_workflow
            raise Exception(f"Unexpected selector: {selector}")

        with patch.object(screen, "query_one", side_effect=mock_query):
            screen._toggle_workflow_view(show=True)

        mock_form.add_class.assert_called_once_with("hidden")
        mock_workflow.remove_class.assert_called_once_with("hidden")
        assert screen.show_workflow_view is True

    def test_toggle_workflow_view_hides_workflow_container(self) -> None:
        """Test that _toggle_workflow_view hides workflow container."""
        screen = FlyScreen()
        mock_form = MagicMock()
        mock_workflow = MagicMock()

        def mock_query(selector: str, widget_type: type | None = None) -> MagicMock:
            if selector == "#form-container":
                return mock_form
            elif selector == "#workflow-container":
                return mock_workflow
            raise Exception(f"Unexpected selector: {selector}")

        with patch.object(screen, "query_one", side_effect=mock_query):
            screen._toggle_workflow_view(show=False)

        mock_workflow.add_class.assert_called_once_with("hidden")
        mock_form.remove_class.assert_called_once_with("hidden")
        assert screen.show_workflow_view is False

    def test_initialize_workflow_stages_creates_stages(self) -> None:
        """Test that _initialize_workflow_stages creates correct stages."""
        screen = FlyScreen()
        mock_progress_widget = MagicMock()

        with patch.object(screen, "query_one", return_value=mock_progress_widget):
            screen._initialize_workflow_stages()

        # Verify update_stages was called with 6 stages
        mock_progress_widget.update_stages.assert_called_once()
        stages = mock_progress_widget.update_stages.call_args[0][0]
        assert len(stages) == 6

        # Verify stage names
        stage_names = [stage.name for stage in stages]
        assert "init" in stage_names
        assert "implementation" in stage_names
        assert "validation" in stage_names
        assert "code_review" in stage_names
        assert "convention_update" in stage_names
        assert "pr_creation" in stage_names

    def test_update_stage_status_updates_widget(self) -> None:
        """Test that _update_stage_status updates the widget."""
        screen = FlyScreen()
        mock_progress_widget = MagicMock()

        with patch.object(screen, "query_one", return_value=mock_progress_widget):
            screen._update_stage_status("init", "active")

        mock_progress_widget.update_stage_status.assert_called_once_with(
            "init", "active", error_message=None
        )

    def test_update_stage_status_with_error_message(self) -> None:
        """Test that _update_stage_status handles error messages."""
        screen = FlyScreen()
        mock_progress_widget = MagicMock()

        with patch.object(screen, "query_one", return_value=mock_progress_widget):
            screen._update_stage_status(
                "validation", "failed", error_message="Test failed"
            )

        mock_progress_widget.update_stage_status.assert_called_once_with(
            "validation", "failed", error_message="Test failed"
        )

    def test_add_agent_message_creates_message(self) -> None:
        """Test that _add_agent_message adds message to widget."""
        screen = FlyScreen()
        mock_output_widget = MagicMock()

        with patch.object(screen, "query_one", return_value=mock_output_widget):
            screen._add_agent_message("Test message", agent_name="TestAgent")

        # Verify add_message was called
        mock_output_widget.add_message.assert_called_once()
        message = mock_output_widget.add_message.call_args[0][0]
        assert message.content == "Test message"
        assert message.agent_name == "TestAgent"


# =============================================================================
# FlyScreen Auto-Transition Tests (Issue #49)
# =============================================================================


class TestFlyScreenAutoTransition:
    """Tests for auto-transition to ReviewScreen after code review."""

    def test_convert_review_results_to_findings_empty(self) -> None:
        """Test _convert_review_results_to_findings with empty results."""
        screen = FlyScreen()
        findings = screen._convert_review_results_to_findings([])
        assert findings == []

    def test_convert_review_results_to_findings_with_data(self) -> None:
        """Test _convert_review_results_to_findings with mock data."""
        screen = FlyScreen()

        # Create mock result with findings attribute
        mock_finding = MagicMock()
        mock_finding.file_path = "test.py"
        mock_finding.line_number = 42
        mock_finding.severity = "error"
        mock_finding.message = "Test error"
        mock_finding.source = "test-reviewer"

        mock_result = MagicMock()
        mock_result.findings = [mock_finding]

        findings = screen._convert_review_results_to_findings([mock_result])

        assert len(findings) == 1
        assert findings[0]["file_path"] == "test.py"
        assert findings[0]["line_number"] == 42
        assert findings[0]["severity"] == "error"
        assert findings[0]["message"] == "Test error"
        assert findings[0]["source"] == "test-reviewer"
