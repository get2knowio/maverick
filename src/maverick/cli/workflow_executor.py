"""Shared workflow execution logic.

Contains ``render_workflow_events`` — a shared event-rendering loop
used by Python workflow execution paths.

See docs/cli-output-rules.md for the rendering rules.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table

from maverick.cli.common import (
    cli_error_handler,
    create_registered_registry,
)
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from maverick.events import ProgressEvent
    from maverick.session_journal import SessionJournal
    from maverick.workflows.base import PythonWorkflow


# ---------------------------------------------------------------------------
# Agent fan-out tracker (Rich Live table)
# ---------------------------------------------------------------------------


def _display_name(step_name: str) -> str:
    """Get human-readable display name for a step identifier.

    Simply converts snake_case to Title Case. Callers that need richer
    labels should use the ``display_label`` field on events instead.
    """
    return step_name.replace("_", " ").title()


class _AgentTracker:
    """Tracks concurrent agent status and renders a Rich Live table.

    Used during fan-out phases (briefing, decompose detail) to show
    all agents in a single updating table instead of interleaved
    start/end lines.
    """

    def __init__(self, console_obj: Any, phase_name: str) -> None:
        self._console = console_obj
        self._phase_name = phase_name
        self._agents: dict[str, dict[str, str]] = {}  # label → {status, timing, provider}
        self._order: list[str] = []  # insertion order
        self._live: Live | None = None
        self._non_agent_messages: list[str] = []  # messages to show after Live ends

    @property
    def active(self) -> bool:
        return self._live is not None

    @property
    def has_pending(self) -> bool:
        return any(a["status"] == "running" for a in self._agents.values())

    def agent_started(self, label: str, provider: str) -> None:
        if label not in self._agents:
            self._order.append(label)
        self._agents[label] = {"status": "running", "timing": "", "provider": provider}
        self._ensure_live()
        self._refresh()

    def agent_completed(self, label: str, timing: str) -> None:
        if label in self._agents:
            self._agents[label]["status"] = "done"
            self._agents[label]["timing"] = timing
        self._refresh()
        if not self.has_pending:
            self._freeze()

    def add_message(self, message: str) -> None:
        """Buffer a non-agent message to show after the Live table."""
        self._non_agent_messages.append(message)

    def force_close(self) -> None:
        """Close the Live display if still open."""
        self._freeze()

    def _ensure_live(self) -> None:
        if self._live is None:
            self._live = Live(console=self._console, refresh_per_second=4)
            self._live.start()

    def _build_table(self) -> Table:
        table = Table(
            show_header=False,
            show_edge=False,
            pad_edge=False,
            box=None,
            padding=(0, 1),
        )
        table.add_column("agent", min_width=20)
        table.add_column("timing", justify="right", min_width=8)
        table.add_column("status", min_width=3)

        for label in self._order:
            info = self._agents[label]
            provider_dim = f" [dim]({info['provider']})[/]" if info["provider"] else ""
            if info["status"] == "done":
                timing = f"[dim]{info['timing']}[/]"
                table.add_row(f"  [green]∟[/] {label}{provider_dim}", timing, "[green]✓[/]")
            else:
                table.add_row(
                    f"  [cyan]∟[/] {label}{provider_dim}", "", Spinner("dots", style="cyan")
                )

        return table

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._build_table())

    def _freeze(self) -> None:
        if self._live is not None:
            # Render final table state before stopping Live
            self._refresh()
            self._live.stop()
            self._live = None
            # Print buffered non-agent messages after the Live table
            for msg in self._non_agent_messages:
                self._console.print(f"  [cyan]∟[/] {msg}")
            self._non_agent_messages.clear()


# ---------------------------------------------------------------------------
# Event renderer
# ---------------------------------------------------------------------------


async def render_workflow_events(
    events: AsyncIterator[ProgressEvent],
    console_obj: Any,
    session_journal: SessionJournal | None = None,
    workflow_name: str | None = None,
    total_steps: int | None = None,
    verbosity: int = 0,
) -> None:
    """Render workflow progress events to the console.

    Uses Rich Live tables for agent fan-out phases (briefing, decompose
    detail) and sequential output for everything else.

    Args:
        events: Async iterator of ProgressEvent instances.
        console_obj: Rich Console to render to.
        session_journal: Optional SessionJournal for logging events.
        workflow_name: Display name for the workflow (for header display).
        total_steps: Total step count for progress numbering.
        verbosity: Verbosity level. 0 = normal, 1+ = verbose.
    """
    from maverick.events import (
        AgentCompleted,
        AgentStarted,
        AgentStreamChunk,
        CheckpointSaved,
        LoopIterationCompleted,
        LoopIterationStarted,
        PreflightCheckFailed,
        PreflightCheckPassed,
        PreflightCompleted,
        PreflightStarted,
        RollbackCompleted,
        RollbackStarted,
        StepCompleted,
        StepOutput,
        StepStarted,
        ValidationCompleted,
        ValidationFailed,
        ValidationStarted,
        WorkflowCompleted,
        WorkflowStarted,
    )

    step_index = 0
    workflow_depth = 0
    _total_steps = total_steps if total_steps is not None else 0
    _agent_streaming = False
    _verbose = verbosity > 0

    # State machine for step rendering
    _header_printed = False
    _current_label: str = ""
    _first_interim: str | None = None  # buffered for collapsing
    _agent_tracker: _AgentTracker | None = None
    _spinner: Any = None
    _progress_live: Any = None  # Rich Live for detail progress counter

    def _ensure_header() -> None:
        """Print the step header if not yet printed."""
        nonlocal _header_printed, _spinner
        if not _header_printed and _current_label:
            if _spinner:
                _spinner.stop()
                _spinner = None
            console_obj.print(f"[bold]{_current_label}[/]")
            _header_printed = True

    _level_styles = {
        "info": "[cyan]",
        "success": "[green]",
        "warning": "[yellow]",
        "error": "[red]",
    }

    async for event in events:
        if session_journal is not None:
            await session_journal.record(event)

        if isinstance(event, ValidationStarted):
            console_obj.print("[cyan]Validating workflow...[/]", end="")

        elif isinstance(event, ValidationCompleted):
            console_obj.print(" [bold green]✓[/]")
            if event.warnings_count > 0:
                console_obj.print(f"  [yellow]({event.warnings_count} warning(s))[/]")
            console_obj.print()

        elif isinstance(event, ValidationFailed):
            console_obj.print(" [bold red]✗[/]")
            console_obj.print()
            error_msg = format_error(
                "Workflow validation failed",
                details=list(event.errors),
                suggestion="Fix validation errors and try again",
            )
            err_console.print(error_msg)
            raise SystemExit(ExitCode.FAILURE)

        elif isinstance(event, PreflightStarted):
            if event.prerequisites:
                console_obj.print("[cyan]Running preflight checks...[/]")

        elif isinstance(event, PreflightCheckPassed):
            console_obj.print(f"  [green]✓[/] [bold]{event.name}[/]")

        elif isinstance(event, PreflightCheckFailed):
            console_obj.print(f"  [red]✗[/] [bold]{event.name}[/]: {event.message}")
            if event.remediation:
                console_obj.print(f"    [dim]Hint: {event.remediation}[/]")

        elif isinstance(event, PreflightCompleted):
            if not event.success:
                error_msg = format_error(
                    "Preflight checks failed",
                    suggestion="Install missing prerequisites and try again.",
                )
                err_console.print(error_msg)
            console_obj.print()

        elif isinstance(event, WorkflowStarted):
            workflow_depth += 1

        elif isinstance(event, StepStarted):
            _current_label = event.display_label or _display_name(event.step_name)
            _header_printed = False
            _first_interim = None
            step_type_value = event.step_type.value

            if workflow_depth == 1:
                step_index += 1
                if step_type_value in ("agent", "python") and hasattr(console_obj, "status"):
                    _spinner = console_obj.status(
                        f"[dim]{_current_label}...[/]",
                        spinner="dots",
                    )
                    _spinner.start()

                if step_type_value in ("loop", "subworkflow"):
                    workflow_depth += 1
            else:
                indent = "  " * (workflow_depth - 1)
                console_obj.print(f"[dim]{indent}{_current_label}[/]")
                _header_printed = True

        elif isinstance(event, StepCompleted):
            if event.step_type.value in ("loop", "subworkflow"):
                workflow_depth = max(1, workflow_depth - 1)

            if _spinner:
                _spinner.stop()
                _spinner = None

            # Close progress live display
            if _progress_live is not None:
                _progress_live.stop()
                _progress_live = None

            # Close any active agent tracker
            if _agent_tracker is not None and _agent_tracker.active:
                _agent_tracker.force_close()
            _agent_tracker = None

            if _agent_streaming:
                console_obj.print()
                _agent_streaming = False

            label = event.display_label or _current_label or _display_name(event.step_name)
            dur = f"{event.duration_ms / 1000:.2f}s"
            icon = "[green]✓[/]" if event.success else "[red]✗[/]"

            # Collapse: if header wasn't printed and we have a buffered
            # interim, show one line using the interim as the message.
            if not _header_printed and _first_interim and not event.error:
                console_obj.print(f"{icon} {_first_interim} [dim]({dur})[/]")
            elif event.error:
                _ensure_header()
                if _first_interim:
                    style = _level_styles.get("info", "[cyan]")
                    console_obj.print(f"  {style}∟[/] {_first_interim}")
                console_obj.print(f"{icon} {label}: {event.error} [dim]({dur})[/]")
            elif not _header_printed:
                # No interims at all — just show the label
                console_obj.print(f"{icon} {label} [dim]({dur})[/]")
            else:
                # Header was printed (multi-interim step) — show completion
                if _first_interim:
                    style = _level_styles.get("info", "[cyan]")
                    console_obj.print(f"  {style}∟[/] {_first_interim}")
                console_obj.print(f"{icon} {label} [dim]({dur})[/]")
            _header_printed = False
            _first_interim = None

        elif isinstance(event, AgentStreamChunk):
            if _verbose:
                text = event.text
                if text.startswith("[TOOL] "):
                    tool_name = text.removeprefix("[TOOL] ").strip()
                    console_obj.print(f"[dim]  ↳ {tool_name}[/]")
                else:
                    if not _agent_streaming:
                        _agent_streaming = True
                    console_obj.print(
                        text,
                        end="",
                        highlight=False,
                        markup=False,
                    )

        elif isinstance(event, AgentStarted):
            if _agent_tracker is None or not _agent_tracker.active:
                _ensure_header()
                _agent_tracker = _AgentTracker(console_obj, event.step_name)
            _agent_tracker.agent_started(event.agent_name, event.provider)

        elif isinstance(event, AgentCompleted):
            if _agent_tracker is not None:
                _agent_tracker.agent_completed(event.agent_name, f"{event.duration_seconds:.1f}s")

        elif isinstance(event, StepOutput):
            if _agent_tracker is not None and _agent_tracker.active:
                _agent_tracker.add_message(event.message)
            elif not _header_printed and not _first_interim:
                # Buffer first interim — enables collapsing for simple steps
                _first_interim = event.message
            else:
                # Check for progress-counter messages (e.g., "Detail 3/45 complete")
                # and render as a single updating line instead of 45 separate lines.
                import re as _re

                _progress_match = _re.match(r"^Detail (\d+)/(\d+) complete$", event.message)
                if _progress_match:
                    done_n, total_n = _progress_match.groups()
                    # Overwrite the previous progress line using Rich Live
                    if _first_interim:
                        _ensure_header()
                        style = _level_styles.get("info", "[cyan]")
                        console_obj.print(f"  {style}∟[/] {_first_interim}")
                        _first_interim = None
                    _ensure_header()
                    # Use carriage return to overwrite progress in-place
                    if _progress_live is None:
                        _progress_live = Live(console=console_obj, refresh_per_second=4)
                        _progress_live.start()
                    from rich.text import Text

                    _progress_live.update(
                        Text(
                            f"  ∟ Details: {done_n}/{total_n} complete",
                            style="cyan",
                        )
                    )
                else:
                    # Stop progress live if it was running
                    if _progress_live is not None:
                        _progress_live.stop()
                        _progress_live = None
                    # Second+ interim — flush header and all interims
                    if _first_interim:
                        _ensure_header()
                        style = _level_styles.get("info", "[cyan]")
                        console_obj.print(f"  {style}∟[/] {_first_interim}")
                        _first_interim = None
                    _ensure_header()
                    style = _level_styles.get(event.level, "[cyan]")
                    console_obj.print(f"  {style}∟[/] {event.message}")

        elif isinstance(event, RollbackStarted):
            console_obj.print(f"[yellow]  ↩ Rolling back: {event.step_name}...[/]")

        elif isinstance(event, RollbackCompleted):
            if event.success:
                console_obj.print(f"[green]  ✓ Rollback succeeded: {event.step_name}[/]")
            else:
                error_detail = f" ({event.error})" if event.error else ""
                console_obj.print(f"[red]  ✗ Rollback failed: {event.step_name}{error_detail}[/]")

        elif isinstance(event, LoopIterationStarted):
            label = event.item_label or f"iteration {event.iteration_index + 1}"
            total = event.total_iterations
            idx = event.iteration_index + 1
            console_obj.print(f"\n[cyan]── [{idx}/{total}] {label} ──[/]")

        elif isinstance(event, LoopIterationCompleted):
            duration_sec = event.duration_ms / 1000
            if event.success:
                console_obj.print(
                    f"[dim]  Iteration {event.iteration_index + 1}"
                    f" completed ({duration_sec:.2f}s)[/]"
                )
            else:
                error_detail = f": {event.error}" if event.error else ""
                console_obj.print(
                    f"[red]  Iteration {event.iteration_index + 1}"
                    f" failed ({duration_sec:.2f}s){error_detail}[/]"
                )

        elif isinstance(event, CheckpointSaved):
            label = event.step_name.replace("_", " ").title()
            console_obj.print(f"[dim]  Checkpoint saved: {label}[/]")

        elif isinstance(event, WorkflowCompleted):
            if _spinner:
                _spinner.stop()
                _spinner = None
            if _agent_tracker is not None and _agent_tracker.active:
                _agent_tracker.force_close()
            _agent_tracker = None

            workflow_depth -= 1

            if workflow_depth > 0:
                total_sec = event.total_duration_ms / 1000
                console_obj.print(f"[dim]({total_sec:.2f}s)[/]")
                continue

            console_obj.print()
            total_sec = event.total_duration_ms / 1000

            if event.success:
                console_obj.print(
                    f"[bold green]Workflow completed successfully[/] in {total_sec:.2f}s"
                )
            else:
                console_obj.print(f"[bold red]Workflow failed[/] after {total_sec:.2f}s")


@dataclass
class PythonWorkflowRunConfig:
    """Configuration for executing a Python workflow from the CLI.

    Attributes:
        workflow_class: PythonWorkflow subclass to instantiate and run.
        inputs: Input dictionary to pass to the workflow.
        session_log_path: Optional path to write session journal (JSONL).
        restart: If True, clear existing checkpoint before running.
    """

    workflow_class: type[PythonWorkflow]
    inputs: dict[str, Any] = field(default_factory=dict)
    session_log_path: Path | None = None
    restart: bool = False


async def execute_python_workflow(
    ctx: click.Context,
    run_config: PythonWorkflowRunConfig,
) -> None:
    """Execute a PythonWorkflow subclass from a CLI command.

    Handles:
    - Registry creation and dependency injection
    - Checkpoint loading and resume logic
    - Event rendering via ``render_workflow_events``
    - Session journal (JSONL) recording
    - Error handling and exit codes

    Args:
        ctx: Click context for accessing CLI-level settings.
        run_config: Configuration for the workflow execution.
    """
    from maverick.checkpoint.store import FileCheckpointStore
    from maverick.session_journal import SessionJournal

    # Extract workflow name from the workflow class's module WORKFLOW_NAME constant.
    _wf_module = importlib.import_module(run_config.workflow_class.__module__)
    workflow_name = getattr(_wf_module, "WORKFLOW_NAME", run_config.workflow_class.__name__)

    with cli_error_handler():
        from maverick.config import load_config

        config = load_config()
        registry = create_registered_registry()
        workflow_class = run_config.workflow_class

        # Ensure workflow_class is a class, not a string.
        if isinstance(workflow_class, str):
            module_path, class_name = workflow_class.rsplit(".", 1)
            module = importlib.import_module(module_path)
            workflow_class = getattr(module, class_name)

        # Checkpoint support
        checkpoint_dir = Path(".maverick/checkpoints")
        checkpoint_store = FileCheckpointStore(checkpoint_dir)

        # Instantiate workflow — actors create their own ACP executors
        wf = workflow_class(
            config=config,
            registry=registry,
            checkpoint_store=checkpoint_store,
        )

        if run_config.restart:
            await checkpoint_store.clear(workflow_name)
            console.print("[yellow]Cleared existing checkpoint.[/]")
            console.print()
        else:
            existing = await checkpoint_store.load_latest(workflow_name)
            if existing:
                console.print(
                    f"[cyan]Resuming from checkpoint "
                    f"'{existing.checkpoint_id}' "
                    f"(saved at {existing.saved_at})[/]"
                )
                console.print()

        # Display workflow header.
        console.print(f"[bold cyan]Executing workflow: {workflow_name}[/]")
        if run_config.inputs:
            parts: list[str] = []
            for k, v in run_config.inputs.items():
                s = str(v)
                if len(s) > 120:
                    s = f"({len(s):,} chars)"
                parts.append(f"{k}=[yellow]{s}[/]")
            console.print(f"Inputs: {', '.join(parts)}")
        else:
            console.print("Inputs: (none)")
        console.print()

        # Set up session journal if requested.
        journal: SessionJournal | None = None
        if run_config.session_log_path is not None:
            journal = SessionJournal(run_config.session_log_path)
            journal.write_header(workflow_name, run_config.inputs)
            console.print(f"[dim]Session log: {run_config.session_log_path}[/]")

        # Determine verbosity from Click context.
        verbosity = ctx.obj.get("verbosity", 0) if ctx.obj else 0

        # Count workflow steps for progress display.
        steps_meta = getattr(workflow_class, "STEPS", None) or {}
        step_count = len(steps_meta) if isinstance(steps_meta, dict) else 0

        # Run the workflow and render events.
        events = wf.execute(run_config.inputs)

        try:
            await render_workflow_events(
                events,
                console,
                session_journal=journal,
                workflow_name=workflow_name,
                total_steps=step_count,
                verbosity=verbosity,
            )
        except SystemExit:
            raise
        except Exception as exc:
            console.print()
            err_console.print(
                format_error(
                    "Workflow failed after execution",
                    details=[str(exc)],
                )
            )
            raise SystemExit(ExitCode.FAILURE) from exc
