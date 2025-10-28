"""CLI entrypoint for triggering readiness checks.

This module provides the command-line interface for executing
the readiness workflow and displaying the results.
"""

import asyncio
import sys

from temporalio.client import Client

from src.common.logging import get_logger
from src.models.prereq import ReadinessSummary
from src.workflows.readiness import ReadinessWorkflow

logger = get_logger(__name__)

# Configuration
TEMPORAL_HOST = "localhost:7233"
TASK_QUEUE = "readiness-task-queue"


def format_summary(summary: ReadinessSummary) -> str:
    """Format the readiness summary for human-readable output.

    Args:
        summary: The ReadinessSummary to format

    Returns:
        Formatted string for display
    """
    lines = []
    lines.append("=" * 60)
    lines.append("CLI Readiness Check")
    lines.append("=" * 60)
    lines.append("")

    # Individual check results
    for result in summary.results:
        status_symbol = "✓" if result.status == "pass" else "✗"
        status_text = "PASS" if result.status == "pass" else "FAIL"

        lines.append(f"{status_symbol} {result.tool.upper()}: {status_text}")
        lines.append(f"  {result.message}")

        if result.remediation:
            lines.append("")
            lines.append("  Remediation:")
            for line in result.remediation.split('\n'):
                lines.append(f"    {line}")

        lines.append("")

    # Overall status
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


async def run_check() -> int:
    """Execute the readiness workflow and display results.

    Returns:
        Exit code: 0 if ready, 1 if not ready, 2 on error
    """
    try:
        logger.info(f"Connecting to Temporal server at {TEMPORAL_HOST}")

        # Connect to Temporal server
        client = await Client.connect(TEMPORAL_HOST)

        logger.info("Executing readiness workflow")

        # Execute workflow
        result: ReadinessSummary = await client.execute_workflow(
            ReadinessWorkflow.run,
            id=f"readiness-check-{asyncio.get_event_loop().time()}",
            task_queue=TASK_QUEUE,
        )

        # Display results
        print(format_summary(result))

        # Return appropriate exit code
        if result.overall_status == "ready":
            logger.info("Readiness check passed")
            return 0
        else:
            logger.warning("Readiness check failed")
            return 1

    except Exception as e:
        logger.error(f"Error executing readiness check: {e}")
        print(f"\nError: Failed to execute readiness check: {e}", file=sys.stderr)
        print("\nTroubleshooting:", file=sys.stderr)
        print("  1. Ensure Temporal server is running (temporal server start-dev)", file=sys.stderr)
        print("  2. Ensure the readiness worker is running (uv run readiness:worker)", file=sys.stderr)
        print("  3. Check logs for more details", file=sys.stderr)
        return 2


def main():
    """Entry point for the CLI command (synchronous wrapper)."""
    exit_code = asyncio.run(run_check())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
