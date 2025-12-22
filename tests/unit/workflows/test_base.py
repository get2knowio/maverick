"""Unit tests for WorkflowDSLMixin base class.

Tests the common DSL integration utilities used by workflow implementations.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maverick.workflows.base import WorkflowDSLMixin


class TestWorkflowDSLMixin:
    """Tests for WorkflowDSLMixin."""

    def test_init_sets_use_dsl_to_false(self) -> None:
        """Test __init__ initializes _use_dsl to False."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            """Concrete implementation for testing."""

            pass

        workflow = ConcreteWorkflow()

        assert hasattr(workflow, "_use_dsl")
        assert workflow._use_dsl is False

    def test_enable_dsl_execution_sets_flag(self) -> None:
        """Test enable_dsl_execution sets _use_dsl to True."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            """Concrete implementation for testing."""

            pass

        workflow = ConcreteWorkflow()

        assert workflow._use_dsl is False

        workflow.enable_dsl_execution()

        assert workflow._use_dsl is True

    def test_load_workflow_calls_builtin_library(self) -> None:
        """Test _load_workflow uses builtin library to load workflow."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            """Concrete implementation for testing."""

            pass

        workflow = ConcreteWorkflow()

        # Mock the builtin library
        mock_library = MagicMock()
        mock_workflow_file = MagicMock()
        mock_workflow_file.name = "test-workflow"
        mock_library.get_workflow.return_value = mock_workflow_file

        with patch(
            "maverick.workflows.base.create_builtin_library", return_value=mock_library
        ):
            result = workflow._load_workflow("test-workflow")

        # Verify library was called correctly
        mock_library.get_workflow.assert_called_once_with("test-workflow")
        assert result == mock_workflow_file

    def test_load_workflow_raises_on_missing_workflow(self) -> None:
        """Test _load_workflow raises KeyError for non-existent workflow."""

        class ConcreteWorkflow(WorkflowDSLMixin):
            """Concrete implementation for testing."""

            pass

        workflow = ConcreteWorkflow()

        # Mock the builtin library to raise KeyError
        mock_library = MagicMock()
        mock_library.get_workflow.side_effect = KeyError("Workflow not found")

        with (
            patch(
                "maverick.workflows.base.create_builtin_library",
                return_value=mock_library,
            ),
            pytest.raises(KeyError, match="Workflow not found"),
        ):
            workflow._load_workflow("non-existent")

    def test_mixin_works_with_inheritance_chain(self) -> None:
        """Test mixin works correctly in an inheritance chain."""

        class BaseWorkflow:
            """Base workflow class."""

            def __init__(self) -> None:
                self.base_attr = "base"

        class ConcreteWorkflow(WorkflowDSLMixin, BaseWorkflow):
            """Concrete implementation with multiple inheritance."""

            def __init__(self) -> None:
                super().__init__()
                self.concrete_attr = "concrete"

        workflow = ConcreteWorkflow()

        # Verify all attributes exist
        assert hasattr(workflow, "_use_dsl")
        assert hasattr(workflow, "base_attr")
        assert hasattr(workflow, "concrete_attr")

        # Verify mixin methods work
        assert workflow._use_dsl is False
        workflow.enable_dsl_execution()
        assert workflow._use_dsl is True
