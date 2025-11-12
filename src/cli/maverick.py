"""Maverick CLI - Local Temporal AI Workflow Orchestration.

Main entry point for the maverick command-line interface.
Provides commands for discovering, running, and monitoring multi-task workflows.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import click
from temporalio.client import Client

from src.cli._adapter import adapt_to_orchestration_input, build_cli_descriptor
from src.cli._bootstrap import BootstrapError, RuntimeBootstrap
from src.cli._discovery import discover_tasks
from src.cli._git import get_current_branch, is_working_tree_dirty, validate_repo_root
from src.cli._models import (
    DryRunResult,
    WorkflowStartResponse,
)
from src.common.logging import get_logger


logger = get_logger(__name__)


class NoTasksDiscoveredError(click.ClickException):
    """Raised when maverick run finds no eligible tasks."""

    def __init__(self, message: str = "No tasks discovered", *, json_payload: dict | None = None) -> None:
        super().__init__(message)
        self.json_payload = json_payload


# Import Rich for styled output
from rich.console import Console
from rich.table import Table

# Version from pyproject.toml
__version__ = "0.1.0"

# Constants
TEMPORAL_HOST = "localhost:7233"
TEMPORAL_TASK_QUEUE = "maverick-task-queue"
WORKFLOW_ID_PREFIX = "maverick-run"
STATUS_POLL_INTERVAL = 2.0  # seconds


@click.group()
@click.version_option(version=__version__, prog_name="maverick")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Maverick - Local Temporal AI Workflow Orchestration.

    Discover and execute multi-task workflows from specs/*/tasks.md files.
    Stream progress in real-time and query workflow status.

    Use --help on any command for detailed usage information.
    """
    # Ensure context object exists for subcommands
    ctx.ensure_object(dict)


@cli.command()
@click.option(
    "--task",
    type=click.Path(exists=True, path_type=Path),
    help="Path to specific tasks.md file to run (default: discover all)",
)
@click.option(
    "--interactive",
    is_flag=True,
    help="Enable interactive mode with pauses after each phase",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be executed without starting workflow",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output results in JSON format",
)
@click.option(
    "--allow-dirty",
    is_flag=True,
    help="Allow execution with uncommitted changes in working tree",
)
@click.option(
    "--compact",
    is_flag=True,
    help="Use compact output format for progress streaming",
)
def run(
    task: Path | None,
    interactive: bool,
    dry_run: bool,
    json_output: bool,
    allow_dirty: bool,
    compact: bool,
) -> None:
    """Discover and run multi-task workflows.

    Scans specs/ directory for tasks.md files, builds task descriptors,
    and starts the MultiTaskOrchestrationWorkflow via Temporal.

    Examples:

        # Run all discovered tasks
        maverick run

        # Run specific task file
        maverick run --task specs/001-my-feature/tasks.md

        # Dry run to see what would execute
        maverick run --dry-run --json

        # Interactive mode with JSON output
        maverick run --interactive --json
    """
    try:
        asyncio.run(_run_workflow(task, interactive, dry_run, json_output, allow_dirty, compact))
    except KeyboardInterrupt:
        if not json_output:
            click.echo("\n\nInterrupted. Managed Temporal runtime has been shut down and the workflow was cancelled.")
        sys.exit(130)
    except click.ClickException as e:
        logger.error(f"Run command failed: {e}")
        if json_output:
            payload = getattr(e, "json_payload", None) or {"error": str(e), "error_type": type(e).__name__}
            click.echo(json.dumps(payload))
        else:
            e.show()
        exit_code = getattr(e, "exit_code", 1)
        sys.exit(exit_code if isinstance(exit_code, int) else 1)
    except Exception as e:
        logger.error(f"Run command failed: {e}")
        if json_output:
            error_payload = {"error": str(e), "error_type": type(e).__name__}
            click.echo(json.dumps(error_payload))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


