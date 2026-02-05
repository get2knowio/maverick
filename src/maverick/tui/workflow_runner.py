"""TUI workflow runner for executing workflows in the TUI.

This module provides the entry point for running workflows in TUI mode,
launching a dedicated workflow execution app.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Static

if TYPE_CHECKING:
    from maverick.dsl.serialization.schema import WorkflowFile
    from maverick.tui.screens.workflow_execution import WorkflowExecutionScreen

__all__ = ["run_workflow_in_tui"]


class WorkflowExecutionApp(App[None]):
    """Dedicated app for running workflow execution in TUI mode.

    This is a minimal App that only shows the WorkflowExecutionScreen,
    without the HomeScreen and other navigation that MaverickApp provides.
    This ensures the workflow execution is not interrupted by home screen.
    """

    CSS_PATH = Path(__file__).parent / "maverick.tcss"
    TITLE = "Maverick - Workflow Execution"
    ENABLE_COMMAND_PALETTE = False

    # Minimum terminal size requirements
    MIN_WIDTH = 80
    MIN_HEIGHT = 24

    BINDINGS = [
        Binding("ctrl+l", "toggle_log", "Toggle Log", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        workflow: WorkflowFile,
        inputs: dict[str, Any],
        session_log_path: Path | None = None,
    ) -> None:
        """Initialize the workflow execution app.

        Args:
            workflow: The workflow to execute.
            inputs: Input values for the workflow.
            session_log_path: If provided, write session journal to this file.
        """
        super().__init__()
        self._workflow = workflow
        self._inputs = inputs
        self._session_log_path = session_log_path
        self._timer_start: float | None = None
        self._timer_running: bool = False
        self._current_workflow: str = ""
        self._execution_screen: WorkflowExecutionScreen | None = None

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header()
        with Horizontal(id="main-container"):
            # Minimal sidebar showing workflow name
            with Vertical(id="sidebar"):
                yield Static("Workflow", classes="sidebar-title")
                yield Static(
                    f"Running: {self._workflow.name}",
                    id="workflow-status",
                    classes="nav-item",
                )
            yield Vertical(id="content-area")
        # Import here to avoid circular imports
        from maverick.tui.widgets.log_panel import LogPanel

        yield LogPanel(id="log-panel")
        yield Footer()
        # Minimum size warning overlay (hidden by default)
        with Container(id="min-size-warning"):
            yield Static(
                (
                    "[bold red]Terminal Too Small[/bold red]\n\n"
                    f"Minimum size: {self.MIN_WIDTH}x{self.MIN_HEIGHT}\n"
                    "Please resize your terminal."
                ),
                id="min-size-warning-text",
            )

    async def on_mount(self) -> None:
        """Initialize app and show the workflow execution screen."""
        # Import here to avoid circular imports
        from maverick.tui.screens.workflow_execution import WorkflowExecutionScreen

        # Check initial terminal size
        self._check_terminal_size()

        # Set up timer interval to update header subtitle every second
        self.set_interval(1.0, self._update_header_subtitle)

        # Set workflow info and start timer
        self.set_workflow_info(self._workflow.name)
        self.start_timer()

        # Create and push the execution screen
        self._execution_screen = WorkflowExecutionScreen(
            workflow=self._workflow,
            inputs=self._inputs,
            session_log_path=self._session_log_path,
        )
        await self.push_screen(self._execution_screen)

    def on_resize(self) -> None:
        """Handle terminal resize events."""
        self._check_terminal_size()

    def _check_terminal_size(self) -> None:
        """Check terminal size and show/hide warning overlay."""
        width = self.size.width
        height = self.size.height

        try:
            warning = self.query_one("#min-size-warning", Container)
            if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
                warning.add_class("visible")
            else:
                warning.remove_class("visible")
        except NoMatches:
            # Widget not yet mounted, skip size check
            pass

    def action_toggle_log(self) -> None:
        """Toggle log panel visibility (Ctrl+L)."""
        from maverick.tui.widgets.log_panel import LogPanel

        try:
            log_panel = self.query_one(LogPanel)
            log_panel.toggle()
        except NoMatches:
            # Widget not yet mounted, skip toggle
            pass

    async def action_quit(self) -> None:
        """Quit the application (q)."""
        self.exit()

    def add_log(
        self,
        message: str,
        level: str = "info",
        source: str = "",
    ) -> None:
        """Add a log entry to the log panel."""
        from maverick.tui.widgets.log_panel import LogPanel

        try:
            log_panel = self.query_one(LogPanel)
            log_panel.add_log(message, level, source)
        except NoMatches:
            # Widget not yet mounted, skip logging
            pass

    def start_timer(self) -> None:
        """Start the elapsed time timer."""
        self._timer_start = time.time()
        self._timer_running = True

    def stop_timer(self) -> None:
        """Stop the elapsed time timer."""
        self._timer_running = False

    @property
    def elapsed_time(self) -> float:
        """Get current elapsed time in seconds."""
        if self._timer_start is None:
            return 0.0
        if self._timer_running:
            return time.time() - self._timer_start
        return 0.0

    def set_workflow_info(self, workflow_name: str, branch_name: str = "") -> None:
        """Set the current workflow info in the header."""
        self._current_workflow = workflow_name
        self._update_header_subtitle()

    def _update_header_subtitle(self) -> None:
        """Update the header subtitle with workflow info and elapsed time."""
        if self._current_workflow:
            elapsed = self.elapsed_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            subtitle = f"{self._current_workflow} - {time_str}"
            try:
                header = self.query_one(Header)
                header.subtitle = subtitle  # type: ignore[attr-defined]
            except NoMatches:
                # Widget not yet mounted, skip update
                pass


async def run_workflow_in_tui(
    workflow_file: Path | None,
    workflow_name: str,
    inputs: dict[str, Any],
    restart: bool = False,
    validate: bool = True,
    only_step: int | None = None,
    session_log_path: Path | None = None,
) -> int:
    """Run a workflow in TUI mode.

    Launches a dedicated workflow execution app with the WorkflowExecutionScreen,
    executing the specified workflow with real-time progress display.

    This function is async to support being called from within an existing
    event loop (e.g., from @async_command decorated CLI handlers).

    Args:
        workflow_file: Path to the workflow file (if loading from file).
        workflow_name: Name of the workflow (for display and discovery).
        inputs: Input values for the workflow.
        restart: Whether to ignore checkpoint and restart from beginning.
        validate: Whether to validate before execution.
        only_step: If set, run only this step index.
        session_log_path: If provided, write session journal to this file.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    # Ensure .env is loaded (may have been missed if entry point was different)
    from dotenv import load_dotenv

    load_dotenv()

    from maverick.dsl.discovery import create_discovery
    from maverick.dsl.serialization import parse_workflow
    from maverick.tui.logging_handler import configure_tui_logging

    # Load workflow
    workflow_obj = None

    if workflow_file and workflow_file.exists():
        # Load from file
        content = workflow_file.read_text(encoding="utf-8")
        workflow_obj = parse_workflow(content, validate_only=True)
    else:
        # Discover from library
        discovery = create_discovery()
        discovery_result = discovery.discover()
        discovered = discovery_result.get_workflow(workflow_name)
        if discovered:
            workflow_obj = discovered.workflow

    if workflow_obj is None:
        # Can't run TUI without a workflow, fall back to error
        import click

        click.echo(f"Error: Workflow '{workflow_name}' not found", err=True)
        return 1

    # Create the dedicated workflow execution app
    app = WorkflowExecutionApp(
        workflow=workflow_obj, inputs=inputs, session_log_path=session_log_path
    )

    # Configure logging to route to TUI (20 = logging.INFO)
    configure_tui_logging(app, level=20)

    # Run the app using run_async() since we're already in an event loop
    await app.run_async()

    # Return exit code based on execution result
    if app._execution_screen is not None and app._execution_screen.success is True:
        return 0
    return 1
