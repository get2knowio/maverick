"""Readiness workflow for orchestrating prerequisite checks.

This workflow coordinates the execution of individual prerequisite
checks and aggregates the results into a summary.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.common.logging import get_logger
    from src.models.prereq import PrereqCheckResult, ReadinessSummary

logger = get_logger(__name__)


@workflow.defn(name="ReadinessWorkflow")
class ReadinessWorkflow:
    """Workflow to check CLI prerequisites and return readiness summary."""

    @workflow.run
    async def run(self) -> ReadinessSummary:
        """Execute prerequisite checks and return summary.

        Returns:
            ReadinessSummary with all check results and overall status
        """
        workflow.logger.info("Starting readiness workflow")
        start_time = workflow.now()

        # Define retry policy for activities
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=10),
            maximum_attempts=3,
            non_retryable_error_types=["FileNotFoundError"]
        )

        # Execute both prerequisite checks in parallel
        gh_check_task = workflow.execute_activity(
            "check_gh_status",
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
            result_type=PrereqCheckResult,
        )

        copilot_check_task = workflow.execute_activity(
            "check_copilot_help",
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
            result_type=PrereqCheckResult,
        )

        # Wait for both checks to complete
        gh_result: PrereqCheckResult = await gh_check_task
        copilot_result: PrereqCheckResult = await copilot_check_task

        # Calculate duration using workflow time
        end_time = workflow.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Determine overall status
        all_passed = (
            gh_result.status == "pass" and
            copilot_result.status == "pass"
        )
        overall_status = "ready" if all_passed else "not_ready"

        # Build summary
        summary = ReadinessSummary(
            results=[gh_result, copilot_result],
            overall_status=overall_status,
            duration_ms=duration_ms
        )

        workflow.logger.info(
            f"Readiness workflow completed: {overall_status} "
            f"(duration: {duration_ms}ms)"
        )

        return summary
