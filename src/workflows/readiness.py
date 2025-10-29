"""Readiness workflow for orchestrating prerequisite checks and repository verification.

This workflow coordinates the execution of individual prerequisite
checks, repository verification, and aggregates the results into a summary.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


with workflow.unsafe.imports_passed_through():
    from src.models.parameters import Parameters
    from src.models.prereq import PrereqCheckResult, ReadinessSummary
    from src.models.verification_result import VerificationResult


@workflow.defn(name="ReadinessWorkflow")
class ReadinessWorkflow:
    """Unified workflow to check CLI prerequisites, verify repository, and return readiness summary."""

    @workflow.run
    async def run(self, params: Parameters) -> ReadinessSummary:
        """Execute prerequisite checks, repository verification, and return summary.

        Args:
            params: Workflow parameters containing github_repo_url

        Returns:
            ReadinessSummary with all check results, repo verification, and overall status
        """
        start_time = workflow.now()

        workflow.logger.info(
            "workflow_started",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
                "github_repo_url": params.github_repo_url,
                "start_time": start_time.isoformat()
            }
        )

        # Define retry policy for prerequisite check activities
        prereq_retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(seconds=10),
            maximum_attempts=3,
            non_retryable_error_types=["FileNotFoundError"]
        )

        # Execute both prerequisite checks in parallel
        gh_check_task = workflow.execute_activity(
            "check_gh_status",
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=prereq_retry_policy,
            result_type=PrereqCheckResult,
        )

        copilot_check_task = workflow.execute_activity(
            "check_copilot_help",
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=prereq_retry_policy,
            result_type=PrereqCheckResult,
        )

        # Wait for both CLI checks to complete
        gh_result: PrereqCheckResult = await gh_check_task
        copilot_result: PrereqCheckResult = await copilot_check_task

        workflow.logger.info(
            "prereq_checks_completed",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "gh_status": gh_result.status,
                "copilot_status": copilot_result.status
            }
        )

        # Execute repository verification
        repo_result: VerificationResult = await workflow.execute_activity(
            "verify_repository",
            params,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                maximum_attempts=1  # No workflow-level retries; activity handles retries
            ),
            result_type=VerificationResult
        )

        workflow.logger.info(
            "repo_verification_completed",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "repo_status": repo_result.status,
                "repo_slug": repo_result.repo_slug,
                "host": repo_result.host,
                "error_code": repo_result.error_code
            }
        )

        # Execute parameter echo activity (demonstrates parameter access)
        if repo_result.status == "pass":
            echo_result = await workflow.execute_activity(
                "echo_parameters",
                params,
                start_to_close_timeout=timedelta(seconds=5),
                result_type=dict
            )

            workflow.logger.info(
                "parameter_echo_completed",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "echo_result": echo_result
                }
            )

        # Calculate duration using workflow time
        end_time = workflow.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Determine overall status - all checks must pass
        all_passed = (
            gh_result.status == "pass" and
            copilot_result.status == "pass" and
            repo_result.status == "pass"
        )
        overall_status = "ready" if all_passed else "not_ready"

        # Build summary
        summary = ReadinessSummary(
            results=[gh_result, copilot_result],
            repo_verification=repo_result,
            overall_status=overall_status,
            duration_ms=duration_ms
        )

        workflow.logger.info(
            "workflow_completed",
            extra={
                "workflow_id": workflow.info().workflow_id,
                "run_id": workflow.info().run_id,
                "overall_status": overall_status,
                "duration_ms": duration_ms
            }
        )

        return summary
