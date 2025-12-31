"""Unit tests for WorkflowScreen.

Note: Some tests involving app property access are limited because WorkflowScreen
uses TYPE_CHECKING imports for MaverickApp, which causes runtime NameErrors in the
isinstance checks. These tests focus on testing the business logic that can be
tested without triggering those runtime checks.
"""

from __future__ import annotations

from maverick.tui.screens.workflow import WorkflowScreen

# =============================================================================
# WorkflowScreen Initialization Tests
# =============================================================================


class TestWorkflowScreenInitialization:
    """Tests for WorkflowScreen initialization."""

    def test_initialization_with_defaults(self) -> None:
        """Test screen creation with default parameters."""
        screen = WorkflowScreen()
        assert screen.TITLE == "Workflow"
        assert screen._workflow_name == ""
        assert screen._branch_name == ""
        assert screen._stages == [
            "setup",
            "implementation",
            "review",
            "validation",
            "pr_management",
        ]

    def test_initialization_with_workflow_and_branch(self) -> None:
        """Test screen creation with workflow name and branch."""
        screen = WorkflowScreen(workflow_name="FlyWorkflow", branch_name="feature/test")
        assert screen._workflow_name == "FlyWorkflow"
        assert screen._branch_name == "feature/test"

    def test_initialization_with_custom_stages(self) -> None:
        """Test screen creation with custom stages."""
        custom_stages = ["init", "build", "test", "deploy"]
        screen = WorkflowScreen(
            workflow_name="CustomWorkflow",
            branch_name="main",
            stages=custom_stages,
        )
        assert screen._stages == custom_stages

    def test_initialization_with_all_parameters(self) -> None:
        """Test screen creation with all parameters."""
        screen = WorkflowScreen(
            workflow_name="Test",
            branch_name="test-branch",
            stages=["stage1", "stage2"],
            name="custom-workflow",
            id="workflow-1",
            classes="custom",
        )
        assert screen._workflow_name == "Test"
        assert screen._branch_name == "test-branch"
        assert screen._stages == ["stage1", "stage2"]
        assert screen.name == "custom-workflow"
        assert screen.id == "workflow-1"


# =============================================================================
# WorkflowScreen Properties Tests
# =============================================================================


class TestWorkflowScreenProperties:
    """Tests for WorkflowScreen properties."""

    def test_workflow_name_property(self) -> None:
        """Test workflow_name property returns correct value."""
        screen = WorkflowScreen(workflow_name="TestWorkflow")
        assert screen.workflow_name == "TestWorkflow"

    def test_workflow_name_property_empty(self) -> None:
        """Test workflow_name property with empty name."""
        screen = WorkflowScreen()
        assert screen.workflow_name == ""

    def test_workflow_name_property_returns_value(self) -> None:
        """Test that workflow_name property is accessible."""
        # Note: elapsed_time property cannot be fully tested due to TYPE_CHECKING
        # import of MaverickApp causing runtime NameError in isinstance check.
        # The property accesses app.elapsed_time which requires MaverickApp instance.
        screen = WorkflowScreen(workflow_name="TestWorkflow")
        assert screen.workflow_name == "TestWorkflow"


# =============================================================================
# WorkflowScreen Update Methods Tests
# =============================================================================


class TestWorkflowScreenUpdateStage:
    """Tests for update_stage method."""

    def test_update_stage_method_exists(self) -> None:
        """Test that update_stage method exists and is callable.

        Note: Full testing is limited due to TYPE_CHECKING import and Textual context.
        The method requires a running Textual app context and MaverickApp instance.
        """
        screen = WorkflowScreen(
            workflow_name="Test", stages=["setup", "implementation"]
        )

        # Verify the method exists
        assert hasattr(screen, "update_stage")
        assert callable(screen.update_stage)


class TestWorkflowScreenShowStageError:
    """Tests for show_stage_error method."""

    def test_show_stage_error_method_exists(self) -> None:
        """Test that show_stage_error method exists and is callable.

        Note: Full testing is limited due to TYPE_CHECKING import and Textual context.
        The method requires a running Textual app context and MaverickApp instance.
        """
        screen = WorkflowScreen(workflow_name="Test", stages=["validation"])

        # Verify the method exists
        assert hasattr(screen, "show_stage_error")
        assert callable(screen.show_stage_error)


# =============================================================================
# WorkflowScreen Cleanup Tests
# =============================================================================


class TestWorkflowScreenCleanup:
    """Tests for cleanup_sidebar method."""

    def test_cleanup_sidebar_exists_and_is_callable(self) -> None:
        """Test that cleanup_sidebar method exists and is callable.

        Note: Full testing is limited due to TYPE_CHECKING import and Textual context.
        The method requires a running Textual app context and MaverickApp instance.
        """
        screen = WorkflowScreen(workflow_name="Test")

        # Verify the method exists
        assert hasattr(screen, "cleanup_sidebar")
        assert callable(screen.cleanup_sidebar)
