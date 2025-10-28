"""Integration tests for readiness workflow orchestration."""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.models.prereq import PrereqCheckResult, ReadinessSummary


@pytest.mark.asyncio
async def test_readiness_workflow_all_pass():
    """Test readiness workflow when all prerequisites pass."""
    from temporalio import activity

    from src.workflows.readiness import ReadinessWorkflow

    # Create mock activities
    @activity.defn(name="check_gh_status")
    async def mock_gh_status() -> PrereqCheckResult:
        return PrereqCheckResult(
            tool="gh",
            status="pass",
            message="GitHub CLI is authenticated",
            remediation=""
        )

    @activity.defn(name="check_copilot_help")
    async def mock_copilot_help() -> PrereqCheckResult:
        return PrereqCheckResult(
            tool="copilot",
            status="pass",
            message="Copilot CLI is available",
            remediation=""
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="readiness-task-queue",
            workflows=[ReadinessWorkflow],
            activities=[mock_gh_status, mock_copilot_help],
        ):
            result = await env.client.execute_workflow(
                ReadinessWorkflow.run,
                id="test-workflow-all-pass",
                task_queue="readiness-task-queue",
            )

            assert isinstance(result, ReadinessSummary)
            assert result.overall_status == "ready"
            assert len(result.results) == 2
            assert all(r.status == "pass" for r in result.results)
            assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_readiness_workflow_gh_fails():
    """Test readiness workflow when gh check fails."""
    from temporalio import activity

    from src.workflows.readiness import ReadinessWorkflow

    # Create mock activities that return our test data
    @activity.defn(name="check_gh_status")
    async def mock_gh_status() -> PrereqCheckResult:
        return PrereqCheckResult(
            tool="gh",
            status="fail",
            message="GitHub CLI is not authenticated",
            remediation="""GitHub CLI is not authenticated.

Authenticate with GitHub:
  gh auth login

Follow the prompts to authenticate via your browser or personal access token.

Official documentation: https://cli.github.com/manual/gh_auth_login"""
        )

    @activity.defn(name="check_copilot_help")
    async def mock_copilot_help() -> PrereqCheckResult:
        return PrereqCheckResult(
            tool="copilot",
            status="pass",
            message="Copilot CLI is available",
            remediation=""
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="readiness-task-queue",
            workflows=[ReadinessWorkflow],
            activities=[mock_gh_status, mock_copilot_help],
        ):
            result = await env.client.execute_workflow(
                ReadinessWorkflow.run,
                id="test-workflow-gh-fails",
                task_queue="readiness-task-queue",
            )

            assert isinstance(result, ReadinessSummary)
            assert result.overall_status == "not_ready"
            assert len(result.results) == 2
            gh_check = next(r for r in result.results if r.tool == "gh")
            assert gh_check.status == "fail"
            assert gh_check.remediation is not None
            assert len(gh_check.remediation) > 0

            # Verify guidance content is actionable
            remediation_lower = gh_check.remediation.lower()
            assert "gh auth login" in remediation_lower, \
                "Remediation should include authentication command"
            assert any(term in remediation_lower for term in ["cli.github.com", "github.com/cli"]), \
                "Remediation should include documentation link"
@pytest.mark.asyncio
async def test_readiness_workflow_copilot_fails():
    """Test readiness workflow when copilot check fails."""
    from temporalio import activity

    from src.workflows.readiness import ReadinessWorkflow

    # Create mock activities
    @activity.defn(name="check_gh_status")
    async def mock_gh_status() -> PrereqCheckResult:
        return PrereqCheckResult(
            tool="gh",
            status="pass",
            message="GitHub CLI is authenticated",
            remediation=""
        )

    @activity.defn(name="check_copilot_help")
    async def mock_copilot_help() -> PrereqCheckResult:
        return PrereqCheckResult(
            tool="copilot",
            status="fail",
            message="Copilot CLI is not installed",
            remediation="Install Copilot CLI from https://github.com/github/gh-copilot"
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="readiness-task-queue",
            workflows=[ReadinessWorkflow],
            activities=[mock_gh_status, mock_copilot_help],
        ):
            result = await env.client.execute_workflow(
                ReadinessWorkflow.run,
                id="test-workflow-copilot-fails",
                task_queue="readiness-task-queue",
            )

            assert isinstance(result, ReadinessSummary)
            assert result.overall_status == "not_ready"
            assert len(result.results) == 2
            copilot_check = next(r for r in result.results if r.tool == "copilot")
            assert copilot_check.status == "fail"
            assert copilot_check.remediation is not None

            # Verify guidance content is actionable
            remediation_lower = copilot_check.remediation.lower()
            assert "install" in remediation_lower, \
                "Remediation should include installation instructions"
            assert "github.com" in remediation_lower or "copilot" in remediation_lower, \
                "Remediation should include documentation or tool reference"


@pytest.mark.asyncio
async def test_readiness_workflow_both_fail():
    """Test readiness workflow when both checks fail."""
    from temporalio import activity

    from src.workflows.readiness import ReadinessWorkflow

    # Create mock activities
    @activity.defn(name="check_gh_status")
    async def mock_gh_status() -> PrereqCheckResult:
        return PrereqCheckResult(
            tool="gh",
            status="fail",
            message="GitHub CLI is not installed",
            remediation="Install GitHub CLI from https://cli.github.com"
        )

    @activity.defn(name="check_copilot_help")
    async def mock_copilot_help() -> PrereqCheckResult:
        return PrereqCheckResult(
            tool="copilot",
            status="fail",
            message="Copilot CLI is not installed",
            remediation="Install Copilot CLI from https://github.com/github/gh-copilot"
        )

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="readiness-task-queue",
            workflows=[ReadinessWorkflow],
            activities=[mock_gh_status, mock_copilot_help],
        ):
            result = await env.client.execute_workflow(
                ReadinessWorkflow.run,
                id="test-workflow-both-fail",
                task_queue="readiness-task-queue",
            )

            assert isinstance(result, ReadinessSummary)
            assert result.overall_status == "not_ready"
            assert len(result.results) == 2
            assert all(r.status == "fail" for r in result.results)
            assert all(r.remediation is not None for r in result.results)

            # Verify both have actionable guidance
            for check in result.results:
                assert check.remediation is not None
                assert len(check.remediation) > 0, \
                    f"{check.tool} should have remediation guidance"

                if check.tool == "gh":
                    assert "install" in check.remediation.lower() or "cli.github.com" in check.remediation.lower()
                elif check.tool == "copilot":
                    assert "install" in check.remediation.lower() or "github.com" in check.remediation.lower()
