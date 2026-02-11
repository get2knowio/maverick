"""Shared workflow execution logic.

Contains ``execute_workflow_run`` — the core execution helper used by
``maverick fly`` and ``maverick refuel speckit`` commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import click

from maverick.cli.common import (
    cli_error_handler,
    create_registered_registry,
    get_discovery_result,
)
from maverick.cli.console import console, err_console
from maverick.cli.context import ExitCode
from maverick.cli.output import format_error
from maverick.dsl.serialization.parser import parse_workflow

if TYPE_CHECKING:
    from maverick.dsl.discovery import DiscoveryResult


def format_workflow_not_found_error(
    discovery_result: DiscoveryResult,
    workflow_name: str,
) -> NoReturn:
    """Format and display a 'workflow not found' error with suggestions.

    Shows the available workflows and exits with a failure code.

    Args:
        discovery_result: The discovery result to pull available names from.
        workflow_name: The workflow name that was not found.

    Raises:
        SystemExit: Always raises with FAILURE exit code.
    """
    available = discovery_result.workflow_names
    if available:
        available_str = ", ".join(available[:5])
        if len(available) > 5:
            available_str += f", ... ({len(available)} total)"
        suggestion = f"Available workflows: {available_str}"
    else:
        suggestion = "No workflows discovered. Check your workflow directories."

    error_msg = format_error(
        f"Workflow '{workflow_name}' not found",
        suggestion=suggestion,
    )
    err_console.print(error_msg)
    raise SystemExit(ExitCode.FAILURE)


async def execute_workflow_run(
    ctx: click.Context,
    name_or_file: str,
    inputs: tuple[str, ...],
    input_file: Path | None,
    dry_run: bool,
    restart: bool,
    no_validate: bool = False,
    list_steps: bool = False,
    only_step: str | None = None,
    session_log_path: Path | None = None,
) -> None:
    """Core workflow execution logic (shared by fly and refuel speckit commands).

    Args:
        ctx: Click context.
        name_or_file: Workflow name or file path.
        inputs: Tuple of KEY=VALUE input strings.
        input_file: Optional path to JSON/YAML input file.
        dry_run: If True, show execution plan without running.
        restart: If True, ignore checkpoint and restart from beginning.
        no_validate: If True, skip semantic validation before execution.
        list_steps: If True, list workflow steps and exit.
        only_step: If provided, run only this step (name or number).
        session_log_path: If provided, write session journal to this file.
    """
    import json

    import yaml

    with cli_error_handler():
        # Determine if name_or_file is a file path or workflow name
        name_path = Path(name_or_file)
        workflow_file = None
        workflow_obj = None

        if name_path.exists():
            # It's a file path - parse directly
            workflow_file = name_path
            content = workflow_file.read_text(encoding="utf-8")
            workflow_obj = parse_workflow(content, validate_only=True)
        else:
            # Look up in discovery (FR-014: use DiscoveryResult for workflow run)
            discovery_result = get_discovery_result(ctx)
            discovered_workflow = discovery_result.get_workflow(name_or_file)

            if discovered_workflow is not None:
                workflow_obj = discovered_workflow.workflow
                workflow_file = discovered_workflow.file_path
            else:
                format_workflow_not_found_error(discovery_result, name_or_file)

        # Parse inputs
        input_dict: dict[str, Any] = {}

        # Load from file first
        if input_file:
            input_content = input_file.read_text(encoding="utf-8")
            if input_file.suffix == ".json":
                input_dict = json.loads(input_content)
            else:
                # Assume YAML
                input_dict = yaml.safe_load(input_content)

        # Parse KEY=VALUE inputs (override file inputs)
        for input_str in inputs:
            if "=" not in input_str:
                error_msg = format_error(
                    f"Invalid input format: {input_str}",
                    suggestion="Use KEY=VALUE format (e.g., -i branch=main)",
                )
                err_console.print(error_msg)
                raise SystemExit(ExitCode.FAILURE)

            key, value = input_str.split("=", 1)

            # Try to parse value as JSON for proper type handling
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                # Keep as string
                parsed_value = value

            input_dict[key] = parsed_value

        # List steps and exit if requested
        if list_steps:
            console.print(f"[bold]Workflow: {workflow_obj.name}[/]")
            console.print(f"Version: {workflow_obj.version}")
            if workflow_obj.description:
                console.print(f"Description: {workflow_obj.description}")
            console.print()
            console.print("[bold]Steps:[/]")
            for i, step in enumerate(workflow_obj.steps, 1):
                console.print(f"  {i}. {step.name} [dim]({step.type.value})[/]")
                if step.when:
                    console.print(f"     [dim]when: {step.when}[/]")
            console.print()
            console.print("Use --step <name|number> to run only a specific step.")
            raise SystemExit(ExitCode.SUCCESS)

        # Resolve only_step to step index if provided
        only_step_index: int | None = None
        if only_step:
            # Try to parse as number first
            try:
                step_num = int(only_step)
                if 1 <= step_num <= len(workflow_obj.steps):
                    only_step_index = step_num - 1  # Convert to 0-based
                else:
                    error_msg = format_error(
                        f"Step number {step_num} out of range",
                        suggestion=f"Valid range: 1-{len(workflow_obj.steps)}",
                    )
                    err_console.print(error_msg)
                    raise SystemExit(ExitCode.FAILURE)
            except ValueError:
                # Try to find step by name
                step_names = [s.name for s in workflow_obj.steps]
                if only_step in step_names:
                    only_step_index = step_names.index(only_step)
                else:
                    # Show available steps
                    error_msg = format_error(
                        f"Step '{only_step}' not found",
                        suggestion="Use --list-steps to see available steps",
                    )
                    err_console.print(error_msg)
                    raise SystemExit(ExitCode.FAILURE) from None

        # Show execution plan for dry run
        if dry_run:
            console.print(
                f"Dry run: Would execute workflow '{workflow_obj.name}'"
            )
            console.print(f"  Version: {workflow_obj.version}")
            console.print(f"  Steps: {len(workflow_obj.steps)}")
            if input_dict:
                console.print("  Inputs:")
                for key, value in input_dict.items():
                    console.print(f"    {key} = [yellow]{value}[/]")
            console.print("\nExecution plan:")
            for i, step in enumerate(workflow_obj.steps, 1):
                console.print(f"  {i}. {step.name} ({step.type.value})")
                if step.when:
                    console.print(f"     when: {step.when}")
            console.print("\nNo actions performed (dry run mode).")
            raise SystemExit(ExitCode.SUCCESS)

        # Execute workflow using WorkflowFileExecutor (CLI mode)
        from maverick.dsl.events import (
            AgentStreamChunk,
            PreflightCheckFailed,
            PreflightCheckPassed,
            PreflightCompleted,
            PreflightStarted,
            StepCompleted,
            StepStarted,
            WorkflowCompleted,
            WorkflowStarted,
        )
        from maverick.dsl.serialization import WorkflowFileExecutor

        # Display workflow header
        wf_name = workflow_obj.name
        console.print(f"[bold cyan]Executing workflow: {wf_name}[/]")
        console.print(f"Version: {workflow_obj.version}")

        # Display input summary
        if input_dict:
            input_summary = ", ".join(
                f"{k}=[yellow]{v}[/]" for k, v in input_dict.items()
            )
            console.print(f"Inputs: {input_summary}")
        else:
            console.print("Inputs: (none)")
        console.print()

        # Create registry with all built-in components registered and executor
        from maverick.dsl.checkpoint.store import FileCheckpointStore

        registry = create_registered_registry()
        checkpoint_store = FileCheckpointStore()

        # Handle checkpoint: check for existing checkpoint and handle restart
        existing_checkpoint = await checkpoint_store.load_latest(workflow_obj.name)

        if restart and existing_checkpoint:
            # Clear checkpoint when restarting
            await checkpoint_store.clear(workflow_obj.name)
            console.print(
                "[yellow]Restarting workflow (cleared existing checkpoint)[/]"
            )
            console.print()
            resume_from_checkpoint = False
        elif existing_checkpoint:
            # Resume from checkpoint (default behavior)
            console.print(
                f"[cyan]Resuming from checkpoint "
                f"'{existing_checkpoint.checkpoint_id}' "
                f"(saved at {existing_checkpoint.saved_at})[/]"
            )
            console.print()
            resume_from_checkpoint = True
        else:
            # No checkpoint exists, start fresh
            resume_from_checkpoint = False

        executor = WorkflowFileExecutor(
            registry=registry,
            checkpoint_store=checkpoint_store,
            validate_semantic=not no_validate,
        )

        # Track step progress with nesting support
        step_index = 0
        total_steps = len(workflow_obj.steps)
        workflow_depth = 0  # Track nesting: 1 = main workflow, 2+ = subworkflows

        # Show limited execution message if --step was used
        if only_step_index is not None:
            only_step_name = workflow_obj.steps[only_step_index].name
            console.print(
                f"[yellow]Will run only step: {only_step_name} "
                f"({only_step_index + 1}/{total_steps})[/]"
            )
            console.print()

        # Execute workflow and display progress
        from maverick.dsl.events import (
            ValidationCompleted,
            ValidationFailed,
            ValidationStarted,
        )

        # Set up session journal if requested
        from maverick.session_journal import SessionJournal

        journal: SessionJournal | None = None
        if session_log_path is not None:
            journal = SessionJournal(session_log_path)
            journal.write_header(workflow_obj.name, input_dict)
            console.print(f"[dim]Session log: {session_log_path}[/]")
            console.print()

        try:
            async for event in executor.execute(
                workflow_obj,
                inputs=input_dict,
                resume_from_checkpoint=resume_from_checkpoint,
                only_step=only_step_index,
            ):
                # Record event to session journal if active
                if journal is not None:
                    await journal.record(event)

                if isinstance(event, ValidationStarted):
                    # Show validation start
                    console.print("[cyan]Validating workflow...[/]", end="")

                elif isinstance(event, ValidationCompleted):
                    # Show validation success
                    console.print(" [bold green]\u2713[/]")
                    if event.warnings_count > 0:
                        console.print(
                            f"  [yellow]({event.warnings_count} warning(s))[/]"
                        )
                    console.print()

                elif isinstance(event, ValidationFailed):
                    # Show validation failure
                    console.print(" [bold red]\u2717[/]")
                    console.print()

                    # Display error details
                    error_msg = format_error(
                        "Workflow validation failed",
                        details=list(event.errors),
                        suggestion="Fix validation errors and try again",
                    )
                    err_console.print(error_msg)
                    raise SystemExit(ExitCode.FAILURE)

                elif isinstance(event, PreflightStarted):
                    if event.prerequisites:
                        console.print("[cyan]Running preflight checks...[/]")

                elif isinstance(event, PreflightCheckPassed):
                    console.print(
                        f"  [green]\u2713[/] [bold]{event.name}[/]"
                    )

                elif isinstance(event, PreflightCheckFailed):
                    console.print(
                        f"  [red]\u2717[/] [bold]{event.name}[/]: {event.message}"
                    )
                    if event.remediation:
                        console.print(
                            f"    [dim]Hint: {event.remediation}[/]"
                        )

                elif isinstance(event, PreflightCompleted):
                    if not event.success:
                        error_msg = format_error(
                            "Preflight checks failed",
                            suggestion="Install missing prerequisites and try again.",
                        )
                        err_console.print(error_msg)
                    console.print()

                elif isinstance(event, WorkflowStarted):
                    # Track workflow nesting depth
                    workflow_depth += 1
                    # Main workflow header already displayed above (depth == 1)
                    # Subworkflow headers are shown as part of their parent step

                elif isinstance(event, StepStarted):
                    # Step type icon mapping
                    type_icons = {
                        "python": "\u2699",
                        "agent": "\U0001f916",
                        "generate": "\u270d",
                        "validate": "\u2713",
                        "checkpoint": "\U0001f4be",
                    }
                    icon = type_icons.get(event.step_type.value, "\u25cf")
                    step_name = event.step_name

                    # Only count and number top-level steps (depth == 1)
                    if workflow_depth == 1:
                        step_index += 1
                        console.print(
                            f"[blue][{step_index}/{total_steps}] "
                            f"{icon} {step_name}[/] "
                            f"({event.step_type.value})... ",
                            end="",
                        )
                    else:
                        # Nested steps: show indented without numbering
                        indent = "  " * (workflow_depth - 1)
                        console.print(
                            f"[dim cyan]{indent}{icon} {step_name}[/] "
                            f"({event.step_type.value})... ",
                            end="",
                        )

                elif isinstance(event, StepCompleted):
                    # Calculate duration
                    duration_sec = event.duration_ms / 1000

                    if event.success:
                        console.print(
                            f"[bold green]\u2713[/] [dim]({duration_sec:.2f}s)[/]"
                        )
                    else:
                        console.print(
                            f"[bold red]\u2717[/] [dim]({duration_sec:.2f}s)[/]"
                        )

                elif isinstance(event, AgentStreamChunk):
                    # Stream agent output to console in real-time
                    if event.chunk_type == "output":
                        # Regular agent output - stream directly
                        console.print(event.text, end="", highlight=False)
                    elif event.chunk_type == "thinking":
                        # Thinking indicator - dim styling
                        console.print(f"[dim]{event.text}[/]")
                    elif event.chunk_type == "error":
                        # Error output - red styling
                        err_console.print(f"[red]{event.text}[/]")

                elif isinstance(event, WorkflowCompleted):
                    # Decrement nesting depth
                    workflow_depth -= 1

                    # Only show summary for main workflow (depth back to 0)
                    if workflow_depth > 0:
                        # Subworkflow completed - show brief inline message
                        total_sec = event.total_duration_ms / 1000
                        console.print(f"[dim]({total_sec:.2f}s)[/]")
                        continue

                    # Main workflow summary
                    console.print()
                    total_sec = event.total_duration_ms / 1000

                    if event.success:
                        console.print(
                            f"[bold green]Workflow completed successfully[/] "
                            f"in {total_sec:.2f}s"
                        )
                    else:
                        console.print(
                            f"[bold red]Workflow failed[/] "
                            f"after {total_sec:.2f}s"
                        )
        finally:
            if journal is not None:
                try:
                    final = executor.get_result()
                    journal.write_summary(
                        {
                            "success": final.success,
                            "total_duration_ms": final.total_duration_ms,
                        }
                    )
                except Exception:
                    journal.write_summary({"success": False})
                journal.close()

        # Get final result
        result = executor.get_result()

        # Display summary
        console.print()
        completed_steps = sum(1 for step in result.step_results if step.success)

        console.print(f"Steps: [green]{completed_steps}[/]/{total_steps} completed")

        if result.success:
            # Display final output (truncated if too long)
            if result.final_output is not None:
                output_str = str(result.final_output)
                if len(output_str) > 200:
                    output_str = output_str[:197] + "..."
                console.print(f"Final output: {output_str}")
            raise SystemExit(ExitCode.SUCCESS)
        else:
            # Find and display the failed step
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
