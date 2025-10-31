"""CLI entrypoint for triggering readiness checks.

This module provides the command-line interface for executing
the readiness workflow and displaying the results.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml
from temporalio.client import Client

from src.common.logging import get_logger
from src.models.compose import ComposeConfig
from src.models.parameters import Parameters
from src.models.prereq import ReadinessSummary
from src.workflows.readiness import ReadinessWorkflow


logger = get_logger(__name__)

# Configuration
TEMPORAL_HOST = "localhost:7233"
TASK_QUEUE = "maverick-task-queue"  # Unified task queue for all workflows


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

    # Display target service if compose was used
    if summary.target_service:
        lines.append(f"Target Service: {summary.target_service}")
        lines.append("")

    # Display compose error if present
    if summary.compose_error:
        lines.append("✗ DOCKER COMPOSE SETUP FAILED")
        lines.append("")
        for line in summary.compose_error.split('\n'):
            lines.append(f"  {line}")
        lines.append("")

        # Display cleanup instructions if environment was preserved
        if summary.cleanup_instructions:
            lines.append("-" * 60)
            lines.append("⚠ ENVIRONMENT PRESERVED FOR TROUBLESHOOTING")
            lines.append("")
            for line in summary.cleanup_instructions.split('\n'):
                lines.append(f"  {line}")
            lines.append("")

        lines.append("-" * 60)
        lines.append("✗ Overall Status: NOT READY")
        lines.append("")
        lines.append("Docker Compose environment setup failed. Fix the errors")
        lines.append("above and try again.")
        lines.append("")
        lines.append(f"Check completed in {summary.duration_ms}ms")
        lines.append("=" * 60)

        return "\n".join(lines)

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

    # Repository verification result
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

    # Display cleanup instructions if environment was preserved
    if summary.cleanup_instructions:
        lines.append("-" * 60)
        lines.append("⚠ ENVIRONMENT PRESERVED FOR TROUBLESHOOTING")
        lines.append("")
        for line in summary.cleanup_instructions.split('\n'):
            lines.append(f"  {line}")
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


async def run_check(github_repo_url: str, compose_file: str | None = None, target_service: str | None = None) -> int:
    """Execute the readiness workflow and display results.

    Args:
        github_repo_url: GitHub repository URL to verify
        compose_file: Optional path to Docker Compose YAML file
        target_service: Optional target service name for multi-service Compose files

    Returns:
        Exit code: 0 if ready, 1 if not ready, 2 on error
    """
    try:
        logger.info(f"Connecting to Temporal server at {TEMPORAL_HOST}")

        # Connect to Temporal server
        client = await Client.connect(TEMPORAL_HOST)

        logger.info(f"Executing readiness workflow for repository: {github_repo_url}")

        # Create compose config if provided
        compose_config = None
        if compose_file:
            logger.info(f"Loading Docker Compose file: {compose_file}")

            try:
                # Read compose file
                compose_path = Path(compose_file)
                if not compose_path.exists():
                    logger.error(f"Compose file not found: {compose_file}")
                    print(f"\nError: Compose file not found: {compose_file}", file=sys.stderr)
                    return 2

                yaml_content = compose_path.read_text(encoding="utf-8")

                # Check size limit (1 MB)
                size_bytes = len(yaml_content.encode("utf-8"))
                if size_bytes > 1_048_576:
                    logger.error(f"Compose file exceeds 1MB limit: {size_bytes} bytes")
                    print(f"\nError: Compose file exceeds 1MB limit: {size_bytes} bytes", file=sys.stderr)
                    print("  Maximum allowed size: 1,048,576 bytes (1 MB)", file=sys.stderr)
                    return 2

                # Parse YAML
                try:
                    parsed_config = yaml.safe_load(yaml_content)
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse YAML: {e}")
                    print("\nError: Invalid YAML syntax in compose file:", file=sys.stderr)
                    print(f"  {str(e)}", file=sys.stderr)
                    return 2

                # Create ComposeConfig
                try:
                    compose_config = ComposeConfig(
                        yaml_content=yaml_content,
                        parsed_config=parsed_config,
                        target_service=target_service,
                    )
                    logger.info("Compose configuration created successfully")
                except ValueError as e:
                    logger.error(f"Invalid compose configuration: {e}")
                    print("\nError: Invalid Docker Compose configuration:", file=sys.stderr)
                    print(f"  {str(e)}", file=sys.stderr)
                    return 2

                # Validate health check presence for target service
                from src.models.compose import resolve_target_service
                try:
                    target_service = resolve_target_service(compose_config)
                    service_config = parsed_config.get('services', {}).get(target_service, {})

                    if 'healthcheck' not in service_config:
                        logger.error(f"Target service '{target_service}' missing required healthcheck")
                        print(f"\nError: Target service '{target_service}' must define a healthcheck", file=sys.stderr)
                        print("  Docker Compose health checks are required for containerized validation.", file=sys.stderr)
                        print("  Example healthcheck:", file=sys.stderr)
                        print("    healthcheck:", file=sys.stderr)
                        print("      test: [\"CMD\", \"curl\", \"-f\", \"http://localhost/health\"]", file=sys.stderr)
                        print("      interval: 5s", file=sys.stderr)
                        print("      timeout: 3s", file=sys.stderr)
                        print("      retries: 3", file=sys.stderr)
                        return 2

                    logger.info(f"Health check validation passed for service '{target_service}'")

                except ValueError as e:
                    logger.error(f"Failed to resolve target service: {e}")
                    print("\nError: Failed to resolve target service:", file=sys.stderr)
                    print(f"  {str(e)}", file=sys.stderr)
                    return 2

            except Exception as e:
                logger.error(f"Failed to load compose file: {e}")
                print(f"\nError: Failed to load compose file: {e}", file=sys.stderr)
                return 2

        # Create parameters
        params = Parameters(
            github_repo_url=github_repo_url,
            compose_config=compose_config
        )

        # Execute workflow
        result: ReadinessSummary = await client.execute_workflow(
            ReadinessWorkflow.run,
            params,
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
        print("  2. Ensure the readiness worker is running (uv run maverick-worker)", file=sys.stderr)
        print("  3. Check logs for more details", file=sys.stderr)
        return 2


def main():
    """Entry point for the CLI command (synchronous wrapper)."""
    parser = argparse.ArgumentParser(
        description="Check CLI readiness and verify GitHub repository access"
    )
    parser.add_argument(
        "github_repo_url",
        help="GitHub repository URL (e.g., https://github.com/owner/repo)"
    )
    parser.add_argument(
        "--compose-file",
        "-c",
        help="Path to Docker Compose YAML file for containerized validation"
    )
    parser.add_argument(
        "--target-service",
        "-t",
        help=(
            "Target service for running validations (default: auto-detect). "
            "Auto-detection: single service → use it; "
            "multiple services → use 'app' if exists; "
            "otherwise → must specify explicitly"
        )
    )

    args = parser.parse_args()

    exit_code = asyncio.run(run_check(args.github_repo_url, args.compose_file, args.target_service))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
