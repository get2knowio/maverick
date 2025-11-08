"""CLI entrypoint for readiness checks and phase automation workflows."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from temporalio.client import Client
from temporalio.common import RetryPolicy

from src.common.logging import get_logger
from src.models.parameters import Parameters
from src.models.phase_automation import AutomatePhaseTasksParams, PhaseAutomationSummary
from src.models.prereq import ReadinessSummary
from src.workflows.phase_automation import AutomatePhaseTasksWorkflow
from src.workflows.readiness import ReadinessWorkflow


logger = get_logger(__name__)

# Configuration
TEMPORAL_HOST = "localhost:7233"
TASK_QUEUE = "maverick-task-queue"  # Unified task queue for all workflows


def format_readiness_summary(summary: ReadinessSummary) -> str:
    """Format the readiness summary for human-readable output."""

    lines = ["=" * 60, "CLI Readiness Check", "=" * 60, ""]

    for result in summary.results:
        status_symbol = "✓" if result.status == "pass" else "✗"
        status_text = "PASS" if result.status == "pass" else "FAIL"

        lines.append(f"{status_symbol} {result.tool.upper()}: {status_text}")
        lines.append(f"  {result.message}")

        if result.remediation:
            lines.append("")
            lines.append("  Remediation:")
            for line in result.remediation.split("\n"):
                lines.append(f"    {line}")

        lines.append("")

    if summary.repo_verification:
        repo = summary.repo_verification
        status_symbol = "✓" if repo.status == "pass" else "✗"
        status_text = "PASS" if repo.status == "pass" else "FAIL"

        lines.append(f"{status_symbol} REPOSITORY: {status_text}")
        lines.append(f"  {repo.message}")
        lines.append(f"  Repository: {repo.host}/{repo.repo_slug}")

        if repo.status == "fail":
            lines.append(f"  Error: {repo.error_code}")
            lines.append(f"  Attempts: {repo.attempts}")
            lines.append(f"  Duration: {repo.duration_ms}ms")

        lines.append("")

    lines.append("-" * 60)
    if summary.overall_status == "ready":
        lines.append("✓ Overall Status: READY")
        lines.append("")
        lines.append("All prerequisites are satisfied. You're ready to proceed!")
    else:
        lines.append("✗ Overall Status: NOT READY")
        lines.append("")
        lines.append("Some prerequisites are not satisfied. Please review the")
        lines.append("remediation guidance above and try again.")

    lines.append("")
    lines.append(f"Check completed in {summary.duration_ms}ms")
    lines.append("=" * 60)

    return "\n".join(lines)


def format_phase_summary(summary: PhaseAutomationSummary) -> str:
    """Format phase automation results for terminal output."""

    lines = ["=" * 60, "Automate Phase Tasks", "=" * 60, ""]

    for result in summary.results:
        if result.status == "success":
            symbol = "✓"
        elif result.status == "skipped":
            symbol = "-"
        else:
            symbol = "✗"

        lines.append(f"{symbol} {result.phase_id}: {result.status.upper()}")

        if result.summary:
            for line in result.summary[:3]:
                lines.append(f"  {line}")

        if result.error:
            lines.append(f"  Error: {result.error}")

        lines.append("")

    lines.append("-" * 60)
    lines.append(f"Tasks.md hash: {summary.tasks_md_hash}")
    if summary.skipped_phase_ids:
        lines.append(f"Skipped phases: {', '.join(summary.skipped_phase_ids)}")
    lines.append(f"Duration: {summary.duration_ms}ms")
    lines.append("=" * 60)

    return "\n".join(lines)


async def run_readiness(client: Client, github_repo_url: str) -> int:
    """Execute the readiness workflow using an existing Temporal client."""

    logger.info("Executing readiness workflow for %s", github_repo_url)

    params = Parameters(github_repo_url=github_repo_url)

    result: ReadinessSummary = await client.execute_workflow(
        ReadinessWorkflow.run,
        params,
        id=f"readiness-check-{uuid.uuid4()}",
        task_queue=TASK_QUEUE,
    )

    print(format_readiness_summary(result))

    if result.overall_status == "ready":
        logger.info("Readiness check passed")
        return 0

    logger.warning("Readiness check failed")
    return 1


async def run_phase_automation(client: Client, args: argparse.Namespace) -> int:
    """Execute the automate-phase-tasks workflow with validated arguments."""

    if args.tasks_md_path and args.tasks_md_content:
        raise ValueError("Provide only one of --tasks-md-path or --tasks-md-content")

    if not args.tasks_md_path and not args.tasks_md_content:
        raise ValueError("One of --tasks-md-path or --tasks-md-content is required")

    if not args.repo_path:
        raise ValueError("--repo-path is required for automate-phase-tasks")

    if not args.branch:
        raise ValueError("--branch is required for automate-phase-tasks")

    repo_path = Path(args.repo_path).resolve()
    tasks_md_path = Path(args.tasks_md_path).resolve() if args.tasks_md_path else None
    timeout_minutes = max(args.timeout_minutes, 30)

    # Configure retry policy based on CLI arguments
    retry_policy = RetryPolicy(
        maximum_attempts=args.retry_max_attempts,
        initial_interval=timedelta(seconds=args.retry_initial_interval_seconds),
        maximum_interval=timedelta(seconds=args.retry_maximum_interval_seconds),
    )

    params = AutomatePhaseTasksParams(
        repo_path=str(repo_path),
        branch=args.branch,
        tasks_md_path=str(tasks_md_path) if tasks_md_path else None,
        tasks_md_content=args.tasks_md_content,
        default_model=args.default_model,
        default_agent_profile=args.default_agent_profile,
        timeout_minutes=timeout_minutes,
        retry_policy=retry_policy,
    )

    # Use provided workflow ID for resume, or generate new one
    workflow_id = args.workflow_id if args.workflow_id else f"automate-phase-tasks-{uuid.uuid4()}"

    logger.info(
        "Executing automate-phase-tasks workflow id=%s repo=%s branch=%s tasks=%s",
        workflow_id,
        repo_path,
        args.branch,
        tasks_md_path if tasks_md_path else "<inline>",
    )

    summary: PhaseAutomationSummary = await client.execute_workflow(
        AutomatePhaseTasksWorkflow.run,
        params,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    print(format_phase_summary(summary))

    if any(result.status == "failed" for result in summary.results):
        logger.warning("One or more phases failed")
        return 1

    logger.info("Phase automation completed without failures")
    return 0


async def query_phase_results(client: Client, workflow_id: str) -> int:
    """Query phase results from a running or completed workflow."""

    logger.info("Querying phase results for workflow %s", workflow_id)

    try:
        handle = client.get_workflow_handle(workflow_id)

        # Query the workflow for phase results
        from src.models.phase_automation import PhaseResult

        results: list[PhaseResult] = await handle.query("get_phase_results")
        persisted_paths: dict[str, str] = await handle.query("get_persisted_paths")

        if not results:
            print(f"No phase results available for workflow {workflow_id}")
            return 0

        # Display results
        lines = ["=" * 60, f"Phase Results: {workflow_id}", "=" * 60, ""]

        for result in results:
            if result.status == "success":
                symbol = "✓"
            elif result.status == "skipped":
                symbol = "-"
            else:
                symbol = "✗"

            lines.append(f"{symbol} {result.phase_id}: {result.status.upper()}")
            lines.append(f"  Started: {result.started_at.isoformat()}")
            lines.append(f"  Finished: {result.finished_at.isoformat()}")
            lines.append(f"  Duration: {result.duration_ms}ms")
            lines.append(f"  Completed tasks: {len(result.completed_task_ids)}")

            if result.stdout_path:
                lines.append(f"  Stdout: {result.stdout_path}")
            if result.stderr_path:
                lines.append(f"  Stderr: {result.stderr_path}")

            if result.phase_id in persisted_paths:
                lines.append(f"  Result file: {persisted_paths[result.phase_id]}")

            if result.error:
                lines.append(f"  Error: {result.error}")

            if result.summary:
                lines.append("  Summary:")
                for line in result.summary[:5]:  # Show first 5 summary lines
                    lines.append(f"    {line}")

            lines.append("")

        lines.append("=" * 60)

        print("\n".join(lines))

        logger.info("Phase results query completed")
        return 0

    except Exception as exc:
        logger.error("Failed to query phase results: %s", exc)
        print(f"Error: Failed to query workflow {workflow_id}: {exc}", file=sys.stderr)
        return 1


async def dispatch(args: argparse.Namespace) -> int:
    """Dispatch execution to the requested workflow."""

    try:
        logger.info("Connecting to Temporal server at %s", TEMPORAL_HOST)
        client = await Client.connect(TEMPORAL_HOST)
    except Exception as exc:  # pragma: no cover - network errors surface to user
        logger.error("Failed to connect to Temporal: %s", exc)
        print(f"Error: Failed to connect to Temporal server: {exc}", file=sys.stderr)
        return 2

    try:
        if args.workflow == "query-phase-results":
            if not args.workflow_id:
                raise ValueError("--workflow-id is required for query-phase-results")
            return await query_phase_results(client, args.workflow_id)

        if args.workflow == "automate-phase-tasks":
            return await run_phase_automation(client, args)

        if not args.github_repo_url:
            raise ValueError("github_repo_url positional argument is required for readiness workflow")

        return await run_readiness(client, args.github_repo_url)

    except Exception as exc:
        logger.error("Workflow execution failed: %s", exc)
        print(f"\nError: {exc}", file=sys.stderr)
        print("\nTroubleshooting:", file=sys.stderr)
        print("  1. Ensure Temporal server is running (temporal server start-dev)", file=sys.stderr)
        print("  2. Ensure the worker is running (uv run maverick-worker)", file=sys.stderr)
        print("  3. Re-run with --help to confirm the required arguments", file=sys.stderr)
        return 2


def main() -> None:
    """Entry point for the CLI command (synchronous wrapper)."""

    parser = argparse.ArgumentParser(
        description="Run readiness checks or automate tasks.md phases via Temporal workflows",
    )
    parser.add_argument(
        "github_repo_url",
        nargs="?",
        help="GitHub repository URL (used when --workflow readiness)",
    )
    parser.add_argument(
        "--workflow",
        choices=["readiness", "automate-phase-tasks", "query-phase-results"],
        default="readiness",
        help="Workflow to execute (default: readiness)",
    )
    parser.add_argument("--tasks-md-path", help="Absolute path to tasks.md (phase automation)")
    parser.add_argument(
        "--tasks-md-content",
        help="Inline tasks.md content (phase automation)",
    )
    parser.add_argument("--repo-path", help="Repository path for phase automation")
    parser.add_argument("--branch", help="Branch name for phase automation")
    parser.add_argument("--default-model", help="Default AI model override for phase automation")
    parser.add_argument(
        "--default-agent-profile",
        help="Default agent profile override for phase automation",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=45,
        help="Per-phase timeout in minutes (minimum 30)",
    )
    parser.add_argument(
        "--workflow-id",
        help="Workflow ID for resume (reuse same ID to resume from checkpoint)",
    )
    parser.add_argument(
        "--retry-max-attempts",
        type=int,
        default=3,
        help="Maximum retry attempts for failed phases (default: 3)",
    )
    parser.add_argument(
        "--retry-initial-interval-seconds",
        type=int,
        default=1,
        help="Initial retry interval in seconds (default: 1)",
    )
    parser.add_argument(
        "--retry-maximum-interval-seconds",
        type=int,
        default=100,
        help="Maximum retry interval in seconds (default: 100)",
    )

    args = parser.parse_args()
    exit_code = asyncio.run(dispatch(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
