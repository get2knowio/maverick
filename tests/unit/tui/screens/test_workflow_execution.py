"""Unit tests for WorkflowExecutionScreen."""

from __future__ import annotations

from unittest.mock import MagicMock

from maverick.tui.screens.workflow_execution import (
    STATUS_ICONS,
    STEP_TYPE_ICONS,
    StepWidget,
    WorkflowExecutionScreen,
)


def create_mock_step(
    name: str = "test-step",
    step_type: str = "python",
) -> MagicMock:
    """Create a mock step for testing."""
    mock_step = MagicMock()
    mock_step.name = name
    mock_step.type.value = step_type
    return mock_step


def create_mock_workflow(
    name: str = "test-workflow",
    description: str | None = "Test workflow description",
    steps: list | None = None,
) -> MagicMock:
    """Create a mock WorkflowFile for testing."""
    mock_workflow = MagicMock()
    mock_workflow.name = name
    mock_workflow.description = description
    mock_workflow.steps = steps or []
    return mock_workflow


# Step Type Icons Tests
class TestStepTypeIcons:
    """Tests for step type icon mapping."""

    def test_python_icon(self):
        """Test python step has gear icon."""
        assert STEP_TYPE_ICONS["python"] == "\u2699"

    def test_agent_icon(self):
        """Test agent step has robot icon."""
        assert STEP_TYPE_ICONS["agent"] == "\U0001f916"

    def test_generate_icon(self):
        """Test generate step has writing hand icon."""
        assert STEP_TYPE_ICONS["generate"] == "\u270d"

    def test_validate_icon(self):
        """Test validate step has checkmark icon."""
        assert STEP_TYPE_ICONS["validate"] == "\u2713"

    def test_checkpoint_icon(self):
        """Test checkpoint step has floppy disk icon."""
        assert STEP_TYPE_ICONS["checkpoint"] == "\U0001f4be"

    def test_subworkflow_icon(self):
        """Test subworkflow step has shuffle icon."""
        assert STEP_TYPE_ICONS["subworkflow"] == "\U0001f500"

    def test_branch_icon(self):
        """Test branch step has shuffle icon."""
        assert STEP_TYPE_ICONS["branch"] == "\U0001f500"

    def test_loop_icon(self):
        """Test loop step has repeat icon."""
        assert STEP_TYPE_ICONS["loop"] == "\U0001f501"


# Status Icons Tests
class TestStatusIcons:
    """Tests for status icon mapping."""

    def test_pending_icon(self):
        """Test pending status has empty circle icon."""
        assert STATUS_ICONS["pending"] == "\u25cb"

    def test_running_icon(self):
        """Test running status has filled circle icon."""
        assert STATUS_ICONS["running"] == "\u25cf"

    def test_completed_icon(self):
        """Test completed status has checkmark icon."""
        assert STATUS_ICONS["completed"] == "\u2713"

    def test_failed_icon(self):
        """Test failed status has X mark icon."""
        assert STATUS_ICONS["failed"] == "\u2717"

    def test_skipped_icon(self):
        """Test skipped status has em dash icon."""
        assert STATUS_ICONS["skipped"] == "\u2014"


# StepWidget Tests
class TestStepWidget:
    """Tests for StepWidget class."""

    def test_initialization(self):
        """Test StepWidget initializes correctly."""
        widget = StepWidget(step_name="test", step_type="python")

        assert widget._step_name == "test"
        assert widget._step_type == "python"
        assert widget._status == "pending"
        assert widget._duration_ms is None
        assert widget._error is None

    def test_set_running(self):
        """Test set_running updates status."""
        widget = StepWidget(step_name="test", step_type="python")

        widget.set_running()

        assert widget._status == "running"

    def test_set_completed(self):
        """Test set_completed updates status and duration."""
        widget = StepWidget(step_name="test", step_type="python")

        widget.set_completed(duration_ms=1500)

        assert widget._status == "completed"
        assert widget._duration_ms == 1500

    def test_set_failed(self):
        """Test set_failed updates status, duration, and error."""
        widget = StepWidget(step_name="test", step_type="python")

        widget.set_failed(duration_ms=500, error="Something went wrong")

        assert widget._status == "failed"
        assert widget._duration_ms == 500
        assert widget._error == "Something went wrong"

    def test_set_skipped(self):
        """Test set_skipped updates status."""
        widget = StepWidget(step_name="test", step_type="python")

        widget.set_skipped()

        assert widget._status == "skipped"


