"""Workflow run subcommand and shared execution logic.

Contains the ``workflow run`` CLI command and the ``_execute_workflow_run``
helper function that is shared with the ``maverick fly`` command.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from maverick.cli.common import (
    cli_error_handler,
    create_registered_registry,
    get_discovery_result,
)
from maverick.cli.context import ExitCode, async_command
from maverick.cli.output import format_error
from maverick.dsl.serialization.parser import parse_workflow

from ._group import workflow
from ._helpers import format_workflow_not_found_error


@workflow.command("run")
@click.argument("name_or_file")
@click.option(
    "-i",
    "--input",
    "inputs",
    multiple=True,
    help="Input parameter (KEY=VALUE format).",
)
@click.option(
    "--input-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Load inputs from JSON/YAML file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show execution plan without running.",
)
@click.option(
    "--restart",
    is_flag=True,
    default=False,
    help="Ignore existing checkpoint and restart workflow from the beginning.",
)
@click.option(
    "--no-validate",
    is_flag=True,
    default=False,
    help="Skip semantic validation before execution (not recommended).",
)
@click.option(
    "--session-log",
    type=click.Path(path_type=Path),
    default=None,
    help="Write session journal (JSONL) to this file path.",
)
@click.pass_context
@async_command
async def workflow_run(
    ctx: click.Context,
    name_or_file: str,
    inputs: tuple[str, ...],
    input_file: Path | None,
    dry_run: bool,
    restart: bool,
    no_validate: bool,
    session_log: Path | None,
) -> None:
    """Execute workflow from file or discovered workflow.

    NAME_OR_FILE can be either a workflow name (from discovery) or a file path.
    Uses discovery to find workflows from builtin, user, or project locations.

    Inputs can be provided via -i flags (KEY=VALUE) or --input-file.

    By default, workflows resume from the latest checkpoint if one exists,
    validating that inputs match the saved checkpoint state. Use --restart
    to ignore checkpoints and start fresh.

    By default, workflows are validated before execution. Use --no-validate
    to skip semantic validation (not recommended).

    Examples:
        maverick workflow run fly
        maverick workflow run my-workflow -i branch=main -i dry_run=true
        maverick workflow run my-workflow.yaml --input-file inputs.json
        maverick workflow run my-workflow --dry-run
        maverick workflow run fly --restart  # Ignore checkpoint and start fresh
        maverick workflow run my-workflow --no-validate  # Skip validation
    """
    # Delegate to helper function
    await _execute_workflow_run(
        ctx,
        name_or_file,
        inputs,
        input_file,
        dry_run,
        restart,
        no_validate,
        session_log_path=session_log,
    )


async def _execute_workflow_run(
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
    """Core workflow execution logic (shared by fly and workflow run commands).

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
                click.echo(error_msg, err=True)
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
            click.echo(click.style(f"Workflow: {workflow_obj.name}", bold=True))
            click.echo(f"Version: {workflow_obj.version}")
            if workflow_obj.description:
                click.echo(f"Description: {workflow_obj.description}")
            click.echo()
            click.echo(click.style("Steps:", bold=True))
            for i, step in enumerate(workflow_obj.steps, 1):
                step_type = click.style(f"({step.type.value})", dim=True)
                click.echo(f"  {i}. {step.name} {step_type}")
                if step.when:
                    when_str = click.style(f"when: {step.when}", dim=True)
                    click.echo(f"     {when_str}")
            click.echo()
            click.echo("Use --step <name|number> to run only a specific step.")
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
                    click.echo(error_msg, err=True)
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
                    click.echo(error_msg, err=True)
                    raise SystemExit(ExitCode.FAILURE) from None

        # Show execution plan for dry run
        if dry_run:
            click.echo(f"Dry run: Would execute workflow '{workflow_obj.name}'")
            click.echo(f"  Version: {workflow_obj.version}")
            click.echo(f"  Steps: {len(workflow_obj.steps)}")
            if input_dict:
                click.echo("  Inputs:")
                for key, value in input_dict.items():
                    click.echo(f"    {key} = {value}")
            click.echo("\nExecution plan:")
            for i, step in enumerate(workflow_obj.steps, 1):
                click.echo(f"  {i}. {step.name} ({step.type.value})")
                if step.when:
                    click.echo(f"     when: {step.when}")
            click.echo("\nNo actions performed (dry run mode).")
            raise SystemExit(ExitCode.SUCCESS)

        # Check if TUI mode should be used
        cli_ctx = ctx.obj.get("cli_ctx")
        use_tui = cli_ctx.use_tui if cli_ctx else False

        if use_tui:
            # Execute in TUI mode
            from maverick.tui.workflow_runner import run_workflow_in_tui

            exit_code = await run_workflow_in_tui(
                workflow_file=workflow_file,
                workflow_name=workflow_obj.name,
                inputs=input_dict,
                restart=restart,
                validate=not no_validate,
                only_step=only_step_index,
                session_log_path=session_log_path,
            )
            raise SystemExit(exit_code)

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
        click.echo(click.style(f"Executing workflow: {wf_name}", fg="cyan", bold=True))
        click.echo(f"Version: {click.style(workflow_obj.version, fg='white')}")

        # Display input summary
        if input_dict:
            input_summary = ", ".join(
                f"{k}={click.style(str(v), fg='yellow')}" for k, v in input_dict.items()
            )
            click.echo(f"Inputs: {input_summary}")
        else:
            click.echo("Inputs: (none)")
        click.echo()

        # Create registry with all built-in components registered and executor
        from maverick.dsl.checkpoint.store import FileCheckpointStore

        registry = create_registered_registry()
        checkpoint_store = FileCheckpointStore()

        # Handle checkpoint: check for existing checkpoint and handle restart
        existing_checkpoint = await checkpoint_store.load_latest(workflow_obj.name)

        if restart and existing_checkpoint:
            # Clear checkpoint when restarting
            await checkpoint_store.clear(workflow_obj.name)
            restart_msg = click.style(
                "Restarting workflow (cleared existing checkpoint)",
                fg="yellow",
            )
            click.echo(restart_msg)
            click.echo()
            resume_from_checkpoint = False
        elif existing_checkpoint:
            # Resume from checkpoint (default behavior)
            resume_msg = click.style(
                f"Resuming from checkpoint '{existing_checkpoint.checkpoint_id}' "
                f"(saved at {existing_checkpoint.saved_at})",
                fg="cyan",
            )
            click.echo(resume_msg)
            click.echo()
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
            limit_msg = click.style(
                f"Will run only step: {only_step_name} "
                f"({only_step_index + 1}/{total_steps})",
                fg="yellow",
            )
            click.echo(limit_msg)
            click.echo()

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
            click.echo(click.style(f"Session log: {session_log_path}", dim=True))
            click.echo()

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
                    msg = click.style("Validating workflow...", fg="cyan")
                    click.echo(msg, nl=False)

                elif isinstance(event, ValidationCompleted):
                    # Show validation success
                    check_mark = click.style("\u2713", fg="green", bold=True)
                    click.echo(f" {check_mark}")
                    if event.warnings_count > 0:
                        warning_msg = click.style(
                            f"  ({event.warnings_count} warning(s))",
                            fg="yellow",
                        )
                        click.echo(warning_msg)
                    click.echo()

                elif isinstance(event, ValidationFailed):
                    # Show validation failure
                    x_mark = click.style("\u2717", fg="red", bold=True)
                    click.echo(f" {x_mark}")
                    click.echo()

                    # Display error details
                    error_msg = format_error(
                        "Workflow validation failed",
                        details=list(event.errors),
                        suggestion="Fix validation errors and try again",
                    )
                    click.echo(error_msg, err=True)
                    raise SystemExit(ExitCode.FAILURE)

                elif isinstance(event, PreflightStarted):
                    if event.prerequisites:
                        msg = click.style("Running preflight checks...", fg="cyan")
                        click.echo(msg)

                elif isinstance(event, PreflightCheckPassed):
                    check_mark = click.style("\u2713", fg="green")
                    name = click.style(event.name, bold=True)
                    click.echo(f"  {check_mark} {name}")

                elif isinstance(event, PreflightCheckFailed):
                    x_mark = click.style("\u2717", fg="red")
                    name = click.style(event.name, bold=True)
                    click.echo(f"  {x_mark} {name}: {event.message}")
                    if event.remediation:
                        hint = click.style(f"    Hint: {event.remediation}", dim=True)
                        click.echo(hint)

                elif isinstance(event, PreflightCompleted):
                    if not event.success:
                        error_msg = format_error(
                            "Preflight checks failed",
                            suggestion="Install missing prerequisites and try again.",
                        )
                        click.echo(error_msg, err=True)
                    click.echo()

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
                        step_header = f"[{step_index}/{total_steps}] {icon} {step_name}"
                        styled = click.style(step_header, fg="blue")
                        click.echo(f"{styled} ({event.step_type.value})... ", nl=False)
                    else:
                        # Nested steps: show indented without numbering
                        indent = "  " * (workflow_depth - 1)
                        step_header = f"{indent}{icon} {step_name}"
                        styled = click.style(step_header, fg="cyan", dim=True)
                        click.echo(f"{styled} ({event.step_type.value})... ", nl=False)

                elif isinstance(event, StepCompleted):
                    # Calculate duration
                    duration_sec = event.duration_ms / 1000

                    if event.success:
                        # Success indicator
                        status_msg = click.style("\u2713", fg="green", bold=True)
                        duration_msg = click.style(f"({duration_sec:.2f}s)", dim=True)
                        click.echo(f"{status_msg} {duration_msg}")
                    else:
                        # Failure indicator
                        status_msg = click.style("\u2717", fg="red", bold=True)
                        duration_msg = click.style(f"({duration_sec:.2f}s)", dim=True)
                        click.echo(f"{status_msg} {duration_msg}")

                elif isinstance(event, AgentStreamChunk):
                    # Stream agent output to console in real-time
                    if event.chunk_type == "output":
                        # Regular agent output - stream directly
                        click.echo(event.text, nl=False)
                    elif event.chunk_type == "thinking":
                        # Thinking indicator - dim styling
                        thinking_msg = click.style(event.text, dim=True)
                        click.echo(thinking_msg)
                    elif event.chunk_type == "error":
                        # Error output - red styling
                        error_msg = click.style(event.text, fg="red")
                        click.echo(error_msg, err=True)

                elif isinstance(event, WorkflowCompleted):
                    # Decrement nesting depth
                    workflow_depth -= 1

                    # Only show summary for main workflow (depth back to 0)
                    if workflow_depth > 0:
                        # Subworkflow completed - show brief inline message
                        total_sec = event.total_duration_ms / 1000
                        duration_msg = click.style(f"({total_sec:.2f}s)", dim=True)
                        click.echo(f"{duration_msg}")
                        continue

                    # Main workflow summary
                    click.echo()
                    total_sec = event.total_duration_ms / 1000

                    if event.success:
                        summary_header = click.style(
                            "Workflow completed successfully",
                            fg="green",
                            bold=True,
                        )
                        click.echo(f"{summary_header} in {total_sec:.2f}s")
                    else:
                        summary_header = click.style(
                            "Workflow failed", fg="red", bold=True
                        )
                        click.echo(f"{summary_header} after {total_sec:.2f}s")
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
        click.echo()
        completed_steps = sum(1 for step in result.step_results if step.success)

        styled_completed = click.style(str(completed_steps), fg="green")
        click.echo(f"Steps: {styled_completed}/{total_steps} completed")

        if result.success:
            # Display final output (truncated if too long)
            if result.final_output is not None:
                output_str = str(result.final_output)
                if len(output_str) > 200:
                    output_str = output_str[:197] + "..."
                click.echo(f"Final output: {click.style(output_str, fg='white')}")
            raise SystemExit(ExitCode.SUCCESS)
        else:
            # Find and display the failed step
            failed_step = result.failed_step
            if failed_step:
                click.echo()
                error_msg = format_error(
                    f"Step '{failed_step.name}' failed",
                    details=[failed_step.error] if failed_step.error else None,
                    suggestion="Check the step configuration and try again.",
                )
                click.echo(error_msg, err=True)
            raise SystemExit(ExitCode.FAILURE)
