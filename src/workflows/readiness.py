"""Readiness workflow for orchestrating prerequisite checks and repository verification.

This workflow coordinates the execution of individual prerequisite
checks, repository verification, and aggregates the results into a summary.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


with workflow.unsafe.imports_passed_through():
    from src.models.compose import ComposeCleanupParams, ComposeUpResult
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
            params: Workflow parameters containing github_repo_url and optional compose_config

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
                "has_compose_config": params.compose_config is not None,
                "start_time": start_time.isoformat()
            }
        )

        # Optional: Start Docker Compose environment if config provided
        compose_environment = None
        compose_error = None
        cleanup_instructions = None

        if params.compose_config:
            workflow.logger.info(
                "compose_setup_starting",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                }
            )

            compose_result: ComposeUpResult = await workflow.execute_activity(
                "compose_up_activity",
                params.compose_config,
                start_to_close_timeout=timedelta(seconds=params.compose_config.startup_timeout_seconds + 30),
                retry_policy=RetryPolicy(
                    maximum_attempts=1  # No retries for compose startup
                ),
                result_type=ComposeUpResult,
            )

            if not compose_result.success:
                # Compose startup failed - determine if we should cleanup
                workflow.logger.error(
                    "compose_setup_failed",
                    extra={
                        "workflow_id": workflow.info().workflow_id,
                        "error_type": compose_result.error_type,
                        "error_message": compose_result.error_message,
                    }
                )

                # Build detailed error message
                error_parts = [
                    "Docker Compose environment failed to start",
                    f"Error type: {compose_result.error_type}",
                    f"Details: {compose_result.error_message}",
                ]

                if compose_result.stderr_excerpt:
                    error_parts.append(f"\nDocker output:\n{compose_result.stderr_excerpt[:500]}")

                compose_error = "\n".join(error_parts)

                # Determine cleanup strategy based on error type
                # Validation errors: cleanup (no resources created)
                # Runtime errors: preserve for troubleshooting
                should_preserve = compose_result.error_type not in ["validation_error", "docker_unavailable"]

                if should_preserve and compose_result.environment:
                    # Preserve environment for debugging runtime failures
                    project_name = compose_result.environment.project_name
                    cleanup_instructions = (
                        f"Docker Compose environment preserved for troubleshooting.\n"
                        f"Project name: {project_name}\n"
                        f"To inspect: docker compose -p {project_name} ps\n"
                        f"To view logs: docker compose -p {project_name} logs\n"
                        f"To clean up manually: docker compose -p {project_name} down -v"
                    )

                    workflow.logger.info(
                        "compose_environment_preserved",
                        extra={
                            "workflow_id": workflow.info().workflow_id,
                            "project_name": project_name,
                            "error_type": compose_result.error_type,
                        }
                    )

                # Return failed summary with compose error
                end_time = workflow.now()
                duration_ms = int((end_time - start_time).total_seconds() * 1000)

                return ReadinessSummary(
                    results=[],
                    repo_verification=None,
                    overall_status="not_ready",
                    duration_ms=duration_ms,
                    compose_error=compose_error,
                    cleanup_instructions=cleanup_instructions,
                    target_service=None,  # No target service since compose failed
                )

            compose_environment = compose_result.environment

            workflow.logger.info(
                "compose_setup_completed",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "project_name": compose_environment.project_name if compose_environment else "unknown",
                    "target_service": compose_environment.target_service if compose_environment else "unknown",
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
        # If compose_environment exists, pass it to run checks inside the container;
        # otherwise, call activities with no arguments to keep compatibility with tests/mocks
        if compose_environment is not None:
            gh_check_task = workflow.execute_activity(
                "check_gh_status",
                compose_environment,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=prereq_retry_policy,
                result_type=PrereqCheckResult,
            )

            copilot_check_task = workflow.execute_activity(
                "check_copilot_help",
                compose_environment,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=prereq_retry_policy,
                result_type=PrereqCheckResult,
            )
        else:
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

        # Cleanup Docker Compose environment if it was started
        if compose_environment:
            # Determine overall status before cleanup
            all_passed = (
                gh_result.status == "pass" and
                copilot_result.status == "pass" and
                repo_result.status == "pass"
            )

            # Choose cleanup mode based on success
            cleanup_mode = "graceful" if all_passed else "preserve"

            workflow.logger.info(
                "compose_cleanup_starting",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "project_name": compose_environment.project_name,
                    "mode": cleanup_mode,
                }
            )

            cleanup_params = ComposeCleanupParams(
                project_name=compose_environment.project_name,
                mode=cleanup_mode,
            )

            cleanup_result = await workflow.execute_activity(
                "compose_down_activity",
                cleanup_params,
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=RetryPolicy(
                    maximum_attempts=1  # No retries for cleanup
                ),
                result_type=dict,
            )

            workflow.logger.info(
                "compose_cleanup_completed",
                extra={
                    "workflow_id": workflow.info().workflow_id,
                    "cleaned": cleanup_result.get("cleaned", False),
                    "has_instructions": "instructions" in cleanup_result,
                }
            )

            # Store cleanup instructions if environment was preserved
            if not all_passed and "instructions" in cleanup_result:
                cleanup_instructions = cleanup_result["instructions"]

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
            duration_ms=duration_ms,
            cleanup_instructions=cleanup_instructions,
            target_service=compose_environment.target_service if compose_environment else None,
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
