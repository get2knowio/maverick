"""Temporal worker entrypoint for all workflows and activities."""

import asyncio
import contextlib
import logging
import os
import signal
import subprocess
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from src.activities.compose import (
    compose_down_activity,
    compose_up_activity,
    validate_in_container_activity,
)
from src.activities.copilot_help import check_copilot_help
from src.activities.gh_status import check_gh_status
from src.activities.param_echo import echo_parameters
from src.activities.repo_verification import verify_repository
from src.utils.logging import get_structured_logger
from src.workflows.readiness import ReadinessWorkflow


# Structured logger for worker
logger = get_structured_logger("worker.main")


async def main() -> None:
    """Start the Temporal worker.

    Connects to Temporal server and registers workflows and activities.
    """
    # Configure basic logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s"  # Structured logger handles formatting
    )

    logger.info(
        "worker_starting",
        workflows=["ReadinessWorkflow"],
        activities=[
            "check_gh_status",
            "check_copilot_help",
            "verify_repository",
            "echo_parameters",
            "compose_up_activity",
            "compose_down_activity",
            "validate_in_container_activity",
        ]
    )

    # Verify Docker Compose V2 availability
    logger.info("docker_compose_check", status="checking")
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5.0
        )
        if result.returncode != 0:
            logger.error(
                "docker_compose_unavailable",
                error="docker compose version check failed",
                stderr=result.stderr.strip(),
                return_code=result.returncode
            )
            sys.exit(1)

        version_output = result.stdout.strip()
        logger.info(
            "docker_compose_available",
            version=version_output
        )
    except FileNotFoundError:
        logger.error(
            "docker_compose_unavailable",
            error="docker command not found",
            hint="Ensure Docker is installed and on PATH"
        )
        sys.exit(1)
    except subprocess.TimeoutExpired:
        logger.error(
            "docker_compose_unavailable",
            error="docker compose version check timed out after 5s"
        )
        sys.exit(1)
    except Exception as e:
        logger.error(
            "docker_compose_unavailable",
            error_type=type(e).__name__,
            error_message=str(e)
        )
        sys.exit(1)

    # Get Temporal server configuration from environment
    temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    connection_timeout = float(os.getenv("TEMPORAL_CONNECTION_TIMEOUT", "10.0"))

    # Validate configuration
    if not temporal_host or not temporal_host.strip():
        logger.error(
            "temporal_config_invalid",
            error="TEMPORAL_HOST cannot be empty",
            provided_value=temporal_host
        )
        sys.exit(1)

    if connection_timeout <= 0:
        logger.error(
            "temporal_config_invalid",
            error="TEMPORAL_CONNECTION_TIMEOUT must be positive",
            provided_value=connection_timeout
        )
        sys.exit(1)

    # Connect to Temporal server with timeout
    logger.info(
        "temporal_connecting",
        target_host=temporal_host,
        timeout_seconds=connection_timeout
    )

    try:
        client = await asyncio.wait_for(
            Client.connect(temporal_host),
            timeout=connection_timeout
        )
        logger.info(
            "temporal_connected",
            target_host=temporal_host,
            status="success"
        )
    except TimeoutError:
        logger.error(
            "temporal_connection_failed",
            error_type="TimeoutError",
            error_message=f"Connection timeout after {connection_timeout}s",
            target_host=temporal_host,
            timeout_seconds=connection_timeout
        )
        sys.exit(1)
    except Exception as e:
        logger.error(
            "temporal_connection_failed",
            error_type=type(e).__name__,
            error_message=str(e),
            target_host=temporal_host,
            timeout_seconds=connection_timeout
        )
        sys.exit(1)

    # Create worker with all workflows and activities
    # Task queue: maverick-task-queue (unified queue for all workflows)
    worker = Worker(
        client,
        task_queue="maverick-task-queue",
        workflows=[ReadinessWorkflow],
        activities=[
            check_gh_status,
            check_copilot_help,
            verify_repository,
            echo_parameters,
            compose_up_activity,
            compose_down_activity,
            validate_in_container_activity,
        ]
    )

    logger.info(
        "worker_created",
        task_queue="maverick-task-queue",
        workflows_count=1,
        activities_count=7
    )

    # Set up graceful shutdown
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def handle_shutdown(sig: int) -> None:
        """Handle shutdown signals."""
        logger.info(
            "shutdown_signal_received",
            signal=signal.Signals(sig).name
        )
        shutdown_event.set()

    # Register signal handlers for graceful shutdown
    loop.add_signal_handler(signal.SIGTERM, lambda: handle_shutdown(signal.SIGTERM))
    loop.add_signal_handler(signal.SIGINT, lambda: handle_shutdown(signal.SIGINT))

    # Run worker until interrupted
    logger.info("worker_running", status="ready")

    try:
        # Run worker until shutdown event is set
        worker_task = asyncio.create_task(worker.run())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        # Wait for either worker completion or shutdown signal
        done, pending = await asyncio.wait(
            [worker_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # If shutdown was triggered, cancel the worker
        if shutdown_task in done:
            logger.info("worker_shutting_down", reason="signal")
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                logger.info("worker_task_cancelled")

        # Cancel any remaining pending tasks
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    except Exception as e:
        logger.error(
            "worker_error",
            phase="execution",
            error_type=type(e).__name__,
            error_message=str(e)
        )
        raise

    finally:
        # Cleanup: remove signal handlers
        loop.remove_signal_handler(signal.SIGTERM)
        loop.remove_signal_handler(signal.SIGINT)

        logger.info(
            "worker_stopped",
            status="cleanup_complete"
        )


def run_worker() -> None:
    """Entry point for running the worker (synchronous wrapper)."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker_interrupted", reason="keyboard_interrupt")
    except Exception as e:
        logger.error(
            "worker_failed",
            error_type=type(e).__name__,
            error_message=str(e)
        )
        raise


if __name__ == "__main__":
    run_worker()
