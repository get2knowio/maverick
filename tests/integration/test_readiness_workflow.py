"""Integration tests for readiness workflow orchestration."""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from src.models.prereq import ReadinessSummary, PrereqCheckResult, CheckStatus, OverallStatus


@pytest.mark.asyncio
async def test_readiness_workflow_all_pass():
    """Test readiness workflow when all prerequisites pass."""
    from src.workflows.readiness import ReadinessWorkflow
    from src.activities.gh_status import check_gh_status
    from src.activities.copilot_help import check_copilot_help
    from unittest.mock import AsyncMock, patch
    from src.models.prereq import PrereqCheckResult
    
    # Mock successful checks
    gh_result = PrereqCheckResult(
        tool="gh",
        status=CheckStatus.PASS,
        message="GitHub CLI is authenticated",
        remediation=""
    )
    copilot_result = PrereqCheckResult(
        tool="copilot",
        status=CheckStatus.PASS,
        message="Copilot CLI is available",
        remediation=""
    )
    
    with patch('src.activities.gh_status.check_gh_status', return_value=gh_result), \
         patch('src.activities.copilot_help.check_copilot_help', return_value=copilot_result):
        
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="readiness-task-queue",
                workflows=[ReadinessWorkflow],
                activities=[check_gh_status, check_copilot_help],
            ):
                result = await env.client.execute_workflow(
                    ReadinessWorkflow.run,
                    id="test-workflow-all-pass",
                    task_queue="readiness-task-queue",
                )
                
                assert isinstance(result, ReadinessSummary)
                assert result.overall_status == OverallStatus.READY
                assert len(result.results) == 2
                assert all(r.status == CheckStatus.PASS for r in result.results)
                assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_readiness_workflow_gh_fails():
    """Test readiness workflow when gh check fails."""
    from src.workflows.readiness import ReadinessWorkflow
    from src.activities.gh_status import check_gh_status
    from src.activities.copilot_help import check_copilot_help
    from unittest.mock import patch
    from src.models.prereq import PrereqCheckResult
    
    # Mock gh failure
    gh_result = PrereqCheckResult(
        tool="gh",
        status=CheckStatus.FAIL,
        message="GitHub CLI is not authenticated",
        remediation="Run 'gh auth login' to authenticate"
    )
    copilot_result = PrereqCheckResult(
        tool="copilot",
        status=CheckStatus.PASS,
        message="Copilot CLI is available",
        remediation=""
    )
    
    with patch('src.activities.gh_status.check_gh_status', return_value=gh_result), \
         patch('src.activities.copilot_help.check_copilot_help', return_value=copilot_result):
        
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="readiness-task-queue",
                workflows=[ReadinessWorkflow],
                activities=[check_gh_status, check_copilot_help],
            ):
                result = await env.client.execute_workflow(
                    ReadinessWorkflow.run,
                    id="test-workflow-gh-fails",
                    task_queue="readiness-task-queue",
                )
                
                assert isinstance(result, ReadinessSummary)
                assert result.overall_status == OverallStatus.NOT_READY
                assert len(result.results) == 2
                gh_check = next(r for r in result.results if r.tool == "gh")
                assert gh_check.status == CheckStatus.FAIL
                assert gh_check.remediation is not None
                assert len(gh_check.remediation) > 0


@pytest.mark.asyncio
async def test_readiness_workflow_copilot_fails():
    """Test readiness workflow when copilot check fails."""
    from src.workflows.readiness import ReadinessWorkflow
    from src.activities.gh_status import check_gh_status
    from src.activities.copilot_help import check_copilot_help
    from unittest.mock import patch
    from src.models.prereq import PrereqCheckResult
    
    # Mock copilot failure
    gh_result = PrereqCheckResult(
        tool="gh",
        status=CheckStatus.PASS,
        message="GitHub CLI is authenticated",
        remediation=""
    )
    copilot_result = PrereqCheckResult(
        tool="copilot",
        status=CheckStatus.FAIL,
        message="Copilot CLI is not installed",
        remediation="Install Copilot CLI from https://github.com/github/gh-copilot"
    )
    
    with patch('src.activities.gh_status.check_gh_status', return_value=gh_result), \
         patch('src.activities.copilot_help.check_copilot_help', return_value=copilot_result):
        
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="readiness-task-queue",
                workflows=[ReadinessWorkflow],
                activities=[check_gh_status, check_copilot_help],
            ):
                result = await env.client.execute_workflow(
                    ReadinessWorkflow.run,
                    id="test-workflow-copilot-fails",
                    task_queue="readiness-task-queue",
                )
                
                assert isinstance(result, ReadinessSummary)
                assert result.overall_status == OverallStatus.NOT_READY
                assert len(result.results) == 2
                copilot_check = next(r for r in result.results if r.tool == "copilot")
                assert copilot_check.status == CheckStatus.FAIL
                assert copilot_check.remediation is not None


@pytest.mark.asyncio
async def test_readiness_workflow_both_fail():
    """Test readiness workflow when both checks fail."""
    from src.workflows.readiness import ReadinessWorkflow
    from src.activities.gh_status import check_gh_status
    from src.activities.copilot_help import check_copilot_help
    from unittest.mock import patch
    from src.models.prereq import PrereqCheckResult
    
    # Mock both failures
    gh_result = PrereqCheckResult(
        tool="gh",
        status=CheckStatus.FAIL,
        message="GitHub CLI is not installed",
        remediation="Install GitHub CLI from https://cli.github.com"
    )
    copilot_result = PrereqCheckResult(
        tool="copilot",
        status=CheckStatus.FAIL,
        message="Copilot CLI is not installed",
        remediation="Install Copilot CLI from https://github.com/github/gh-copilot"
    )
    
    with patch('src.activities.gh_status.check_gh_status', return_value=gh_result), \
         patch('src.activities.copilot_help.check_copilot_help', return_value=copilot_result):
        
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="readiness-task-queue",
                workflows=[ReadinessWorkflow],
                activities=[check_gh_status, check_copilot_help],
            ):
                result = await env.client.execute_workflow(
                    ReadinessWorkflow.run,
                    id="test-workflow-both-fail",
                    task_queue="readiness-task-queue",
                )
                
                assert isinstance(result, ReadinessSummary)
                assert result.overall_status == OverallStatus.NOT_READY
                assert len(result.results) == 2
                assert all(r.status == CheckStatus.FAIL for r in result.results)
                assert all(r.remediation is not None for r in result.results)
