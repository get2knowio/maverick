"""Temporal worker for hosting readiness activities and workflows.

This worker registers the readiness workflow and its activities,
listening on the readiness task queue.
"""

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from src.activities.copilot_help import check_copilot_help
from src.activities.gh_status import check_gh_status
from src.common.logging import get_logger
from src.workflows.readiness import ReadinessWorkflow

logger = get_logger(__name__)

# Configuration
TEMPORAL_HOST = "localhost:7233"
TASK_QUEUE = "readiness-task-queue"


async def main():
    """Start the Temporal worker."""
    logger.info(f"Connecting to Temporal server at {TEMPORAL_HOST}")

    # Connect to Temporal server
    client = await Client.connect(TEMPORAL_HOST)

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")

    # Create worker with workflows and activities
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ReadinessWorkflow],
        activities=[check_gh_status, check_copilot_help],
    )

    logger.info("Worker started successfully. Listening for tasks...")

    # Run the worker
    await worker.run()


def run_worker():
    """Entry point for running the worker (synchronous wrapper)."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise


if __name__ == "__main__":
    run_worker()
