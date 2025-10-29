"""Integration tests for readiness workflow orchestration."""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from src.models.parameters import Parameters
from src.models.prereq import PrereqCheckResult, ReadinessSummary
from src.models.verification_result import VerificationResult


@pytest.mark.asyncio
async def test_readiness_workflow_all_pass():
    """Test readiness workflow when all prerequisites and repo verification pass."""
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

    @activity.defn(name="verify_repository")
    async def mock_verify_repository(params: Parameters) -> VerificationResult:
        return VerificationResult(
            tool="gh",
            status="pass",
            message="Repository is accessible",
            host="github.com",
            repo_slug="owner/repo",
            error_code="none",
            attempts=1,
            duration_ms=100
        )

    @activity.defn(name="echo_parameters")
    async def mock_echo_parameters(params: Parameters) -> dict:
        return {"github_repo_url": params.github_repo_url}

    params = Parameters(github_repo_url="https://github.com/owner/repo")

    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue="readiness-task-queue",
        workflows=[ReadinessWorkflow],
        activities=[mock_gh_status, mock_copilot_help, mock_verify_repository, mock_echo_parameters],
    ):
        result = await env.client.execute_workflow(
            ReadinessWorkflow.run,
            params,
            id="test-workflow-all-pass",
            task_queue="readiness-task-queue",
        )

        assert isinstance(result, ReadinessSummary)
        assert result.overall_status == "ready"
        assert len(result.results) == 2
        assert all(r.status == "pass" for r in result.results)
        assert result.repo_verification is not None
        assert result.repo_verification.status == "pass"
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

    @activity.defn(name="verify_repository")
    async def mock_verify_repository(params: Parameters) -> VerificationResult:
        return VerificationResult(
            tool="gh",
            status="pass",
            message="Repository is accessible",
            host="github.com",
            repo_slug="owner/repo",
            error_code="none",
            attempts=1,
            duration_ms=100
        )

    @activity.defn(name="echo_parameters")
    async def mock_echo_parameters(params: Parameters) -> dict:
        return {"github_repo_url": params.github_repo_url}

    params = Parameters(github_repo_url="https://github.com/owner/repo")

    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue="readiness-task-queue",
        workflows=[ReadinessWorkflow],
        activities=[mock_gh_status, mock_copilot_help, mock_verify_repository, mock_echo_parameters],
    ):
        result = await env.client.execute_workflow(
            ReadinessWorkflow.run,
            params,
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

    @activity.defn(name="verify_repository")
    async def mock_verify_repository(params: Parameters) -> VerificationResult:
        return VerificationResult(
            tool="gh",
            status="pass",
            message="Repository is accessible",
            host="github.com",
            repo_slug="owner/repo",
            error_code="none",
            attempts=1,
            duration_ms=100
        )

    @activity.defn(name="echo_parameters")
    async def mock_echo_parameters(params: Parameters) -> dict:
        return {"github_repo_url": params.github_repo_url}

    params = Parameters(github_repo_url="https://github.com/owner/repo")

    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue="readiness-task-queue",
        workflows=[ReadinessWorkflow],
        activities=[mock_gh_status, mock_copilot_help, mock_verify_repository, mock_echo_parameters],
    ):
        result = await env.client.execute_workflow(
            ReadinessWorkflow.run,
            params,
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
    """Test readiness workflow when both CLI checks fail."""
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

    @activity.defn(name="verify_repository")
    async def mock_verify_repository(params: Parameters) -> VerificationResult:
        return VerificationResult(
            tool="gh",
            status="pass",
            message="Repository is accessible",
            host="github.com",
            repo_slug="owner/repo",
            error_code="none",
            attempts=1,
            duration_ms=100
        )

    @activity.defn(name="echo_parameters")
    async def mock_echo_parameters(params: Parameters) -> dict:
        return {"github_repo_url": params.github_repo_url}

    params = Parameters(github_repo_url="https://github.com/owner/repo")

    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue="readiness-task-queue",
        workflows=[ReadinessWorkflow],
        activities=[mock_gh_status, mock_copilot_help, mock_verify_repository, mock_echo_parameters],
    ):
        result = await env.client.execute_workflow(
            ReadinessWorkflow.run,
            params,
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


@pytest.mark.asyncio
async def test_readiness_workflow_repo_verification_fails():
    """Test readiness workflow when repository verification fails."""
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

    @activity.defn(name="verify_repository")
    async def mock_verify_repository(params: Parameters) -> VerificationResult:
        return VerificationResult(
            tool="gh",
            status="fail",
            message="Repository not found",
            host="github.com",
            repo_slug="owner/nonexistent",
            error_code="not_found",
            attempts=2,
            duration_ms=200
        )

    params = Parameters(github_repo_url="https://github.com/owner/nonexistent")

    async with await WorkflowEnvironment.start_time_skipping() as env, Worker(
        env.client,
        task_queue="readiness-task-queue",
        workflows=[ReadinessWorkflow],
        activities=[mock_gh_status, mock_copilot_help, mock_verify_repository],
    ):
        result = await env.client.execute_workflow(
            ReadinessWorkflow.run,
            params,
            id="test-workflow-repo-fails",
            task_queue="readiness-task-queue",
        )

        assert isinstance(result, ReadinessSummary)
        assert result.overall_status == "not_ready"
        assert len(result.results) == 2
        # Both CLI checks pass
        assert all(r.status == "pass" for r in result.results)
        # But repo verification fails
        assert result.repo_verification is not None
        assert result.repo_verification.status == "fail"
        assert result.repo_verification.error_code == "not_found"
        assert result.duration_ms > 0
