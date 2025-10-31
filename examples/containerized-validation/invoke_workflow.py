#!/usr/bin/env python3
"""Example script to invoke the readiness workflow with Docker Compose integration.

This demonstrates how to programmatically start the workflow with containerized
validation using the Temporal Python SDK.

Usage:
    python invoke_workflow.py

Requirements:
    - Temporal dev server running: temporal server start-dev
    - Maverick worker running: uv run maverick-worker
    - Docker Compose V2 available: docker compose version
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from temporalio.client import Client


async def main() -> None:
    """Run the readiness workflow with Docker Compose integration."""

    # Ensure project root is on sys.path to import Maverick modules
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Local import after sys.path adjustment to satisfy import resolution and linting
    from src.common.logging import get_logger
    from src.models.compose import ComposeConfig
    from src.models.parameters import Parameters
    from src.workflows.readiness import ReadinessWorkflow

    logger = get_logger(__name__)

    # Configuration
    compose_file_path = Path(__file__).parent / "docker-compose.yml"
    github_repo_url = "https://github.com/get2knowio/maverick"
    temporal_host = "localhost:7233"
    task_queue = "maverick-task-queue"

    # Load and parse Docker Compose file
    logger.info("Loading compose file: %s", compose_file_path)

    if not compose_file_path.exists():
        logger.error("Compose file not found: %s", compose_file_path)
        sys.exit(1)

    with open(compose_file_path) as f:
        yaml_content = f.read()

    try:
        parsed_config = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        logger.error("Error parsing YAML: %s", e)
        sys.exit(1)

    # Create workflow parameters
    compose_config = ComposeConfig(
        yaml_content=yaml_content,
        parsed_config=parsed_config,
        target_service="app",  # Explicitly specify (or omit to use default selection)
        startup_timeout_seconds=300,  # 5 minutes for environment startup
        validation_timeout_seconds=60,  # 1 minute per validation step
    )

    params = Parameters(
        github_repo_url=github_repo_url,
        compose_config=compose_config,
    )

    logger.info("Workflow parameters:")
    logger.info("  Repository: %s", github_repo_url)
    logger.info("  Target service: %s", compose_config.target_service)
    logger.info("  Startup timeout: %ss", compose_config.startup_timeout_seconds)
    logger.info("  Validation timeout: %ss", compose_config.validation_timeout_seconds)

    # Connect to Temporal
    logger.info("Connecting to Temporal at %s...", temporal_host)

    try:
        client = await Client.connect(temporal_host)
        logger.info("Connected to Temporal")
    except Exception as e:
        logger.error("Failed to connect to Temporal: %s", e)
        logger.info("Make sure Temporal dev server is running: 'temporal server start-dev'")
        sys.exit(1)

    # Generate workflow ID with timestamp (timezone-aware)
    # Use timezone-aware timestamp for workflow ID; keep timezone.utc for compatibility
    workflow_id = f"readiness-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"  # noqa: UP017

    logger.info("Starting workflow: %s", workflow_id)
    logger.info("This may take a few minutes while the container starts and health checks complete...")

    try:
        # Execute workflow and wait for result
        result = await client.execute_workflow(
            ReadinessWorkflow.run,
            params,
            id=workflow_id,
            task_queue=task_queue,
        )

        # Display results
        logger.info("%s", "=" * 70)
        logger.info("WORKFLOW COMPLETED")
        logger.info("%s", "=" * 70)
        logger.info("Overall Status: %s", result.overall_status)

        if result.target_service:
            logger.info("Target Service: %s", result.target_service)

        # Display individual check results
        logger.info("Checks:")
        for check in result.results:
            status_icon = "✓" if check.status == "pass" else "✗"
            logger.info("  %s %s: %s", status_icon, check.tool, check.status)
            if check.message:
                logger.info("     %s", check.message)

        # Display repo verification if present
        if result.repo_verification:
            status_icon = "✓" if result.repo_verification.status == "pass" else "✗"
            logger.info("  %s Repository Access: %s", status_icon, result.repo_verification.status)
            if result.repo_verification.message:
                logger.info("     %s", result.repo_verification.message)

        # Display cleanup information
        logger.info("Environment:")
        if result.target_service:
            logger.info("  Validated in containerized environment (service: %s)", result.target_service)

        if result.cleanup_instructions:
            logger.warning("Cleanup Required:\n  %s", result.cleanup_instructions)
        else:
            logger.info("  Environment cleaned up successfully")

        # Exit with appropriate code
        if result.overall_status == "ready":
            logger.info("All checks passed!")
            sys.exit(0)
        else:
            logger.error("Some checks failed")
            sys.exit(1)

    except Exception as e:
        logger.error("Workflow execution failed: %s", e)
        logger.info("Troubleshooting:")
        logger.info("  1. Check worker is running: uv run maverick-worker")
        logger.info("  2. Check Docker is available: docker compose version")
        logger.info("  3. Check compose file syntax: docker compose -f docker-compose.yml config")
        logger.info(
            "  4. View workflow in Temporal UI: http://localhost:8233/namespaces/default/workflows/%s",
            workflow_id,
        )
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