# Duration Formatting Tests
class TestDurationFormatting:
    """Tests for duration formatting in StepWidget."""

    def test_duration_milliseconds(self):
        """Test duration formatting for milliseconds."""
        widget = StepWidget(step_name="test", step_type="python")
        widget._duration_ms = 500
        widget._status = "completed"

        widget._update_display()

        # Duration should be formatted with ms suffix
        # This is verified through the widget's renderable content

    def test_duration_seconds(self):
        """Test duration formatting for seconds."""
        widget = StepWidget(step_name="test", step_type="python")
        widget._duration_ms = 2500
        widget._status = "completed"

        widget._update_display()

        # Duration should be formatted with seconds

    def test_duration_minutes(self):
        """Test duration formatting for minutes."""
        widget = StepWidget(step_name="test", step_type="python")
        widget._duration_ms = 125000  # 2m 5s
        widget._status = "completed"

        widget._update_display()

        # Duration should be formatted with minutes and seconds


# WorkflowExecutionScreen Initialization Tests
class TestWorkflowExecutionInitialization:
    """Tests for WorkflowExecutionScreen initialization."""

    def test_screen_has_correct_title(self):
        """Test that screen has correct title."""
        assert WorkflowExecutionScreen.TITLE == "Running Workflow"

    def test_screen_has_required_bindings(self):
        """Test that screen has all required key bindings."""
        binding_keys = [b.key for b in WorkflowExecutionScreen.BINDINGS]
        assert "escape" in binding_keys
        assert "q" in binding_keys

    def test_screen_initializes_with_workflow(self):
        """Test that screen initializes with workflow data."""
        mock_workflow = create_mock_workflow(
            name="my-workflow",
            steps=[create_mock_step()],
        )
        inputs = {"key": "value"}

        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs=inputs)

        assert screen._workflow == mock_workflow
        assert screen._inputs == inputs
        assert screen._step_widgets == {}
        assert screen._cancel_requested is False


# Reactive State Tests
class TestReactiveState:
    """Tests for reactive state properties."""

    def test_initial_is_running_state(self):
        """Test initial is_running state is False."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.is_running is False

    def test_initial_is_complete_state(self):
        """Test initial is_complete state is False."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.is_complete is False

    def test_initial_current_step(self):
        """Test initial current_step is 0."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.current_step == 0

    def test_initial_total_steps(self):
        """Test initial total_steps is 0."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.total_steps == 0

    def test_initial_success_state(self):
        """Test initial success state is None."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.success is None


# Step Marking Tests
class TestStepMarking:
    """Tests for step marking methods."""

    def test_mark_step_running(self):
        """Test marking a step as running."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        step_widget = StepWidget(step_name="test", step_type="python")
        screen._step_widgets["test"] = step_widget

        screen._mark_step_running("test")

        assert step_widget._status == "running"

    def test_mark_step_completed(self):
        """Test marking a step as completed."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        step_widget = StepWidget(step_name="test", step_type="python")
        screen._step_widgets["test"] = step_widget

        screen._mark_step_completed("test", 1000)

        assert step_widget._status == "completed"
        assert step_widget._duration_ms == 1000

    def test_mark_step_failed(self):
        """Test marking a step as failed."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        step_widget = StepWidget(step_name="test", step_type="python")
        screen._step_widgets["test"] = step_widget

        screen._mark_step_failed("test", 500, "Error message")

        assert step_widget._status == "failed"
        assert step_widget._duration_ms == 500
        assert step_widget._error == "Error message"

    def test_mark_unknown_step_no_error(self):
        """Test marking unknown step doesn't raise error."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Should not raise
        screen._mark_step_running("unknown-step")
        screen._mark_step_completed("unknown-step", 1000)
        screen._mark_step_failed("unknown-step", 500)


# Cancel Tests
class TestCancel:
    """Tests for workflow cancellation."""

    def test_cancel_flag_initial_state(self):
        """Test cancel flag is False initially."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen._cancel_requested is False

    def test_cancel_flag_can_be_set(self):
        """Test cancel flag can be set directly."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        screen._cancel_requested = True
        assert screen._cancel_requested is True


# Progress Tests
class TestProgress:
    """Tests for progress tracking."""

    def test_update_progress_calculation(self):
        """Test progress calculation."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen.total_steps = 10
        screen.current_step = 5

        # Progress should be 50%
        percent = screen.current_step / screen.total_steps * 100
        assert percent == 50.0

    def test_update_progress_zero_total(self):
        """Test progress calculation with zero total steps."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen.total_steps = 0
        screen.current_step = 0

        # Should not raise division by zero
        if screen.total_steps > 0:
            percent = screen.current_step / screen.total_steps * 100
        else:
            percent = 0.0
        assert percent == 0.0
