"""Tests for TUI workflow runner module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRunWorkflowInTui:
    """Tests for run_workflow_in_tui function."""

    def test_imports_are_valid(self) -> None:
        """Test that all imports in the function are valid.

        This catches import errors that would otherwise only be found
        at runtime when the function is called.
        """
        # Call the imports that happen inside the function
        # These are lazy imports, so we need to trigger them
        from maverick.dsl.discovery import create_discovery
        from maverick.dsl.serialization import parse_workflow
        from maverick.tui.logging_handler import configure_tui_logging
        from maverick.tui.screens.workflow_execution import WorkflowExecutionScreen
        from maverick.tui.workflow_runner import WorkflowExecutionApp

        # Verify the imports are callable/usable
        assert callable(create_discovery)
        assert callable(parse_workflow)
        assert WorkflowExecutionApp is not None
        assert callable(configure_tui_logging)
        assert WorkflowExecutionScreen is not None

    @pytest.mark.asyncio
    async def test_workflow_not_found_returns_error(self) -> None:
        """Test that missing workflow returns exit code 1."""
        from maverick.tui.workflow_runner import run_workflow_in_tui

        # Patch at the source module where the import comes from
        with patch("maverick.dsl.discovery.create_discovery") as mock_create:
            # Mock discovery to return no workflow
            mock_result = MagicMock()
            mock_result.get_workflow.return_value = None
            mock_create.return_value.discover.return_value = mock_result

            result = await run_workflow_in_tui(
                workflow_file=None,
                workflow_name="nonexistent-workflow",
                inputs={},
            )

            assert result == 1

    @pytest.mark.asyncio
    async def test_workflow_file_loading(self, tmp_path: Path) -> None:
        """Test that workflow file is loaded correctly."""
        from maverick.tui.workflow_runner import run_workflow_in_tui

        # Create a minimal valid workflow file
        workflow_content = """
version: "1.0"
name: test-workflow
description: Test workflow

steps:
  - name: step1
    type: python
    action: print
    args:
      - "hello"
"""
        workflow_file = tmp_path / "test.yaml"
        workflow_file.write_text(workflow_content)

        # Mock the screen to set success=True after run_async completes
        mock_screen = MagicMock()
        mock_screen.success = True

        async def mock_run_async(self: MagicMock) -> None:
            """Mock run_async that sets up the execution screen."""
            # Simulate the screen being created and succeeding
            self._execution_screen = mock_screen

        with (
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.run_async",
                mock_run_async,
            ),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp._check_terminal_size"
            ),
            patch("maverick.tui.workflow_runner.WorkflowExecutionApp.set_interval"),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.set_workflow_info"
            ),
            patch("maverick.tui.workflow_runner.WorkflowExecutionApp.start_timer"),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.push_screen",
                new_callable=AsyncMock,
            ),
            patch("maverick.tui.logging_handler.configure_tui_logging"),
            patch(
                "maverick.tui.screens.workflow_execution.WorkflowExecutionScreen"
            ) as mock_screen_class,
        ):
            mock_screen_class.return_value = mock_screen

            result = await run_workflow_in_tui(
                workflow_file=workflow_file,
                workflow_name="test-workflow",
                inputs={},
            )

            # Success should return 0
            assert result == 0

    @pytest.mark.asyncio
    async def test_workflow_discovery_fallback(self) -> None:
        """Test that workflow discovery is used when no file provided."""
        from maverick.tui.workflow_runner import run_workflow_in_tui

        mock_screen = MagicMock()
        mock_screen.success = True

        async def mock_run_async(self: MagicMock) -> None:
            self._execution_screen = mock_screen

        with (
            patch("maverick.dsl.discovery.create_discovery") as mock_create,
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.run_async",
                mock_run_async,
            ),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp._check_terminal_size"
            ),
            patch("maverick.tui.workflow_runner.WorkflowExecutionApp.set_interval"),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.set_workflow_info"
            ),
            patch("maverick.tui.workflow_runner.WorkflowExecutionApp.start_timer"),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.push_screen",
                new_callable=AsyncMock,
            ),
            patch("maverick.tui.logging_handler.configure_tui_logging"),
            patch(
                "maverick.tui.screens.workflow_execution.WorkflowExecutionScreen"
            ) as mock_screen_class,
        ):
            # Set up mock workflow from discovery
            mock_workflow = MagicMock()
            mock_workflow.name = "discovered-workflow"

            mock_discovered = MagicMock()
            mock_discovered.workflow = mock_workflow

            mock_result = MagicMock()
            mock_result.get_workflow.return_value = mock_discovered

            mock_discovery = MagicMock()
            mock_discovery.discover.return_value = mock_result
            mock_create.return_value = mock_discovery

            mock_screen_class.return_value = mock_screen

            result = await run_workflow_in_tui(
                workflow_file=None,
                workflow_name="discovered-workflow",
                inputs={"key": "value"},
            )

            # Verify discovery was called
            mock_create.assert_called_once()
            mock_discovery.discover.assert_called_once()
            mock_result.get_workflow.assert_called_once_with("discovered-workflow")

            # Success should return 0
            assert result == 0

    @pytest.mark.asyncio
    async def test_failure_returns_exit_code_1(self, tmp_path: Path) -> None:
        """Test that workflow failure returns exit code 1."""
        from maverick.tui.workflow_runner import run_workflow_in_tui

        workflow_content = """