async def _run_workflow(
    task: Path | None,
    interactive: bool,
    dry_run: bool,
    json_output: bool,
    allow_dirty: bool,
    compact: bool,
) -> None:
    """Internal async implementation of run command."""
    errors_count = 0

    # Initialize Rich console if outputting to TTY (not when --json is used)
    console = None
    if not json_output and sys.stdout.isatty():
        console = Console()

    # Get repository root (current working directory assumed to be repo root)
    repo_root = Path.cwd()

    # Validate repository
    try:
        validate_repo_root(repo_root)
    except ValueError as e:
        logger.error(f"Invalid repository: {e}")
        remediation = (
            "\n\nRemediation:\n"
            "  1. Ensure you're running from inside a git repository\n"
            "  2. Run 'git init' if this is a new project\n"
            f"  3. Current directory: {repo_root}"
        )
        raise click.ClickException(f"Not a git repository: {repo_root}{remediation}") from e

    # Check for dirty working tree (unless allowed)
    if not allow_dirty:
        try:
            if is_working_tree_dirty(repo_root):
                msg = (
                    "Working tree has uncommitted changes. "
                    "Commit changes or use --allow-dirty to proceed."
                )
                logger.error(msg)
                raise click.ClickException(msg)
        except Exception as e:
            logger.error(f"Failed to check working tree status: {e}")
            errors_count += 1
            raise click.ClickException(f"Git status check failed: {e}") from e

    # Get current branch
    try:
        return_to_branch = get_current_branch(repo_root)
        logger.info(f"Current branch: {return_to_branch}")
    except Exception as e:
        logger.error(f"Failed to get current branch: {e}")
        errors_count += 1
        raise click.ClickException(f"Failed to get current branch: {e}") from e

    # Discover tasks
    discovery_start = time.time()
    try:
        # Normalize and validate task path if provided
        task_file = None
        if task:
            task_file = task.resolve()
            # Validate that task file is under repo root
            try:
                task_file.relative_to(repo_root)
            except ValueError as e:
                msg = (
                    f"Task file must be under repository root:\n"
                    f"  Task: {task_file}\n"
                    f"  Repo: {repo_root}\n\n"
                    "Remediation:\n"
                    "  1. Ensure task file path is correct\n"
                    "  2. Run command from repository root\n"
                    "  3. Use relative path to tasks.md file"
                )
                logger.error(msg)
                raise click.ClickException(msg) from e

        discovered_tasks = discover_tasks(repo_root, task_file)
        discovery_ms = int((time.time() - discovery_start) * 1000)

        if not discovered_tasks:
            msg = "No tasks discovered"
            logger.warning(msg)

            if dry_run:
                if json_output:
                    click.echo(json.dumps({"task_count": 0, "tasks": []}))
                else:
                    click.echo(msg)
                return

            json_payload = {
                "error": msg,
                "error_type": "NoTasksDiscoveredError",
                "task_count": 0,
                "tasks": [],
            }
            raise NoTasksDiscoveredError(msg, json_payload=json_payload)

        logger.info(f"Discovered {len(discovered_tasks)} task(s) in {discovery_ms}ms")

    except NoTasksDiscoveredError:
        raise
    except Exception as e:
        logger.error(f"Task discovery failed: {e}")
        errors_count += 1
        raise click.ClickException(f"Task discovery failed: {e}") from e

    # Build CLI descriptors
    try:
        cli_descriptors = []
        for discovered in discovered_tasks:
            descriptor = build_cli_descriptor(
                task_file=Path(discovered.file_path),
                spec_root=Path(discovered.spec_dir),
                repo_root=repo_root,
                return_to_branch=return_to_branch,
                interactive=interactive,
            )
            cli_descriptors.append(descriptor)

        logger.info(f"Built {len(cli_descriptors)} CLI descriptor(s)")

    except Exception as e:
        logger.error(f"Failed to build descriptors: {e}")
        errors_count += 1
        raise click.ClickException(f"Failed to build descriptors: {e}") from e

    # Handle dry-run mode
    if dry_run:
        dry_run_result = DryRunResult(
            task_count=len(cli_descriptors),
            discovery_ms=discovery_ms,
            descriptors=cli_descriptors,
        )

        if json_output:
            # Convert to dict for JSON serialization
            output = {
                "task_count": dry_run_result.task_count,
                "discovery_ms": dry_run_result.discovery_ms,
                "tasks": [
                    {
                        "task_id": d.task_id,
                        "task_file": d.task_file,
                        "spec_root": d.spec_root,
                        "branch_name": d.branch_name,
                        "interactive": d.interactive,
                    }
                    for d in dry_run_result.descriptors
                ],
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo(f"Dry run - would execute {dry_run_result.task_count} task(s):")
            click.echo(f"  Discovery time: {dry_run_result.discovery_ms}ms")
            for desc in dry_run_result.descriptors:
                click.echo(f"\n  Task: {desc.task_id}")
                click.echo(f"    File: {desc.task_file}")
                click.echo(f"    Branch: {desc.branch_name or '(derived)'}")
                click.echo(f"    Interactive: {desc.interactive}")

        return

    # Build orchestration input
    try:
        orchestration_input = adapt_to_orchestration_input(
            cli_descriptors=cli_descriptors,
            repo_root=str(repo_root),
            return_to_branch=return_to_branch,
            interactive_mode=interactive,
        )
        logger.info("Built OrchestrationInput for workflow")

    except Exception as e:
        logger.error(f"Failed to build orchestration input: {e}")
        errors_count += 1
        raise click.ClickException(f"Failed to build orchestration input: {e}") from e

    bootstrap: RuntimeBootstrap | None = None
    try:
        bootstrap = RuntimeBootstrap(
            temporal_host=TEMPORAL_HOST,
            logger=logger,
            start_worker=True,
        )
        await bootstrap.start()
    except BootstrapError as e:
        logger.error(f"Runtime bootstrap failed: {e}")
        raise click.ClickException(str(e)) from e

    workflow_start_begin = time.time()
    try:
        try:
            client = await Client.connect(TEMPORAL_HOST)
            logger.info(f"Connected to Temporal at {TEMPORAL_HOST}")
        except Exception as e:
            logger.error(f"Failed to connect to Temporal: {e}")
            errors_count += 1
            remediation = (
                "\n\nRemediation:\n"
                "  1. Ensure the Temporal CLI ('temporal') is installed and accessible\n"
                f"  2. Verify the server is reachable at {TEMPORAL_HOST}\n"
                "  3. For remote clusters, set TEMPORAL_HOST and disable auto-bootstrap via MAVERICK_SKIP_TEMPORAL_BOOTSTRAP=1\n"
                "  4. Check firewall/network settings or run 'temporal server start-dev' manually for debugging"
            )
            raise click.ClickException(
                f"Failed to connect to Temporal at {TEMPORAL_HOST}. "
                f"Is the Temporal server running?{remediation}\n\nError: {e}"
            ) from e

        try:
            from src.workflows.multi_task_orchestration import MultiTaskOrchestrationWorkflow

            workflow_id = f"{WORKFLOW_ID_PREFIX}-{int(time.time())}"

            handle = await client.start_workflow(
                MultiTaskOrchestrationWorkflow.run,
                orchestration_input,
                id=workflow_id,
                task_queue=TEMPORAL_TASK_QUEUE,
            )

            workflow_start_ms = int((time.time() - workflow_start_begin) * 1000)

            run_id = handle.result_run_id or handle.id

            logger.info(
                f"Started workflow: id={handle.id}, run_id={run_id}, "
                f"start_time={workflow_start_ms}ms, task_count={len(cli_descriptors)}, "
                f"discovery_ms={discovery_ms}"
            )

            # Create start response
            start_response = WorkflowStartResponse(
                workflow_id=handle.id,
                run_id=run_id,
                task_count=len(cli_descriptors),
                discovery_ms=discovery_ms,
                workflow_start_ms=workflow_start_ms,
            )

            # Output start info
            if json_output:
                output = {
                    "workflow_id": start_response.workflow_id,
                    "run_id": start_response.run_id,
                    "task_count": start_response.task_count,
                    "discovery_ms": start_response.discovery_ms,
                    "workflow_start_ms": start_response.workflow_start_ms,
                }
                click.echo(json.dumps(output))
            elif console:
                # Rich output
                table = Table(title="Workflow Started", show_header=False)
                table.add_row("Workflow ID", start_response.workflow_id)
                table.add_row("Run ID", start_response.run_id)
                table.add_row("Tasks", str(start_response.task_count))
                table.add_row("Discovery (discovery_ms)", f"{start_response.discovery_ms}ms")
                table.add_row("Start time", f"{start_response.workflow_start_ms}ms")
                console.print(table)
            else:
                click.echo("\nWorkflow started:")
                click.echo(f"  Workflow ID: {start_response.workflow_id}")
                click.echo(f"  Run ID: {start_response.run_id}")
                click.echo(f"  Tasks: {start_response.task_count}")
                click.echo(f"  Discovery (discovery_ms): {start_response.discovery_ms}ms")
                click.echo(f"  Start time: {start_response.workflow_start_ms}ms")
                click.echo()

        except Exception as e:
            logger.error(f"Failed to start workflow: {e}")
            errors_count += 1
            raise click.ClickException(f"Failed to start workflow: {e}") from e

        try:
            await _stream_progress(handle, json_output, compact, errors_count, console)
        except KeyboardInterrupt:
            raise
    finally:
        if bootstrap:
            await bootstrap.stop()


async def _stream_progress(
    handle,
    json_output: bool,
    compact: bool,
    errors_count: int,
    console=None,
) -> None:
    """Stream workflow progress updates.

    Polls workflow for progress at fixed intervals and displays updates.
    Ctrl+C is propagated to the caller so the managed runtime can shut down cleanly.
    
    Args:
        handle: Temporal workflow handle
        json_output: Whether to output JSON
        compact: Whether to use compact output
        errors_count: Current error count
        console: Optional Rich Console for styled output
    """
    poll_latencies: list[int] = []

    try:
        while True:
            poll_start = time.time()

            try:
                # Query workflow for progress
                progress = await handle.query("get_progress")
                task_results = await handle.query("get_task_results")

                poll_latency_ms = int((time.time() - poll_start) * 1000)
                poll_latencies.append(poll_latency_ms)

                # Check if workflow is complete
                workflow_info = await handle.describe()
                is_running = workflow_info.status.name == "RUNNING"

                if json_output:
                    # Output JSON status update
                    status_output = {
                        "workflow_id": handle.id,
                        "status": "running" if is_running else "completed",
                        "progress": progress if progress else {},
                        "task_results": task_results if task_results else [],
                        "poll_latency_ms": poll_latency_ms,
                    }
                    click.echo(json.dumps(status_output))
                else:
                    # Human-readable output
                    if compact:
                        # Compact: single line updates
                        if progress:
                            current = progress.get("current_task", "N/A")
                            phase = progress.get("current_phase", "N/A")
                            click.echo(f"\r[{current}] Phase: {phase}", nl=False)
                    else:
                        # Full output with details
                        if progress:
                            click.echo(f"Progress: {progress}")
                        if task_results:
                            click.echo(f"Results: {len(task_results)} task(s) completed")

                if not is_running:
                    # Workflow completed
                    if not json_output:
                        click.echo("\n\nWorkflow completed!")

                    # Calculate final metrics
                    if poll_latencies:
                        sorted_latencies = sorted(poll_latencies)
                        p95_index = int(len(sorted_latencies) * 0.95)
                        status_poll_latency_ms_p95 = sorted_latencies[p95_index]
                    else:
                        status_poll_latency_ms_p95 = 0

                    if json_output:
                        final_output = {
                            "workflow_id": handle.id,
                            "status": "completed",
                            "status_poll_latency_ms_p95": status_poll_latency_ms_p95,
                            "errors_count": errors_count,
                        }
                        click.echo(json.dumps(final_output))
                    else:
                        click.echo(f"Poll latency (p95): {status_poll_latency_ms_p95}ms")
                        if errors_count > 0:
                            click.echo(f"Errors: {errors_count}")

                    break

            except Exception as e:
                logger.error(f"Failed to query workflow progress: {e}")
                if json_output:
                    error_output = {"error": str(e), "error_type": type(e).__name__}
                    click.echo(json.dumps(error_output))
                else:
                    click.echo(f"\nError querying progress: {e}")
                # Continue polling despite errors

            # Wait before next poll
            await asyncio.sleep(STATUS_POLL_INTERVAL)

    except KeyboardInterrupt:
        # Propagate so the caller can tear down bootstrap resources.
        raise


async def _get_workflow_status(workflow_id: str, json_output: bool) -> None:
    """Internal async implementation of status command.

    Args:
        workflow_id: Temporal workflow ID to query
        json_output: Whether to output in JSON format

    Raises:
        click.ClickException: On validation or query errors
    """
    from datetime import UTC, datetime

    from temporalio.client import WorkflowFailureError
    from temporalio.service import RPCError

    from src.cli._models import TaskProgressInfo, WorkflowStatusInfo

    # Connect to Temporal
    try:
        client = await Client.connect(TEMPORAL_HOST)
        logger.info(f"Connected to Temporal at {TEMPORAL_HOST}")
    except Exception as e:
        logger.error(f"Failed to connect to Temporal: {e}")
        remediation = (
            "\n\nRemediation:\n"
            "  1. Ensure the `maverick` session managing Temporal is still running (or rerun the workflow)\n"
            f"  2. Verify the server is reachable at {TEMPORAL_HOST}\n"
            "  3. Check firewall/network settings if using a remote cluster\n"
            "  4. Install the Temporal CLI or start `temporal server start-dev` manually for debugging"
        )
        raise click.ClickException(
            f"Failed to connect to Temporal at {TEMPORAL_HOST}. "
            f"Is the Temporal server running?{remediation}\n\nError: {e}"
        ) from e

    # Get workflow handle
    try:
        handle = client.get_workflow_handle(workflow_id)
        logger.info(f"Got workflow handle for: {workflow_id}")
    except Exception as e:
        logger.error(f"Failed to get workflow handle: {e}")
        raise click.ClickException(
            f"Failed to get workflow handle for {workflow_id}: {e}"
        ) from e

    # Query workflow status
    try:
        # Get workflow info to check status
        workflow_info = await handle.describe()
        run_id = workflow_info.run_id

        # Determine state based on workflow status
        workflow_status = workflow_info.status
        if workflow_status is None:
            state = "unknown"
        else:
            workflow_status_name = workflow_status.name
            if workflow_status_name == "RUNNING":
                state = "running"
            elif workflow_status_name in ("COMPLETED", "FAILED", "TERMINATED", "TIMED_OUT"):
                state = "completed" if workflow_status_name == "COMPLETED" else "failed"
            else:
                state = "paused"  # For cancelled or other states

        # Query for progress and task results
        current_task_id = None
        current_phase = None
        last_activity = None
        task_progress_list: list[TaskProgressInfo] = []

        try:
            progress = await handle.query("get_progress")
            if progress:
                current_task_id = progress.get("current_task")
                current_phase = progress.get("current_phase")
                last_activity = progress.get("last_activity")
        except Exception as e:
            logger.warning(f"Failed to query progress: {e}")

        try:
            task_results = await handle.query("get_task_results")
            if task_results:
                # Convert task results to TaskProgressInfo
                for result in task_results:
                    if isinstance(result, dict):
                        task_id = result.get("task_id", "unknown")
                        status_str = result.get("status", "unknown")
                        message = result.get("message")

                        # Map status to valid values
                        if status_str in ("pending", "running", "success", "failed", "skipped"):
                            task_progress_list.append(
                                TaskProgressInfo(
                                    task_id=task_id,
                                    status=status_str,
                                    last_message=message,
                                )
                            )
        except Exception as e:
            logger.warning(f"Failed to query task results: {e}")

        # Create status info
        updated_at = datetime.now(UTC).isoformat()

        status_info = WorkflowStatusInfo(
            workflow_id=workflow_id,
            run_id=run_id,
            state=state,
            current_task_id=current_task_id,
            current_phase=current_phase,
            last_activity=last_activity,
            updated_at=updated_at,
            tasks=task_progress_list,
        )

        # Output status
        if json_output:
            output = {
                "workflow_id": status_info.workflow_id,
                "run_id": status_info.run_id,
                "state": status_info.state,
                "current_task_id": status_info.current_task_id,
                "current_phase": status_info.current_phase,
                "last_activity": status_info.last_activity,
                "updated_at": status_info.updated_at,
                "tasks": [
                    {
                        "task_id": task.task_id,
                        "status": task.status,
                        "last_message": task.last_message,
                    }
                    for task in status_info.tasks
                ],
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo("\nWorkflow Status:")
            click.echo(f"  Workflow ID: {status_info.workflow_id}")
            click.echo(f"  Run ID: {status_info.run_id}")
            click.echo(f"  State: {status_info.state}")

            if status_info.current_task_id:
                click.echo(f"  Current Task: {status_info.current_task_id}")
            if status_info.current_phase:
                click.echo(f"  Current Phase: {status_info.current_phase}")
            if status_info.last_activity:
                click.echo(f"  Last Activity: {status_info.last_activity}")

            click.echo(f"  Updated: {status_info.updated_at}")

            if status_info.tasks:
                click.echo(f"\n  Tasks ({len(status_info.tasks)}):")
                for task in status_info.tasks:
                    status_icon = "✓" if task.status == "success" else "✗" if task.status == "failed" else "●"
                    click.echo(f"    {status_icon} {task.task_id}: {task.status}")
                    if task.last_message:
                        click.echo(f"      {task.last_message}")

    except WorkflowFailureError as e:
        logger.error(f"Workflow not found or failed: {e}")
        remediation = (
            "\n\nRemediation:\n"
            "  1. Verify workflow ID is correct\n"
            "  2. Check workflow was started successfully\n"
            "  3. Use 'maverick run' to start a new workflow\n"
            f"  4. Workflow ID format: {WORKFLOW_ID_PREFIX}-<timestamp>"
        )
        raise click.ClickException(
            f"Workflow {workflow_id} not found or has failed.{remediation}\n\nError: {e}"
        ) from e
    except RPCError as e:
        logger.error(f"RPC error querying workflow: {e}")
        remediation = (
            "\n\nRemediation:\n"
            "  1. Ensure Temporal server is running\n"
            f"  2. Verify connection to {TEMPORAL_HOST}\n"
            "  3. Check network/firewall settings\n"
            "  4. Review Temporal server logs"
        )
        raise click.ClickException(
            f"Failed to query workflow {workflow_id}.{remediation}\n\nError: {e}"
        ) from e
    except Exception as e:
        logger.error(f"Failed to query workflow status: {e}")
        raise click.ClickException(f"Failed to query workflow status: {e}") from e


@cli.command()
@click.argument("workflow-id")
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output results in JSON format",
)
def status(workflow_id: str, json_output: bool) -> None:
    """Check status of a running workflow.

    Query workflow progress by ID and display current state.

    WORKFLOW_ID: The Temporal workflow ID to query

    Examples:

        # Check workflow status
        maverick status maverick-run-1234567890

        # Get status in JSON format
        maverick status maverick-run-1234567890 --json
    """
    try:
        asyncio.run(_get_workflow_status(workflow_id, json_output))
    except Exception as e:
        logger.error(f"Status command failed: {e}")
        if json_output:
            error_payload = {
                "error": str(e),
                "error_type": type(e).__name__,
                "workflow_id": workflow_id,
            }
            click.echo(json.dumps(error_payload))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
