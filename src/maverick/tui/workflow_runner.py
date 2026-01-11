"""TUI workflow runner for executing workflows in the TUI.

This module provides the entry point for running workflows in TUI mode,
launching the MaverickApp and pushing the WorkflowExecutionScreen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["run_workflow_in_tui"]


def run_workflow_in_tui(
    workflow_file: Path | None,
    workflow_name: str,
    inputs: dict[str, Any],
    resume: bool = False,
    validate: bool = True,
    only_step: int | None = None,
) -> int:
    """Run a workflow in TUI mode.

    Launches the MaverickApp with the WorkflowExecutionScreen,
    executing the specified workflow with real-time progress display.

    Args:
        workflow_file: Path to the workflow file (if loading from file).
        workflow_name: Name of the workflow (for display and discovery).
        inputs: Input values for the workflow.
        resume: Whether to resume from checkpoint.
        validate: Whether to validate before execution.
        only_step: If set, run only this step index.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    import logging

    from maverick.dsl.discovery import get_discovery_result
    from maverick.dsl.serialization import parse_workflow
    from maverick.tui.app import MaverickApp
    from maverick.tui.logging_handler import configure_tui_logging
    from maverick.tui.screens.workflow_execution import WorkflowExecutionScreen

    # Load workflow
    workflow_obj = None

    if workflow_file and workflow_file.exists():
        # Load from file
        content = workflow_file.read_text(encoding="utf-8")
        workflow_obj = parse_workflow(content, validate_only=True)
    else:
        # Discover from library
        discovery_result = get_discovery_result()
        discovered = discovery_result.get_workflow(workflow_name)
        if discovered:
            workflow_obj = discovered.workflow

    if workflow_obj is None:
        # Can't run TUI without a workflow, fall back to error
        import click

        click.echo(f"Error: Workflow '{workflow_name}' not found", err=True)
        return 1

    # Create the app
    app = MaverickApp()

    # Configure logging to route to TUI
    configure_tui_logging(app, level=logging.INFO)

    # Create execution screen with workflow and inputs
    execution_screen = WorkflowExecutionScreen(
        workflow=workflow_obj,
        inputs=inputs,
    )

    # Override on_mount to push execution screen after home screen
    original_on_mount = app.on_mount

    async def custom_on_mount() -> None:
        """Custom mount that skips home and goes directly to execution."""
        # Check initial terminal size
        app._check_terminal_size()
        # Set up timer interval
        app.set_interval(1.0, app._update_header_subtitle)
        # Set workflow info in header
        app.set_workflow_info(workflow_obj.name)
        app.start_timer()
        # Push execution screen directly
        await app.push_screen(execution_screen)

    app.on_mount = custom_on_mount  # type: ignore[method-assign]

    # Run the app
    app.run()

    # Return exit code based on execution result
    if execution_screen.success is True:
        return 0
    return 1
