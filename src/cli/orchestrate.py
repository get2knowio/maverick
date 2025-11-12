"""CLI entry point for multi-task orchestration workflow.

This module provides a command-line interface for executing the multi-task
orchestration workflow, which processes multiple task files sequentially through
all phases (initialize, implement, review/fix, PR/CI/merge).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from temporalio.client import Client

from src.common.logging import get_logger
from src.models.orchestration import OrchestrationInput, OrchestrationResult


logger = get_logger(__name__)

# Configuration
TEMPORAL_HOST = "localhost:7233"
TASK_QUEUE = "maverick-task-queue"  # Unified task queue for all workflows


def format_orchestration_result(result: OrchestrationResult) -> str:
    """Format the orchestration result for human-readable output.
    
    Args:
        result: The orchestration workflow result to format
        
    Returns:
        Formatted string for terminal display
    """
    lines = ["=" * 60, "Multi-Task Orchestration", "=" * 60, ""]

    # Summary statistics
    lines.append(f"Total Tasks:       {result.total_tasks}")
    lines.append(f"Successful Tasks:  {result.successful_tasks}")
    lines.append(f"Failed Tasks:      {result.failed_tasks}")
    lines.append(f"Skipped Tasks:     {result.skipped_tasks}")
    lines.append(f"Unprocessed Tasks: {result.unprocessed_tasks}")
    lines.append("")

    if result.early_termination:
        lines.append("⚠️  Workflow terminated early due to task failure")
        lines.append("")

    # Task-by-task results
    lines.append("-" * 60)
    lines.append("Task Results:")
    lines.append("")

    for idx, task_result in enumerate(result.task_results, start=1):
        if task_result.overall_status == "success":
            symbol = "✓"
        elif task_result.overall_status == "skipped":
            symbol = "-"
        else:
            symbol = "✗"

        lines.append(f"{symbol} Task {idx}: {task_result.overall_status.upper()}")
        lines.append(f"  File: {task_result.task_file_path}")
        lines.append(f"  Duration: {task_result.total_duration_seconds}s")

        if task_result.phase_results:
            lines.append(f"  Phases: {len(task_result.phase_results)}")
            for phase_result in task_result.phase_results:
                phase_symbol = "✓" if phase_result.status == "success" else "✗"
                retry_info = f" (retries: {phase_result.retry_count})" if phase_result.retry_count > 0 else ""
                lines.append(
                    f"    {phase_symbol} {phase_result.phase_name}: "
                    f"{phase_result.status}{retry_info} ({phase_result.duration_seconds}s)"
                )

        if task_result.failure_reason:
            lines.append(f"  Failure: {task_result.failure_reason}")

        lines.append("")

    # Unprocessed tasks
    if result.unprocessed_task_paths:
        lines.append("-" * 60)
        lines.append("Unprocessed Tasks (not attempted):")
        lines.append("")
        for path in result.unprocessed_task_paths:
            lines.append(f"  - {path}")
        lines.append("")

    # Final status
    lines.append("-" * 60)
    if result.failed_tasks == 0 and result.unprocessed_tasks == 0:
        lines.append("✓ All tasks completed successfully!")
    elif result.early_termination:
        lines.append("✗ Workflow stopped early due to task failure")
    else:
        lines.append("⚠️  Some tasks failed or were skipped")

    lines.append("")
    lines.append(f"Total Duration: {result.total_duration_seconds}s")
    lines.append("=" * 60)

    return "\n".join(lines)


async def run_orchestration(client: Client, args: argparse.Namespace) -> int:
    """Execute the multi-task orchestration workflow.
    
    Args:
        client: Connected Temporal client
        args: Parsed command-line arguments
        
    Returns:
        Exit code (0 for success, 1 for workflow failures, 2 for system errors)
    """
    # Validate required arguments
    if not args.task_files:
        raise ValueError("At least one task file must be specified")

    if not args.repo_path:
        raise ValueError("--repo-path is required")

    if not args.branch:
        raise ValueError("--branch is required")

    # Resolve paths
    repo_path = Path(args.repo_path).resolve()
    task_file_paths = tuple(str(Path(f).resolve()) for f in args.task_files)

    # Validate task files exist
    for task_file in task_file_paths:
        if not Path(task_file).exists():
            raise ValueError(f"Task file does not exist: {task_file}")

    # Build workflow input
    orchestration_input = OrchestrationInput(
        task_file_paths=task_file_paths,
        interactive_mode=args.interactive,
        retry_limit=args.retry_limit,
        repo_path=str(repo_path),
        branch=args.branch,
        default_model=args.default_model,
        default_agent_profile=args.default_agent_profile,
    )

    # Use provided workflow ID for resume, or generate new one
    workflow_id = args.workflow_id if args.workflow_id else f"orchestrate-{uuid.uuid4()}"

    logger.info(
        "Executing multi-task orchestration workflow id=%s tasks=%d repo=%s branch=%s interactive=%s",
        workflow_id,
        len(task_file_paths),
        repo_path,
        args.branch,
        args.interactive,
    )

    # Execute workflow
    try:
        result: OrchestrationResult = await client.execute_workflow(
            "MultiTaskOrchestrationWorkflow",
            orchestration_input,
            id=workflow_id,
            task_queue=TASK_QUEUE,
        )

        print(format_orchestration_result(result))

        # Determine exit code
        if result.failed_tasks > 0 or result.unprocessed_tasks > 0:
            logger.warning("Orchestration completed with failures or unprocessed tasks")
            return 1

        logger.info("Orchestration completed successfully")
        return 0

    except Exception as exc:
        logger.error("Workflow execution failed: %s", exc)
        raise


async def query_orchestration_progress(client: Client, workflow_id: str) -> int:
    """Query progress from a running orchestration workflow.
    
    Args:
        client: Connected Temporal client
        workflow_id: ID of the workflow to query
        
    Returns:
        Exit code (0 for success, 1 for errors)
    """
    logger.info("Querying orchestration progress for workflow %s", workflow_id)

    try:
        handle = client.get_workflow_handle(workflow_id)

        # Query the workflow for current progress
        progress: dict = await handle.query("get_progress")

        # Display progress
        lines = ["=" * 60, f"Orchestration Progress: {workflow_id}", "=" * 60, ""]

        lines.append(f"Current Task:  {progress['current_task_index'] + 1}/{progress['total_tasks']}")
        lines.append(f"Completed:     {len(progress['completed_task_indices'])}")
        lines.append(f"Paused:        {'Yes' if progress['is_paused'] else 'No'}")

        if progress["current_task_file"]:
            lines.append(f"Current File:  {progress['current_task_file']}")

        lines.append("")
        lines.append("=" * 60)

        print("\n".join(lines))

        logger.info("Progress query completed")
        return 0

    except Exception as exc:
        logger.error("Failed to query progress: %s", exc)
        print(f"Error: Failed to query workflow {workflow_id}: {exc}", file=sys.stderr)
        return 1


async def send_continue_signal(client: Client, workflow_id: str) -> int:
    """Send continue signal to a paused orchestration workflow.
    
    Args:
        client: Connected Temporal client
        workflow_id: ID of the workflow to signal
        
    Returns:
        Exit code (0 for success, 1 for errors)
    """
    logger.info("Sending continue signal to workflow %s", workflow_id)

    try:
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("continue_to_next_phase")

        print(f"✓ Continue signal sent to workflow {workflow_id}")
        logger.info("Continue signal sent successfully")
        return 0

    except Exception as exc:
        logger.error("Failed to send signal: %s", exc)
        print(f"Error: Failed to send signal to workflow {workflow_id}: {exc}", file=sys.stderr)
        return 1


async def send_skip_signal(client: Client, workflow_id: str) -> int:
    """Send skip signal to a paused orchestration workflow.
    
    Args:
        client: Connected Temporal client
        workflow_id: ID of the workflow to signal
        
    Returns:
        Exit code (0 for success, 1 for errors)
    """
    logger.info("Sending skip signal to workflow %s", workflow_id)

    try:
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal("skip_current_task")

        print(f"✓ Skip signal sent to workflow {workflow_id}")
        logger.info("Skip signal sent successfully")
        return 0

    except Exception as exc:
        logger.error("Failed to send signal: %s", exc)
        print(f"Error: Failed to send signal to workflow {workflow_id}: {exc}", file=sys.stderr)
        return 1


async def dispatch(args: argparse.Namespace) -> int:
    """Dispatch execution to the requested operation.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Exit code
    """
    try:
        logger.info("Connecting to Temporal server at %s", TEMPORAL_HOST)
        client = await Client.connect(TEMPORAL_HOST)
    except Exception as exc:  # pragma: no cover - network errors surface to user
        logger.error("Failed to connect to Temporal: %s", exc)
        print(f"Error: Failed to connect to Temporal server: {exc}", file=sys.stderr)
        return 2

    try:
        # Route to appropriate operation
        if args.operation == "run":
            return await run_orchestration(client, args)
        elif args.operation == "query":
            if not args.workflow_id:
                raise ValueError("--workflow-id is required for query operation")
            return await query_orchestration_progress(client, args.workflow_id)
        elif args.operation == "continue":
            if not args.workflow_id:
                raise ValueError("--workflow-id is required for continue operation")
            return await send_continue_signal(client, args.workflow_id)
        elif args.operation == "skip":
            if not args.workflow_id:
                raise ValueError("--workflow-id is required for skip operation")
            return await send_skip_signal(client, args.workflow_id)
        else:
            raise ValueError(f"Unknown operation: {args.operation}")

    except Exception as exc:
        logger.error("Operation failed: %s", exc)
        print(f"\nError: {exc}", file=sys.stderr)
        print("\nTroubleshooting:", file=sys.stderr)
        print("  1. Ensure Temporal server is running (temporal server start-dev)", file=sys.stderr)
        print("  2. Ensure the worker is running (uv run maverick-worker)", file=sys.stderr)
        print("  3. Re-run with --help to confirm the required arguments", file=sys.stderr)
        return 2


def main() -> None:
    """Entry point for the CLI command (synchronous wrapper)."""
    parser = argparse.ArgumentParser(
        description="Orchestrate multiple task files through all phases sequentially",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run orchestration for multiple task files
  maverick-orchestrate run task1.md task2.md task3.md \\
    --repo-path /path/to/repo \\
    --branch feature-001

  # Run with interactive mode (pause after each phase)
  maverick-orchestrate run task1.md task2.md \\
    --repo-path /path/to/repo \\
    --branch feature-001 \\
    --interactive

  # Query progress of running workflow
  maverick-orchestrate query --workflow-id orchestrate-abc123

  # Send continue signal to paused workflow
  maverick-orchestrate continue --workflow-id orchestrate-abc123

  # Skip current task in paused workflow
  maverick-orchestrate skip --workflow-id orchestrate-abc123
        """,
    )

    subparsers = parser.add_subparsers(dest="operation", required=True)

    # Run operation
    run_parser = subparsers.add_parser("run", help="Execute multi-task orchestration workflow")
    run_parser.add_argument(
        "task_files",
        nargs="+",
        help="Task markdown files to process (in order)",
    )
    run_parser.add_argument(
        "--repo-path",
        required=True,
        help="Repository root path for task execution",
    )
    run_parser.add_argument(
        "--branch",
        required=True,
        help="Git branch name for all tasks",
    )
    run_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable interactive mode (pause after each phase for approval)",
    )
    run_parser.add_argument(
        "--retry-limit",
        type=int,
        default=3,
        help="Maximum retry attempts for phase execution (1-10, default: 3)",
    )
    run_parser.add_argument(
        "--default-model",
        help="Default AI model for phase execution",
    )
    run_parser.add_argument(
        "--default-agent-profile",
        help="Default agent profile for phase execution",
    )
    run_parser.add_argument(
        "--workflow-id",
        help="Workflow ID (reuse same ID to resume from checkpoint)",
    )

    # Query operation
    query_parser = subparsers.add_parser("query", help="Query progress of running workflow")
    query_parser.add_argument(
        "--workflow-id",
        required=True,
        help="Workflow ID to query",
    )

    # Continue operation
    continue_parser = subparsers.add_parser(
        "continue",
        help="Send continue signal to paused workflow",
    )
    continue_parser.add_argument(
        "--workflow-id",
        required=True,
        help="Workflow ID to signal",
    )

    # Skip operation
    skip_parser = subparsers.add_parser("skip", help="Skip current task in paused workflow")
    skip_parser.add_argument(
        "--workflow-id",
        required=True,
        help="Workflow ID to signal",
    )

    args = parser.parse_args()
    exit_code = asyncio.run(dispatch(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
