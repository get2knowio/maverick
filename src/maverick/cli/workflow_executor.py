"""Shared workflow execution logic.

Contains ``render_workflow_events`` — a shared event-rendering loop
used by Python workflow execution paths.
"""

from __future__ import annotations

import asyncio
import importlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

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


async def render_workflow_events(
    events: AsyncIterator[ProgressEvent],
    console_obj: Any,
    session_journal: SessionJournal | None = None,
    workflow_name: str | None = None,
    total_steps: int | None = None,
    verbosity: int = 0,
) -> None:
    """Render workflow progress events to the console.

    Shared event-rendering loop for Python workflow execution. Handles
    ValidationStarted/Completed/Failed, PreflightStarted/CheckPassed/
    CheckFailed/Completed, WorkflowStarted, StepStarted, StepCompleted,
    AgentStreamChunk, WorkflowCompleted, StepOutput, and
    LoopIterationStarted/Completed events.

    Args:
        events: Async iterator of ProgressEvent instances (accepts both
            AsyncGenerator and AsyncIterator).
        console_obj: Rich Console to render to.
        session_journal: Optional SessionJournal for logging events.
        workflow_name: Display name for the workflow (for header display).
        total_steps: Total step count for progress numbering. If None,
            step numbers are not shown.
        verbosity: Verbosity level. 0 = normal (agent stream suppressed),
            1+ = verbose (raw agent stream shown).
    """
    from maverick.events import (
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
    workflow_depth = 0  # Track nesting: 1 = main workflow, 2+ = subworkflows
    _total_steps = total_steps if total_steps is not None else 0
    _agent_streaming = False  # Whether we're mid-agent-stream (for newline mgmt)
    _verbose = verbosity > 0
    _spinner: Any = None  # Active Rich Status spinner, if any

    def _stop_spinner() -> None:
        nonlocal _spinner
        if _spinner is not None:
            _spinner.stop()
            _spinner = None

    async for event in events:
        # Record event to session journal if active
        if session_journal is not None:
            await session_journal.record(event)

        if isinstance(event, ValidationStarted):
            console_obj.print("[cyan]Validating workflow...[/]", end="")

        elif isinstance(event, ValidationCompleted):
            console_obj.print(" [bold green]\u2713[/]")
            if event.warnings_count > 0:
                console_obj.print(f"  [yellow]({event.warnings_count} warning(s))[/]")
            console_obj.print()

        elif isinstance(event, ValidationFailed):
            console_obj.print(" [bold red]\u2717[/]")
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
            console_obj.print(f"  [green]\u2713[/] [bold]{event.name}[/]")

        elif isinstance(event, PreflightCheckFailed):
            console_obj.print(
                f"  [red]\u2717[/] [bold]{event.name}[/]: {event.message}"
            )
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
            type_icons = {
                "python": "\u2699",
                "agent": "\U0001f916",
                "generate": "\u270d",
                "validate": "\u2713",
                "checkpoint": "\U0001f4be",
            }
            icon = type_icons.get(event.step_type.value, "\u25cf")
            step_name = event.step_name

            # Build type annotation: "provider / model" or just "python"
            type_annotation = event.step_type.value
            if event.provider or event.model_id:
                parts = [p for p in (event.provider, event.model_id) if p]
                type_annotation = " / ".join(parts)

            # Use a spinner for long-running step types (agent/python)
            _use_spinner = event.step_type.value in ("agent", "python")

            if workflow_depth == 1:
                step_index += 1
                if _total_steps > 0:
                    step_label = (
                        f"[{step_index}/{_total_steps}] "
                        f"{icon} {step_name} ({type_annotation})"
                    )
                else:
                    step_label = f"{icon} {step_name} ({type_annotation})"

                if _use_spinner and hasattr(console_obj, "status"):
                    console_obj.print(f"[blue]{step_label}[/]")
                    _spinner = console_obj.status(
                        f"[dim]{step_name}...[/]",
                        spinner="dots",
                    )
                    _spinner.start()
                else:
                    console_obj.print(
                        f"[blue]{step_label}...[/] ",
                        end="",
                    )

                if event.step_type.value in ("loop", "subworkflow"):
                    workflow_depth += 1
            else:
                indent = "  " * (workflow_depth - 1)
                console_obj.print(
                    f"[dim cyan]{indent}{icon} {step_name}[/] ({type_annotation})... ",
                    end="",
                )

        elif isinstance(event, StepCompleted):
            if event.step_type.value in ("loop", "subworkflow"):
                workflow_depth = max(1, workflow_depth - 1)

            _stop_spinner()

            # If we were streaming agent output, close that section first
            if _agent_streaming:
                console_obj.print()  # End the agent stream block
                _agent_streaming = False

            duration_sec = event.duration_ms / 1000

            if event.success:
                console_obj.print(
                    f"[bold green]\u2713[/] [dim]({duration_sec:.2f}s)[/]"
                )
            else:
                console_obj.print(f"[bold red]\u2717[/] [dim]({duration_sec:.2f}s)[/]")

        elif isinstance(event, AgentStreamChunk):
            if _verbose:
                # Verbose mode: show raw agent stream, but dim [TOOL] lines
                text = event.text
                if text.startswith("[TOOL] "):
                    tool_name = text.removeprefix("[TOOL] ").strip()
                    console_obj.print(
                        f"[dim]  \u21b3 {tool_name}[/]",
                    )
                else:
                    if not _agent_streaming:
                        _agent_streaming = True
                    console_obj.print(
                        text,
                        end="",
                        highlight=False,
                        markup=False,
                    )
            # Normal mode: suppress raw agent stream entirely.
            # Workflows should emit StepOutput events for user-facing summaries.

        elif isinstance(event, StepOutput):
            # Model announcements: suppress from output
            if (
                event.source == "acp_executor"
                and event.level == "debug"
                and event.message.startswith("model: ")
            ):
                continue
            level_styles = {
                "info": "[cyan]",
                "success": "[green]",
                "warning": "[yellow]",
                "error": "[red]",
            }
            style = level_styles.get(event.level, "[cyan]")
            prefix = f"  {style}{event.step_name}[/]: " if event.step_name else "  "
            console_obj.print(f"{prefix}{event.message}")

        elif isinstance(event, RollbackStarted):
            console_obj.print(f"[yellow]  \u21a9 Rolling back: {event.step_name}...[/]")

        elif isinstance(event, RollbackCompleted):
            if event.success:
                console_obj.print(
                    f"[green]  \u2713 Rollback succeeded: {event.step_name}[/]"
                )
            else:
                error_detail = f" ({event.error})" if event.error else ""
                console_obj.print(
                    f"[red]  \u2717 Rollback failed: {event.step_name}{error_detail}[/]"
                )

        elif isinstance(event, LoopIterationStarted):
            label = event.item_label or f"iteration {event.iteration_index + 1}"
            total = event.total_iterations
            idx = event.iteration_index + 1
            console_obj.print(
                f"\n[cyan]\u2500\u2500 [{idx}/{total}] {label} \u2500\u2500[/]"
            )

        elif isinstance(event, LoopIterationCompleted):
            duration_sec = event.duration_ms / 1000
            if event.success:
                console_obj.print(
                    f"[dim]  Iteration {event.iteration_index + 1} completed "
                    f"({duration_sec:.2f}s)[/]"
                )
            else:
                error_detail = f": {event.error}" if event.error else ""
                console_obj.print(
                    f"[red]  Iteration {event.iteration_index + 1} failed "
                    f"({duration_sec:.2f}s){error_detail}[/]"
                )

        elif isinstance(event, CheckpointSaved):
            console_obj.print(
                f"[dim]  \U0001f4be Checkpoint saved: {event.step_name}[/]"
            )

        elif isinstance(event, WorkflowCompleted):
            _stop_spinner()
            workflow_depth -= 1

            if workflow_depth > 0:
                total_sec = event.total_duration_ms / 1000
                console_obj.print(f"[dim]({total_sec:.2f}s)[/]")
                continue

            console_obj.print()
            total_sec = event.total_duration_ms / 1000

            if event.success:
                console_obj.print(
                    f"[bold green]Workflow completed successfully[/] "
                    f"in {total_sec:.2f}s"
                )
            else:
                console_obj.print(
                    f"[bold red]Workflow failed[/] after {total_sec:.2f}s"
                )


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
    """Execute a Python workflow from a CLI command.

    Instantiates a PythonWorkflow subclass, sets up the checkpoint store
    and session journal (if configured), streams events through
    ``render_workflow_events``, and displays a final summary.

    Args:
        ctx: Click context (used to retrieve MaverickConfig).
        run_config: Configuration describing which workflow to run
            and how to run it.
    """
    with cli_error_handler():
        from maverick.checkpoint.store import FileCheckpointStore
        from maverick.config import load_config
        from maverick.session_journal import SessionJournal

        # Retrieve config from CLI context (populated by the root ``cli`` group).
        config = ctx.obj.get("config") if ctx.obj else None
        if config is None:
            config = load_config()

        # Create registry with all built-in components registered.
        registry = create_registered_registry()

        # Create checkpoint store.
        checkpoint_store = FileCheckpointStore()

        # Determine workflow name from class (check WORKFLOW_NAME constant first).
        wf_cls = run_config.workflow_class
        workflow_name: str = getattr(wf_cls, "WORKFLOW_NAME", None) or (
            # Derive from constants module if available.
            _derive_workflow_name(wf_cls)
        )

        # Handle restart: clear existing checkpoint.
        if run_config.restart:
            existing = await checkpoint_store.load_latest(workflow_name)
            if existing:
                await checkpoint_store.clear(workflow_name)
                console.print(
                    "[yellow]Restarting workflow (cleared existing checkpoint)[/]"
                )
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
            input_summary = ", ".join(
                f"{k}=[yellow]{v}[/]" for k, v in run_config.inputs.items()
            )
            console.print(f"Inputs: {input_summary}")
        else:
            console.print("Inputs: (none)")
        console.print()

        # Set up session journal if requested.
        journal: SessionJournal | None = None
        if run_config.session_log_path is not None:
            journal = SessionJournal(run_config.session_log_path)
            journal.write_header(workflow_name, run_config.inputs)
            console.print(f"[dim]Session log: {run_config.session_log_path}[/]")
            console.print()

        # Create agent step executor using ACP-based executor.
        from maverick.executor.acp import AcpStepExecutor
        from maverick.executor.provider_registry import AgentProviderRegistry

        provider_registry = AgentProviderRegistry.from_config(config.agent_providers)
        step_executor = AcpStepExecutor(
            provider_registry=provider_registry,
            agent_registry=registry,
        )

        # Instantiate the workflow.
        workflow = wf_cls(
            config=config,
            registry=registry,
            checkpoint_store=checkpoint_store,
            step_executor=step_executor,
            workflow_name=workflow_name,
        )

        # Thread verbosity from CLI context to event renderer.
        cli_ctx = ctx.obj.get("cli_ctx") if ctx.obj else None
        _verbosity = getattr(cli_ctx, "verbosity", 0) if cli_ctx else 0
        # Also check raw obj dict for backwards compat.
        if _verbosity == 0 and ctx.obj:
            _verbosity = ctx.obj.get("verbose", 0)

        try:
            await render_workflow_events(
                workflow.execute(run_config.inputs),
                console,
                session_journal=journal,
                workflow_name=workflow_name,
                verbosity=_verbosity,
            )
        finally:
            # Clean up ACP agent subprocesses (FR-019).
            # Use a timeout to prevent cleanup from hanging when the
            # subprocess is unresponsive (e.g. after Ctrl-C).
            if hasattr(step_executor, "cleanup"):
                try:
                    await asyncio.wait_for(step_executor.cleanup(), timeout=3.0)
                except (TimeoutError, asyncio.CancelledError):
                    logger.warning("step_executor_cleanup_timeout")
                    _force_kill_connections(step_executor)
                except Exception as exc:
                    logger.warning("step_executor_cleanup_failed", error=str(exc))

            if journal is not None:
                try:
                    wf_result = workflow.result
                    if wf_result is not None:
                        journal.write_summary(
                            {
                                "success": wf_result.success,
                                "total_duration_ms": wf_result.total_duration_ms,
                            }
                        )
                    else:
                        journal.write_summary({"success": False})
                except Exception as exc:
                    logger.warning("journal_summary_failed", error=str(exc))
                    journal.write_summary({"success": False})
                journal.close()

        # Display final summary.
        result = workflow.result
        if result is None:
            err_console.print(format_error("Workflow produced no result"))
            raise SystemExit(ExitCode.FAILURE)

        if result.success:
            raise SystemExit(ExitCode.SUCCESS)
        else:
            failed_step = result.failed_step
            if failed_step:
                console.print()
                error_msg = format_error(
                    f"Step '{failed_step.name}' failed",
                    details=[failed_step.error] if failed_step.error else None,
                    suggestion="Check the step configuration and try again.",
                )
                err_console.print(error_msg)
            raise SystemExit(ExitCode.FAILURE)


def _derive_workflow_name(wf_cls: type) -> str:
    """Derive a kebab-case workflow name from a class name.

    Checks the class's constants module for WORKFLOW_NAME first. Falls back
    to converting the class name to lowercase kebab-case.

    Args:
        wf_cls: PythonWorkflow subclass.

    Returns:
        Kebab-case workflow name string.
    """
    # Try to find WORKFLOW_NAME in the class's module package.
    module_name = getattr(wf_cls, "__module__", "") or ""
    # e.g. maverick.workflows.fly_beads.workflow
    #   -> maverick.workflows.fly_beads.constants
    pkg = ".".join(module_name.split(".")[:-1])
    if pkg:
        try:
            constants_mod = importlib.import_module(f"{pkg}.constants")
            name = getattr(constants_mod, "WORKFLOW_NAME", None)
            if name:
                return str(name)
        except ImportError:
            pass

    # Fall back: class name → kebab-case (e.g. FlyBeadsWorkflow → fly-beads-workflow)
    class_name = wf_cls.__name__
    # Insert hyphens before uppercase letters following lowercase letters.
    kebab = re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", class_name).lower()
    # Remove trailing -workflow suffix if present.
    kebab = re.sub(r"-workflow$", "", kebab)
    return kebab


def _force_kill_connections(step_executor: Any) -> None:
    """Force-kill ACP subprocess connections when graceful cleanup times out.

    Sends SIGKILL to any backing subprocess that is still alive. This is a
    last-resort fallback so the CLI can exit promptly after Ctrl-C.
    """
    connections: dict[str, Any] = getattr(step_executor, "_connections", {})
    for name, cached in connections.items():
        proc = getattr(cached, "proc", None)
        if proc is None:
            continue
        try:
            proc.kill()
        except (OSError, ProcessLookupError):
            pass
        else:
            logger.debug("force_killed_subprocess", provider=name)
