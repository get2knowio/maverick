"""Integration tests for PR CI automation workflow."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.activities.pr_ci_automation import pr_ci_automation
from src.models.phase_automation import (
    PollingConfiguration,
    PullRequestAutomationRequest,
)
from tests.fixtures.pr_ci_automation.gh_cli_stub import GhCliStubHelper, GhCommandStub


@pytest.fixture
def gh_stub() -> GhCliStubHelper:
    """Fixture providing gh CLI stub helper."""
    return GhCliStubHelper()


class MockSubprocessFactory:
    """Factory for creating mock subprocess instances with stubbed responses."""

    def __init__(self, gh_stub: GhCliStubHelper):
        self.gh_stub = gh_stub

    async def create_subprocess_exec(
        self,
        *args: str,
        stdout: Any = asyncio.subprocess.PIPE,
        stderr: Any = asyncio.subprocess.PIPE,
        **kwargs: Any,
    ) -> AsyncMock:
        """Create a mock subprocess with stubbed response."""
        command_parts = tuple(args)
        stub = self.gh_stub.get_stub(command_parts)

        if stub is None:
            stub = GhCommandStub.failure(f"No stub for command: {args}", returncode=1)

        mock_process = AsyncMock()
        mock_process.returncode = stub.returncode
        mock_process.communicate = AsyncMock(return_value=(stub.stdout.encode("utf-8"), stub.stderr.encode("utf-8")))

        return mock_process


# Green-Path Workflow Tests (T008)


@pytest.mark.asyncio
async def test_pr_automation_workflow_success_path(gh_stub: GhCliStubHelper) -> None:
    """Test successful end-to-end PR automation workflow.

    Verifies that the workflow:
    1. Checks remote branch exists
    2. Creates/finds PR
    3. Polls CI until success
    4. Merges PR
    5. Returns merged result
    """
    # Stub git ls-remote for branch existence check
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/test"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/test\n", returncode=0),
    )

    # Stub gh repo view for default branch resolution
    gh_stub.stub_repo_view(default_branch="main")

    # Stub PR creation
    pr_data = {
        "number": 123,
        "url": "https://github.com/owner/repo/pull/123",
        "baseRefName": "main",
        "headRefName": "feature/test",
    }
    gh_stub.add_stub(
        (
            "gh",
            "pr",
            "view",
            "--head",
            "feature/test",
            "--json",
            "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository",
        ),
        GhCommandStub.failure("no pull requests found", returncode=1),
    )
    gh_stub.add_stub(
        (
            "gh",
            "pr",
            "create",
            "--title",
            "Automated PR",
            "--body",
            "Test summary",
            "--base",
            "main",
            "--head",
            "feature/test",
        ),
        GhCommandStub.success(pr_data),
    )

    # Stub PR view for base branch validation
    gh_stub.stub_pr_view(pr_number=123, state="OPEN", base_branch="main", head_branch="feature/test")

    # Stub CI checks - all passing
    checks = [
        {
            "name": "build",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        }
    ]
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    # Stub merge
    gh_stub.stub_pr_merge(pr_number=123, merge_commit_sha="abc123def456")

    factory = MockSubprocessFactory(gh_stub)

    # Create request
    request = PullRequestAutomationRequest(
        source_branch="feature/test",
        target_branch="main",
        summary="Test summary",
        workflow_attempt_id="test-123",
        polling=PollingConfiguration(interval_seconds=1, timeout_minutes=1, max_retries=0),
    )

    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        patch("asyncio.sleep", new=AsyncMock()),  # Speed up polling
    ):
        result = await pr_ci_automation(request)

        assert result.status == "merged"
        assert result.pull_request_number == 123
        assert result.pull_request_url == "https://github.com/owner/repo/pull/123"
        assert result.merge_commit_sha == "abc123def456"
        assert result.polling_duration_seconds >= 0


@pytest.mark.asyncio
async def test_pr_automation_workflow_ci_failure(gh_stub: GhCliStubHelper) -> None:
    """Test workflow handles CI failures gracefully."""
    # Stub branch check
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/test"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/test\n", returncode=0),
    )

    # Stub repo view
    gh_stub.stub_repo_view(default_branch="main")

    # Stub existing PR
    gh_stub.stub_pr_view(pr_number=123, state="OPEN", base_branch="main", head_branch="feature/test")

    # Stub base branch validation
    gh_stub.add_stub(
        ("gh", "pr", "view", "123", "--json", "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository"),
        GhCommandStub.success(
            {
                "number": 123,
                "state": "OPEN",
                "baseRefName": "main",
                "headRefName": "feature/test",
                "url": "https://github.com/owner/repo/pull/123",
                "mergedAt": None,
                "isCrossRepository": False,
            }
        ),
    )

    # Stub PR description update
    gh_stub.add_stub(("gh", "pr", "edit", "123", "--body", "Test summary"), GhCommandStub.success({"number": 123}))

    # Stub CI checks - one failure
    checks = [
        {
            "name": "build",
            "status": "completed",
            "conclusion": "failure",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        }
    ]
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/test",
        target_branch="main",
        summary="Test summary",
        workflow_attempt_id="test-456",
        polling=PollingConfiguration(interval_seconds=1, timeout_minutes=1, max_retries=0),
    )

    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = await pr_ci_automation(request)

        assert result.status == "ci_failed"
        assert result.pull_request_number == 123
        assert len(result.ci_failures) == 1
        assert result.ci_failures[0].job_name == "build"
        assert result.ci_failures[0].status == "failure"


# Base-Branch Mismatch Tests (T039)


@pytest.mark.asyncio
async def test_pr_automation_workflow_base_branch_mismatch(gh_stub: GhCliStubHelper) -> None:
    """Test workflow returns error for base-branch mismatch."""
    # Stub branch check
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/test"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/test\n", returncode=0),
    )

    # Stub repo view to resolve default branch
    gh_stub.stub_repo_view(default_branch="main")

    # Stub existing PR with different base branch
    gh_stub.stub_pr_view(
        pr_number=123,
        state="OPEN",
        base_branch="develop",  # Mismatch!
        head_branch="feature/test",
    )

    # Stub base branch validation (will fail)
    gh_stub.add_stub(
        ("gh", "pr", "view", "123", "--json", "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository"),
        GhCommandStub.success(
            {
                "number": 123,
                "state": "OPEN",
                "baseRefName": "develop",  # Mismatch with expected "main"
                "headRefName": "feature/test",
                "url": "https://github.com/owner/repo/pull/123",
                "mergedAt": None,
                "isCrossRepository": False,
            }
        ),
    )

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/test",
        target_branch="main",  # Expects main, but PR targets develop
        summary="Test summary",
        workflow_attempt_id="test-789",
    )

    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await pr_ci_automation(request)

        # Should return error status with details
        assert result.status == "error"
        assert result.pull_request_number == 123
        assert result.error_detail is not None
        assert "Base branch mismatch" in result.error_detail
        assert result.retry_advice is not None
        assert "Update target branch" in result.retry_advice


# CI Failed Output Tests (T016)


@pytest.mark.asyncio
async def test_pr_automation_workflow_ci_failed_multiple_jobs(gh_stub: GhCliStubHelper) -> None:
    """Test workflow captures multiple CI job failures."""
    # Stub branch check
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/multi-fail"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/multi-fail\n", returncode=0),
    )

    # Stub repo view
    gh_stub.stub_repo_view(default_branch="main")

    # Stub existing PR
    gh_stub.stub_pr_view(pr_number=456, state="OPEN", base_branch="main", head_branch="feature/multi-fail")

    # Stub base branch validation
    gh_stub.add_stub(
        ("gh", "pr", "view", "456", "--json", "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository"),
        GhCommandStub.success(
            {
                "number": 456,
                "state": "OPEN",
                "baseRefName": "main",
                "headRefName": "feature/multi-fail",
                "url": "https://github.com/owner/repo/pull/456",
                "mergedAt": None,
                "isCrossRepository": False,
            }
        ),
    )

    # Stub PR description update
    gh_stub.add_stub(
        ("gh", "pr", "edit", "456", "--body", "Multi-failure test"), GhCommandStub.success({"number": 456})
    )

    # Stub CI checks - multiple failures
    checks = [
        {
            "name": "lint",
            "status": "completed",
            "conclusion": "failure",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        },
        {
            "name": "test",
            "status": "completed",
            "conclusion": "failure",
            "completedAt": "2025-01-01T00:06:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/2",
        },
        {
            "name": "build",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T00:07:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/3",
        },
    ]
    gh_stub.stub_pr_checks(pr_number=456, checks=checks)

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/multi-fail",
        target_branch="main",
        summary="Multi-failure test",
        workflow_attempt_id="test-multi-fail",
        polling=PollingConfiguration(interval_seconds=1, timeout_minutes=1, max_retries=0),
    )

    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = await pr_ci_automation(request)

        # Verify ci_failed status with failure details
        assert result.status == "ci_failed"
        assert result.pull_request_number == 456
        assert len(result.ci_failures) == 2  # lint and test failed

        # Verify failure details are structured correctly
        job_names = {f.job_name for f in result.ci_failures}
        assert "lint" in job_names
        assert "test" in job_names
        assert "build" not in job_names  # Success should not be in failures

        # Verify each failure has required fields
        for failure in result.ci_failures:
            assert failure.job_name in ("lint", "test")
            assert failure.status == "failure"
            assert failure.log_url is not None
            assert failure.completed_at is not None
            assert failure.attempt >= 1


@pytest.mark.asyncio
async def test_pr_automation_workflow_ci_failed_with_cancelled(gh_stub: GhCliStubHelper) -> None:
    """Test workflow captures cancelled and timed_out jobs as failures."""
    # Stub branch check
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/cancelled"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/cancelled\n", returncode=0),
    )

    # Stub repo view
    gh_stub.stub_repo_view(default_branch="main")

    # Stub existing PR
    gh_stub.stub_pr_view(pr_number=789, state="OPEN", base_branch="main", head_branch="feature/cancelled")

    # Stub base branch validation
    gh_stub.add_stub(
        ("gh", "pr", "view", "789", "--json", "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository"),
        GhCommandStub.success(
            {
                "number": 789,
                "state": "OPEN",
                "baseRefName": "main",
                "headRefName": "feature/cancelled",
                "url": "https://github.com/owner/repo/pull/789",
                "mergedAt": None,
                "isCrossRepository": False,
            }
        ),
    )

    # Stub PR description update
    gh_stub.add_stub(("gh", "pr", "edit", "789", "--body", "Cancelled test"), GhCommandStub.success({"number": 789}))

    # Stub CI checks - cancelled and timed_out
    checks = [
        {
            "name": "slow-test",
            "status": "completed",
            "conclusion": "timed_out",
            "completedAt": "2025-01-01T00:30:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        },
        {
            "name": "cancelled-build",
            "status": "completed",
            "conclusion": "cancelled",
            "completedAt": "2025-01-01T00:10:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/2",
        },
    ]
    gh_stub.stub_pr_checks(pr_number=789, checks=checks)

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/cancelled",
        target_branch="main",
        summary="Cancelled test",
        workflow_attempt_id="test-cancelled",
        polling=PollingConfiguration(interval_seconds=1, timeout_minutes=1, max_retries=0),
    )

    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = await pr_ci_automation(request)

        # Verify both cancelled and timed_out are captured as failures
        assert result.status == "ci_failed"
        assert len(result.ci_failures) == 2

        statuses = {f.status for f in result.ci_failures}
        assert "timed_out" in statuses
        assert "cancelled" in statuses


# Resume Workflow Tests (T021 - Phase 5: User Story 3)


@pytest.mark.asyncio
async def test_pr_automation_workflow_resume_after_already_merged(gh_stub: GhCliStubHelper) -> None:
    """Test workflow resume when PR is already merged from previous run.

    Verifies that:
    1. Activity detects PR is already merged
    2. Returns merged status immediately without re-polling CI
    3. Includes correct merge commit SHA
    """
    # Stub git ls-remote for branch existence check
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/already-merged"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/already-merged\n", returncode=0),
    )

    # Stub gh repo view for default branch resolution
    gh_stub.stub_repo_view(default_branch="main")

    # Stub PR view to return already-merged PR
    merged_pr_data = {
        "number": 555,
        "url": "https://github.com/owner/repo/pull/555",
        "state": "MERGED",
        "baseRefName": "main",
        "headRefName": "feature/already-merged",
        "mergedAt": "2025-01-01T10:00:00Z",
        "isCrossRepository": False,
    }
    gh_stub.add_stub(
        (
            "gh",
            "pr",
            "view",
            "--head",
            "feature/already-merged",
            "--json",
            "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository",
        ),
        GhCommandStub.success(merged_pr_data),
    )

    # Stub query for merge commit SHA
    gh_stub.add_stub(
        ("gh", "pr", "view", "555", "--json", "mergeCommit"),
        GhCommandStub(stdout='{"mergeCommit": {"oid": "already-merged-sha"}}', returncode=0),
    )

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/already-merged",
        target_branch="main",
        summary="Already merged PR",
        workflow_attempt_id="resume-merged-001",
    )

    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await pr_ci_automation(request)

        # Should return merged status immediately
        assert result.status == "merged"
        assert result.pull_request_number == 555
        assert result.merge_commit_sha == "already-merged-sha"
        assert result.polling_duration_seconds == 0  # No polling needed


@pytest.mark.asyncio
async def test_pr_automation_workflow_resume_with_new_ci_pass(gh_stub: GhCliStubHelper) -> None:
    """Test workflow resume when PR now passes CI after previous timeout/failure.

    Verifies that:
    1. Reuses existing open PR from previous run
    2. Re-polls CI and detects success
    3. Merges successfully
    """
    # Stub git ls-remote for branch existence check
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/retry-pass"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/retry-pass\n", returncode=0),
    )

    # Stub gh repo view for default branch resolution
    gh_stub.stub_repo_view(default_branch="main")

    # Stub PR view to return existing open PR
    open_pr_data = {
        "number": 666,
        "url": "https://github.com/owner/repo/pull/666",
        "state": "OPEN",
        "baseRefName": "main",
        "headRefName": "feature/retry-pass",
        "mergedAt": None,
        "isCrossRepository": False,
    }
    gh_stub.add_stub(
        (
            "gh",
            "pr",
            "view",
            "--head",
            "feature/retry-pass",
            "--json",
            "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository",
        ),
        GhCommandStub.success(open_pr_data),
    )

    # Stub base branch validation (fetches full PR details)
    gh_stub.add_stub(
        (
            "gh",
            "pr",
            "view",
            "666",
            "--json",
            "number,state,baseRefName,headRefName,url,mergedAt,isCrossRepository",
        ),
        GhCommandStub.success(open_pr_data),
    )

    # Stub PR description update
    gh_stub.add_stub(("gh", "pr", "edit", "666", "--body", "Retry pass"), GhCommandStub.success({"number": 666}))

    # Stub CI checks - now passing after previous failure
    checks = [
        {
            "name": "build",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T01:00:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/100",
        },
        {
            "name": "test",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T01:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/101",
        },
    ]
    gh_stub.stub_pr_checks(pr_number=666, checks=checks)

    # Stub merge
    gh_stub.stub_pr_merge(pr_number=666, merge_commit_sha="retry-success-sha")

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/retry-pass",
        target_branch="main",
        summary="Retry pass",
        workflow_attempt_id="resume-pass-001",
        polling=PollingConfiguration(interval_seconds=1, timeout_minutes=1, max_retries=0),
    )

    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = await pr_ci_automation(request)

        # Should successfully merge after re-polling
        assert result.status == "merged"
        assert result.pull_request_number == 666
        assert result.merge_commit_sha == "retry-success-sha"