version: "1.0"
name: failing-workflow
description: Test workflow

steps:
  - name: step1
    type: python
    action: print
    args:
      - "hello"
"""
        workflow_file = tmp_path / "test.yaml"
        workflow_file.write_text(workflow_content)

        mock_screen = MagicMock()
        mock_screen.success = False

        async def mock_run_async(self: MagicMock) -> None:
            self._execution_screen = mock_screen

        with (
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.run_async",
                mock_run_async,
            ),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp._check_terminal_size"
            ),
            patch("maverick.tui.workflow_runner.WorkflowExecutionApp.set_interval"),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.set_workflow_info"
            ),
            patch("maverick.tui.workflow_runner.WorkflowExecutionApp.start_timer"),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.push_screen",
                new_callable=AsyncMock,
            ),
            patch("maverick.tui.logging_handler.configure_tui_logging"),
            patch(
                "maverick.tui.screens.workflow_execution.WorkflowExecutionScreen"
            ) as mock_screen_class,
        ):
            mock_screen_class.return_value = mock_screen

            result = await run_workflow_in_tui(
                workflow_file=workflow_file,
                workflow_name="failing-workflow",
                inputs={},
            )

            assert result == 1

    @pytest.mark.asyncio
    async def test_none_success_returns_exit_code_1(self, tmp_path: Path) -> None:
        """Test that None success (not yet set) returns exit code 1."""
        from maverick.tui.workflow_runner import run_workflow_in_tui

        workflow_content = """
version: "1.0"
name: test-workflow
description: Test workflow

steps:
  - name: step1
    type: python
    action: print
    args:
      - "hello"
"""
        workflow_file = tmp_path / "test.yaml"
        workflow_file.write_text(workflow_content)

        mock_screen = MagicMock()
        mock_screen.success = None

        async def mock_run_async(self: MagicMock) -> None:
            self._execution_screen = mock_screen

        with (
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.run_async",
                mock_run_async,
            ),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp._check_terminal_size"
            ),
            patch("maverick.tui.workflow_runner.WorkflowExecutionApp.set_interval"),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.set_workflow_info"
            ),
            patch("maverick.tui.workflow_runner.WorkflowExecutionApp.start_timer"),
            patch(
                "maverick.tui.workflow_runner.WorkflowExecutionApp.push_screen",
                new_callable=AsyncMock,
            ),
            patch("maverick.tui.logging_handler.configure_tui_logging"),
            patch(
                "maverick.tui.screens.workflow_execution.WorkflowExecutionScreen"
            ) as mock_screen_class,
        ):
            mock_screen_class.return_value = mock_screen

            result = await run_workflow_in_tui(
                workflow_file=workflow_file,
                workflow_name="test-workflow",
                inputs={},
            )

            # None is not True, so should return 1
            assert result == 1


class TestWorkflowExecutionApp:
    """Tests for WorkflowExecutionApp class."""

    def test_app_can_be_instantiated(self) -> None:
        """Test that WorkflowExecutionApp can be instantiated."""
        from maverick.tui.workflow_runner import WorkflowExecutionApp

        mock_workflow = MagicMock()
        mock_workflow.name = "test-workflow"

        app = WorkflowExecutionApp(workflow=mock_workflow, inputs={"key": "value"})

        assert app._workflow == mock_workflow
        assert app._inputs == {"key": "value"}
        assert app._execution_screen is None

    def test_timer_methods(self) -> None:
        """Test timer start/stop methods."""
        from maverick.tui.workflow_runner import WorkflowExecutionApp

        mock_workflow = MagicMock()
        mock_workflow.name = "test-workflow"

        app = WorkflowExecutionApp(workflow=mock_workflow, inputs={})

        # Initially no timer
        assert app.elapsed_time == 0.0

        # Start timer
        app.start_timer()
        assert app._timer_running is True
        assert app._timer_start is not None

        # Stop timer
        app.stop_timer()
        assert app._timer_running is False
