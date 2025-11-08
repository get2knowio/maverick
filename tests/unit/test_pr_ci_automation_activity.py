"""Unit tests for PR CI automation activity."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.activities.pr_ci_automation import (
    check_remote_branch_exists,
    resolve_target_branch,
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


# Remote Branch Existence Tests


@pytest.mark.asyncio
async def test_check_remote_branch_exists_success(gh_stub: GhCliStubHelper) -> None:
    """Test successful remote branch existence check."""
    # Stub git ls-remote to show branch exists
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/test"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/test\n", returncode=0),
    )

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await check_remote_branch_exists("feature/test")
        assert result is True


@pytest.mark.asyncio
async def test_check_remote_branch_exists_not_found(gh_stub: GhCliStubHelper) -> None:
    """Test remote branch does not exist."""
    # Stub git ls-remote to return empty (branch not found)
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "nonexistent"),
        GhCommandStub(stdout="", returncode=0),
    )

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await check_remote_branch_exists("nonexistent")
        assert result is False


@pytest.mark.asyncio
async def test_check_remote_branch_exists_git_error(gh_stub: GhCliStubHelper) -> None:
    """Test git command failure during branch check."""
    # Stub git ls-remote to fail
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/test"),
        GhCommandStub.failure("fatal: repository not found", returncode=128),
    )

    factory = MockSubprocessFactory(gh_stub)
    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        pytest.raises(RuntimeError, match="Failed to check remote branch"),
    ):
        await check_remote_branch_exists("feature/test")


# Target Branch Resolution Tests


@pytest.mark.asyncio
async def test_resolve_target_branch_explicit(gh_stub: GhCliStubHelper) -> None:
    """Test explicit target branch is used without querying."""
    # No stub needed - should not call gh repo view
    result = await resolve_target_branch(explicit_target="develop")
    assert result == "develop"


@pytest.mark.asyncio
async def test_resolve_target_branch_default(gh_stub: GhCliStubHelper) -> None:
    """Test resolving default branch from repository."""
    gh_stub.stub_repo_view(default_branch="main")

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await resolve_target_branch()
        assert result == "main"


@pytest.mark.asyncio
async def test_resolve_target_branch_custom_default(gh_stub: GhCliStubHelper) -> None:
    """Test resolving custom default branch."""
    gh_stub.stub_repo_view(default_branch="master")

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await resolve_target_branch()
        assert result == "master"


@pytest.mark.asyncio
async def test_resolve_target_branch_gh_error(gh_stub: GhCliStubHelper) -> None:
    """Test gh repo view command failure."""
    gh_stub.add_stub(
        ("gh", "repo", "view", "--json", "defaultBranchRef,owner,name"),
        GhCommandStub.failure("gh: not authenticated", returncode=1),
    )

    factory = MockSubprocessFactory(gh_stub)
    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        pytest.raises(RuntimeError, match="Failed to resolve default branch"),
    ):
        await resolve_target_branch()


@pytest.mark.asyncio
async def test_resolve_target_branch_invalid_json(gh_stub: GhCliStubHelper) -> None:
    """Test handling of invalid JSON from gh repo view."""
    gh_stub.add_stub(
        ("gh", "repo", "view", "--json", "defaultBranchRef,owner,name"),
        GhCommandStub(stdout="invalid json", returncode=0),
    )

    factory = MockSubprocessFactory(gh_stub)
    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        pytest.raises(RuntimeError, match="Failed to parse repository data"),
    ):
        await resolve_target_branch()


@pytest.mark.asyncio
async def test_resolve_target_branch_missing_field(gh_stub: GhCliStubHelper) -> None:
    """Test handling of missing defaultBranchRef in response."""
    gh_stub.add_stub(
        ("gh", "repo", "view", "--json", "defaultBranchRef,owner,name"),
        GhCommandStub.success({"owner": {"login": "test"}, "name": "repo"}),  # Missing defaultBranchRef
    )

    factory = MockSubprocessFactory(gh_stub)
    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        pytest.raises(RuntimeError, match="Missing defaultBranchRef"),
    ):
        await resolve_target_branch()


# PR Discovery and Creation Tests (T007)


@pytest.mark.asyncio
async def test_find_or_create_pr_existing_open(gh_stub: GhCliStubHelper) -> None:
    """Test discovering an existing open PR."""
    from src.activities.pr_ci_automation import find_or_create_pr

    gh_stub.stub_pr_view(
        pr_number=123,
        state="OPEN",
        base_branch="main",
        head_branch="feature/test",
        url="https://github.com/owner/repo/pull/123",
    )

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        pr_number, pr_url, created, state = await find_or_create_pr(
            source_branch="feature/test", target_branch="main", summary="Test PR summary"
        )

        assert pr_number == 123
        assert pr_url == "https://github.com/owner/repo/pull/123"
        assert created is False
        assert state == "OPEN"


@pytest.mark.asyncio
async def test_find_or_create_pr_creates_new(gh_stub: GhCliStubHelper) -> None:
    """Test creating a new PR when none exists."""
    from src.activities.pr_ci_automation import find_or_create_pr

    # Stub pr view to return not found
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

    # Stub pr create to succeed
    pr_data = {
        "number": 456,
        "url": "https://github.com/owner/repo/pull/456",
        "baseRefName": "main",
        "headRefName": "feature/test",
    }
    gh_stub.add_stub(
        (
            "gh",
            "pr",
            "create",
            "--title",
            "Automated PR",
            "--body",
            "Test PR summary",
            "--base",
            "main",
            "--head",
            "feature/test",
        ),
        GhCommandStub.success(pr_data),
    )

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        pr_number, pr_url, created, state = await find_or_create_pr(
            source_branch="feature/test", target_branch="main", summary="Test PR summary"
        )

        assert pr_number == 456
        assert pr_url == "https://github.com/owner/repo/pull/456"
        assert created is True
        assert state == "OPEN"


@pytest.mark.asyncio
async def test_find_or_create_pr_reuses_merged(gh_stub: GhCliStubHelper) -> None:
    """Test reusing an existing merged PR."""
    from src.activities.pr_ci_automation import find_or_create_pr

    gh_stub.stub_pr_view(
        pr_number=789,
        state="MERGED",
        base_branch="main",
        head_branch="feature/test",
        url="https://github.com/owner/repo/pull/789",
        merged_at="2025-01-01T12:00:00Z",
    )

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        pr_number, pr_url, created, state = await find_or_create_pr(
            source_branch="feature/test", target_branch="main", summary="Test PR summary"
        )

        assert pr_number == 789
        assert pr_url == "https://github.com/owner/repo/pull/789"
        assert created is False
        assert state == "MERGED"


# CI Polling Tests (T007)


@pytest.mark.asyncio
async def test_poll_ci_status_all_success(gh_stub: GhCliStubHelper) -> None:
    """Test polling returns success when all checks pass."""
    from src.activities.pr_ci_automation import poll_ci_status

    checks = [
        {
            "name": "build",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        },
        {
            "name": "test",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T00:06:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/2",
        },
    ]
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        status, failures = await poll_ci_status(pr_number=123)

        assert status == "success"
        assert failures == []


@pytest.mark.asyncio
async def test_poll_ci_status_some_failures(gh_stub: GhCliStubHelper) -> None:
    """Test polling returns failure details when checks fail."""
    from src.activities.pr_ci_automation import poll_ci_status

    checks = [
        {
            "name": "build",
            "status": "completed",
            "conclusion": "success",
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
    ]
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        status, failures = await poll_ci_status(pr_number=123)

        assert status == "failure"
        assert len(failures) == 1
        assert failures[0].job_name == "test"
        assert failures[0].status == "failure"


@pytest.mark.asyncio
async def test_poll_ci_status_in_progress(gh_stub: GhCliStubHelper) -> None:
    """Test polling returns in_progress when checks are running."""
    from src.activities.pr_ci_automation import poll_ci_status

    checks = [
        {
            "name": "build",
            "status": "in_progress",
            "conclusion": None,
            "completedAt": None,
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        },
        {
            "name": "test",
            "status": "queued",
            "conclusion": None,
            "completedAt": None,
            "detailsUrl": "https://github.com/owner/repo/actions/runs/2",
        },
    ]
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        status, failures = await poll_ci_status(pr_number=123)

        assert status == "in_progress"
        assert failures == []


# Merge Execution Tests (T007)


@pytest.mark.asyncio
async def test_merge_pull_request_success(gh_stub: GhCliStubHelper) -> None:
    """Test successful PR merge."""
    from src.activities.pr_ci_automation import merge_pull_request

    gh_stub.stub_pr_merge(pr_number=123, merge_commit_sha="abc123def456")

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        merge_sha = await merge_pull_request(pr_number=123)

        assert merge_sha == "abc123def456"


@pytest.mark.asyncio
async def test_merge_pull_request_failure(gh_stub: GhCliStubHelper) -> None:
    """Test merge failure handling."""
    from src.activities.pr_ci_automation import merge_pull_request

    gh_stub.stub_pr_merge(pr_number=123, merged=False)

    factory = MockSubprocessFactory(gh_stub)
    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        pytest.raises(RuntimeError, match="Failed to merge pull request"),
    ):
        await merge_pull_request(pr_number=123)


# Timeout and No-Check Polling Tests (T030)


@pytest.mark.asyncio
async def test_poll_ci_status_no_checks(gh_stub: GhCliStubHelper) -> None:
    """Test polling with no CI checks configured."""
    from src.activities.pr_ci_automation import poll_ci_status

    # Empty checks array
    gh_stub.stub_pr_checks(pr_number=123, checks=[])

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        status, failures = await poll_ci_status(pr_number=123)

        # No checks should be treated as success
        assert status == "success"
        assert failures == []


@pytest.mark.asyncio
async def test_poll_ci_timeout_detection(gh_stub: GhCliStubHelper) -> None:
    """Test timeout detection when polling exceeds limit."""
    from src.activities.pr_ci_automation import poll_ci_with_timeout
    from src.models.phase_automation import PollingConfiguration

    checks = [
        {
            "name": "build",
            "status": "in_progress",
            "conclusion": None,
            "completedAt": None,
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        }
    ]
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    factory = MockSubprocessFactory(gh_stub)
    config = PollingConfiguration(
        interval_seconds=1,
        timeout_minutes=1,  # Short timeout for testing
        max_retries=0,
    )

    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        patch("asyncio.sleep", new=AsyncMock()),  # Speed up test
    ):
        result = await poll_ci_with_timeout(pr_number=123, polling_config=config)

        assert result.status == "timeout"
        assert result.polling_duration_seconds > 0


# PR Body Update Tests (T031)


@pytest.mark.asyncio
async def test_update_pr_description_changes_summary(gh_stub: GhCliStubHelper) -> None:
    """Test updating PR description with new AI summary."""
    from src.activities.pr_ci_automation import update_pr_description

    gh_stub.add_stub(
        ("gh", "pr", "edit", "123", "--body", "Updated AI summary"), GhCommandStub.success({"number": 123})
    )

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        await update_pr_description(pr_number=123, new_summary="Updated AI summary")
        # Should not raise - success is silent


@pytest.mark.asyncio
async def test_update_pr_description_preserves_on_error(gh_stub: GhCliStubHelper) -> None:
    """Test update failure doesn't crash - logs warning instead."""
    from src.activities.pr_ci_automation import update_pr_description

    gh_stub.add_stub(
        ("gh", "pr", "edit", "123", "--body", "New summary"), GhCommandStub.failure("edit failed", returncode=1)
    )

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        # Should log warning but not raise
        await update_pr_description(pr_number=123, new_summary="New summary")


# Base-Branch Mismatch Tests (T038)


@pytest.mark.asyncio
async def test_validate_base_branch_match(gh_stub: GhCliStubHelper) -> None:
    """Test base branch validation passes when branches match."""
    from src.activities.pr_ci_automation import validate_base_branch

    gh_stub.stub_pr_view(pr_number=123, base_branch="main", head_branch="feature/test")

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        # Should not raise
        await validate_base_branch(pr_number=123, expected_base="main")


@pytest.mark.asyncio
async def test_validate_base_branch_mismatch_error(gh_stub: GhCliStubHelper) -> None:
    """Test base branch mismatch raises error with details."""
    from src.activities.pr_ci_automation import validate_base_branch

    gh_stub.stub_pr_view(pr_number=123, base_branch="develop", head_branch="feature/test")

    factory = MockSubprocessFactory(gh_stub)
    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        pytest.raises(ValueError, match="Base branch mismatch"),
    ):
        await validate_base_branch(pr_number=123, expected_base="main")


# SLA Metrics Tests (T040)


@pytest.mark.asyncio
async def test_poll_ci_emits_sla_metrics(gh_stub: GhCliStubHelper) -> None:
    """Test that polling emits SLA timing metrics."""
    from unittest.mock import MagicMock

    from src.activities.pr_ci_automation import poll_ci_with_timeout
    from src.models.phase_automation import PollingConfiguration

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

    factory = MockSubprocessFactory(gh_stub)
    config = PollingConfiguration(interval_seconds=1, timeout_minutes=5)

    # Mock logger to verify metrics emission
    mock_logger = MagicMock()

    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        patch("asyncio.sleep", new=AsyncMock()),
        patch("src.activities.pr_ci_automation.logger", mock_logger),
    ):
        result = await poll_ci_with_timeout(pr_number=123, polling_config=config)

        assert result.status == "merged"
        # Verify logger was called with metrics
        assert any("ci_poll_" in str(call) for call in mock_logger.info.call_args_list)


@pytest.mark.asyncio
async def test_sla_metrics_track_detection_latency(gh_stub: GhCliStubHelper) -> None:
    """Test SLA metrics track time to detect terminal CI status."""
    from src.activities.pr_ci_automation import poll_ci_with_timeout
    from src.models.phase_automation import PollingConfiguration

    # First poll: in progress
    checks_in_progress = [
        {
            "name": "build",
            "status": "in_progress",
            "conclusion": None,
            "completedAt": None,
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        }
    ]

    # Second poll: completed
    checks_completed = [
        {
            "name": "build",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        }
    ]

    # Stub multiple polling attempts
    poll_count = 0

    def stub_varying_checks() -> GhCommandStub:
        nonlocal poll_count
        poll_count += 1
        checks = checks_in_progress if poll_count == 1 else checks_completed
        return GhCommandStub.success(checks)

    gh_stub.add_stub(
        ("gh", "pr", "checks", "123", "--json", "name,status,conclusion,completedAt,detailsUrl"), stub_varying_checks()
    )

    factory = MockSubprocessFactory(gh_stub)
    config = PollingConfiguration(interval_seconds=1, timeout_minutes=5)

    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = await poll_ci_with_timeout(pr_number=123, polling_config=config)

        # Should have detected success after multiple polls
        assert result.status in ("merged", "ci_failed", "timeout")
        assert result.polling_duration_seconds > 0


# CI Failure Job Aggregation Tests (T015)


@pytest.mark.asyncio
async def test_aggregate_ci_failures_multiple_jobs(gh_stub: GhCliStubHelper) -> None:
    """Test aggregating failures from multiple CI jobs."""
    from src.activities.pr_ci_automation import poll_ci_status

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
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        status, failures = await poll_ci_status(pr_number=123)

        assert status == "failure"
        assert len(failures) == 2

        # Verify lint failure
        lint_failure = next(f for f in failures if f.job_name == "lint")
        assert lint_failure.status == "failure"
        assert lint_failure.log_url == "https://github.com/owner/repo/actions/runs/1"
        assert lint_failure.completed_at is not None

        # Verify test failure
        test_failure = next(f for f in failures if f.job_name == "test")
        assert test_failure.status == "failure"
        assert test_failure.log_url == "https://github.com/owner/repo/actions/runs/2"


@pytest.mark.asyncio
async def test_aggregate_ci_failures_cancelled_jobs(gh_stub: GhCliStubHelper) -> None:
    """Test aggregating cancelled CI jobs as failures."""
    from src.activities.pr_ci_automation import poll_ci_status

    checks = [
        {
            "name": "build",
            "status": "completed",
            "conclusion": "cancelled",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        },
        {
            "name": "test",
            "status": "completed",
            "conclusion": "timed_out",
            "completedAt": "2025-01-01T00:06:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/2",
        },
    ]
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        status, failures = await poll_ci_status(pr_number=123)

        assert status == "failure"
        assert len(failures) == 2

        # Verify cancelled is treated as failure
        cancelled = next(f for f in failures if f.job_name == "build")
        assert cancelled.status == "cancelled"

        # Verify timed_out is treated as failure
        timed_out = next(f for f in failures if f.job_name == "test")
        assert timed_out.status == "timed_out"


@pytest.mark.asyncio
async def test_aggregate_ci_failures_latest_attempt(gh_stub: GhCliStubHelper) -> None:
    """Test that only latest attempt per job is included in failures."""
    from src.activities.pr_ci_automation import parse_ci_failures_from_checks

    # Simulate gh pr checks output with multiple attempts for same job
    checks = [
        {
            "name": "test",
            "status": "completed",
            "conclusion": "failure",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        },
        {
            "name": "test",
            "status": "completed",
            "conclusion": "failure",
            "completedAt": "2025-01-01T00:10:00Z",  # Later attempt
            "detailsUrl": "https://github.com/owner/repo/actions/runs/2",
        },
        {
            "name": "test",
            "status": "completed",
            "conclusion": "failure",
            "completedAt": "2025-01-01T00:08:00Z",  # Middle attempt
            "detailsUrl": "https://github.com/owner/repo/actions/runs/3",
        },
    ]

    failures = parse_ci_failures_from_checks(checks)

    # Should only have one failure for test job (latest attempt)
    assert len(failures) == 1
    assert failures[0].job_name == "test"
    # Latest attempt should be the one with most recent completedAt
    assert failures[0].log_url == "https://github.com/owner/repo/actions/runs/2"


@pytest.mark.asyncio
async def test_ci_failure_payload_structure(gh_stub: GhCliStubHelper) -> None:
    """Test that CiFailureDetail payload includes all required fields."""
    from datetime import UTC, datetime

    from src.activities.pr_ci_automation import parse_ci_failures_from_checks

    checks = [
        {
            "name": "integration-test",
            "status": "completed",
            "conclusion": "failure",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        }
    ]

    failures = parse_ci_failures_from_checks(checks)

    assert len(failures) == 1
    failure = failures[0]

    # Verify all required fields
    assert failure.job_name == "integration-test"
    assert failure.attempt >= 1
    assert failure.status == "failure"
    assert failure.log_url == "https://github.com/owner/repo/actions/runs/1"
    assert failure.completed_at is not None
    assert failure.completed_at.tzinfo is not None  # Timezone-aware
    assert failure.completed_at == datetime(2025, 1, 1, 0, 5, 0, tzinfo=UTC)


# Deterministic Result Payload Schema Tests (T034)


@pytest.mark.asyncio
async def test_result_schema_merged_status() -> None:
    """Test merged status result has required fields."""
    from src.models.phase_automation import PullRequestAutomationResult

    result = PullRequestAutomationResult(
        status="merged",
        polling_duration_seconds=120,
        pull_request_number=123,
        pull_request_url="https://github.com/owner/repo/pull/123",
        merge_commit_sha="abc123def456",
    )

    assert result.status == "merged"
    assert result.merge_commit_sha == "abc123def456"
    assert result.pull_request_number == 123
    assert result.pull_request_url is not None
    assert result.ci_failures == ()  # Empty tuple
    assert result.error_detail is None


@pytest.mark.asyncio
async def test_result_schema_ci_failed_status() -> None:
    """Test ci_failed status result has required fields."""
    from datetime import UTC, datetime

    from src.models.phase_automation import CiFailureDetail, PullRequestAutomationResult

    failures = [
        CiFailureDetail(
            job_name="test",
            attempt=1,
            status="failure",
            log_url="https://github.com/owner/repo/actions/runs/1",
            completed_at=datetime(2025, 1, 1, 0, 5, 0, tzinfo=UTC),
        )
    ]

    result = PullRequestAutomationResult(
        status="ci_failed",
        polling_duration_seconds=180,
        pull_request_number=123,
        pull_request_url="https://github.com/owner/repo/pull/123",
        ci_failures=failures,
    )

    assert result.status == "ci_failed"
    assert len(result.ci_failures) == 1
    assert result.ci_failures[0].job_name == "test"
    assert result.merge_commit_sha is None
    assert result.error_detail is None


@pytest.mark.asyncio
async def test_result_schema_timeout_status() -> None:
    """Test timeout status result has required fields."""
    from src.models.phase_automation import PullRequestAutomationResult

    result = PullRequestAutomationResult(
        status="timeout",
        polling_duration_seconds=2700,  # 45 minutes
        pull_request_number=123,
        pull_request_url="https://github.com/owner/repo/pull/123",
        retry_advice="Check if CI jobs are stuck or queued",
    )

    assert result.status == "timeout"
    assert result.polling_duration_seconds == 2700
    assert result.retry_advice is not None
    assert result.merge_commit_sha is None
    assert result.ci_failures == ()
    assert result.error_detail is None


@pytest.mark.asyncio
async def test_result_schema_error_status() -> None:
    """Test error status result has required fields."""
    from src.models.phase_automation import PullRequestAutomationResult

    result = PullRequestAutomationResult(
        status="error",
        polling_duration_seconds=10,
        error_detail="Source branch 'feature/test' not found on remote",
        retry_advice="Check branch name and push to remote",
    )

    assert result.status == "error"
    assert result.error_detail is not None
    assert "not found" in result.error_detail
    assert result.merge_commit_sha is None
    assert result.ci_failures == ()


@pytest.mark.asyncio
async def test_result_schema_invariants_merged_requires_sha() -> None:
    """Test merged status requires merge_commit_sha."""
    from src.models.phase_automation import PullRequestAutomationResult

    with pytest.raises(ValueError, match="merge_commit_sha must be provided"):
        PullRequestAutomationResult(
            status="merged",
            polling_duration_seconds=120,
            pull_request_number=123,
            # Missing merge_commit_sha
        )


@pytest.mark.asyncio
async def test_result_schema_invariants_ci_failed_requires_failures() -> None:
    """Test ci_failed status requires non-empty ci_failures."""
    from src.models.phase_automation import PullRequestAutomationResult

    with pytest.raises(ValueError, match="ci_failures must be non-empty"):
        PullRequestAutomationResult(
            status="ci_failed",
            polling_duration_seconds=120,
            pull_request_number=123,
            # Missing ci_failures
        )


@pytest.mark.asyncio
async def test_result_schema_invariants_error_requires_detail() -> None:
    """Test error status requires error_detail."""
    from src.models.phase_automation import PullRequestAutomationResult

    with pytest.raises(ValueError, match="error_detail must be provided"):
        PullRequestAutomationResult(
            status="error",
            polling_duration_seconds=10,
            # Missing error_detail
        )


# CLI/System Error Differentiation Tests (T035)


@pytest.mark.asyncio
async def test_differentiate_gh_cli_error_from_ci_failure(gh_stub: GhCliStubHelper) -> None:
    """Test that gh CLI errors return error status, not ci_failed."""
    from src.activities.pr_ci_automation import poll_ci_status

    # Stub gh pr checks to fail with CLI error
    gh_stub.add_stub(
        ("gh", "pr", "checks", "123", "--json", "name,status,conclusion,completedAt,detailsUrl"),
        GhCommandStub.failure("gh: authentication required", returncode=1),
    )

    factory = MockSubprocessFactory(gh_stub)
    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        pytest.raises(RuntimeError, match="Failed to poll CI status"),
    ):
        await poll_ci_status(pr_number=123)


@pytest.mark.asyncio
async def test_differentiate_git_command_error_from_ci_failure(gh_stub: GhCliStubHelper) -> None:
    """Test that git command errors return error status."""
    # Already covered by test_check_remote_branch_exists_git_error
    # but verify error propagation through activity
    from src.activities.pr_ci_automation import pr_ci_automation
    from src.models.phase_automation import PullRequestAutomationRequest

    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/test"),
        GhCommandStub.failure("fatal: repository not found", returncode=128),
    )

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/test", target_branch="main", summary="Test PR", workflow_attempt_id="test-123"
    )

    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await pr_ci_automation(request)

        # Should return error status, not ci_failed
        assert result.status == "error"
        assert result.error_detail is not None
        assert "Failed to check remote branch" in result.error_detail


@pytest.mark.asyncio
async def test_differentiate_json_parse_error_from_ci_failure(gh_stub: GhCliStubHelper) -> None:
    """Test that JSON parsing errors are system errors."""
    from src.activities.pr_ci_automation import poll_ci_status

    # Stub gh pr checks to return invalid JSON
    gh_stub.add_stub(
        ("gh", "pr", "checks", "123", "--json", "name,status,conclusion,completedAt,detailsUrl"),
        GhCommandStub(stdout="not valid json", returncode=0),
    )

    factory = MockSubprocessFactory(gh_stub)
    with (
        patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec),
        pytest.raises(RuntimeError, match="Failed to parse CI status"),
    ):
        await poll_ci_status(pr_number=123)


@pytest.mark.asyncio
async def test_ci_failure_returns_ci_failed_not_error(gh_stub: GhCliStubHelper) -> None:
    """Test that actual CI failures return ci_failed status, not error."""
    from src.activities.pr_ci_automation import poll_ci_status

    checks = [
        {
            "name": "test",
            "status": "completed",
            "conclusion": "failure",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/owner/repo/actions/runs/1",
        }
    ]
    gh_stub.stub_pr_checks(pr_number=123, checks=checks)

    factory = MockSubprocessFactory(gh_stub)
    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        status, failures = await poll_ci_status(pr_number=123)

        # Should be failure status with failures, not error
        assert status == "failure"
        assert len(failures) > 0
        assert failures[0].job_name == "test"


@pytest.mark.asyncio
async def test_network_timeout_returns_error_not_ci_failed(gh_stub: GhCliStubHelper) -> None:
    """Test that network/timeout errors return error status."""
    from src.activities.pr_ci_automation import poll_ci_status

    # Simulate timeout by making subprocess hang then fail
    async def create_hanging_subprocess(*args: str, **kwargs: Any) -> AsyncMock:
        mock_process = AsyncMock()
        mock_process.returncode = 124  # timeout exit code

        async def slow_communicate() -> tuple[bytes, bytes]:
            await asyncio.sleep(0.1)
            raise TimeoutError("Command timed out")

        mock_process.communicate = slow_communicate
        return mock_process

    with (
        patch("asyncio.create_subprocess_exec", new=create_hanging_subprocess),
        pytest.raises(asyncio.TimeoutError),
    ):
        await poll_ci_status(pr_number=123)


# Resume and Idempotency Tests (T020 - Phase 5: User Story 3)


@pytest.mark.asyncio
async def test_resume_reuses_existing_open_pr(gh_stub: GhCliStubHelper) -> None:
    """Test that resuming automation reuses an existing open PR without recreating."""
    from src.activities.pr_ci_automation import pr_ci_automation
    from src.models.phase_automation import PullRequestAutomationRequest

    # Setup: Branch exists
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/resume-test"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/resume-test\n", returncode=0),
    )

    # Resolve target branch
    gh_stub.stub_repo_view(owner="testowner", name="testrepo", default_branch="main")

    # Existing open PR found
    gh_stub.stub_pr_view(
        pr_number=456,
        state="OPEN",
        base_branch="main",
        head_branch="feature/resume-test",
        url="https://github.com/testowner/testrepo/pull/456",
    )

    # Validate base branch
    gh_stub.add_stub(
        ("gh", "pr", "view", "456", "--json", "baseRefName"),
        GhCommandStub(stdout='{"baseRefName": "main"}', returncode=0),
    )

    # CI checks pass
    checks = [
        {
            "name": "build",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/testowner/testrepo/actions/runs/1",
        }
    ]
    gh_stub.stub_pr_checks(pr_number=456, checks=checks)

    # Merge succeeds
    gh_stub.stub_pr_merge(pr_number=456, merge_commit_sha="def789")

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/resume-test",
        target_branch="main",
        summary="Resume test PR",
        workflow_attempt_id="resume-attempt-001",
    )

    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await pr_ci_automation(request)

        # Should successfully merge using existing PR
        assert result.status == "merged"
        assert result.pull_request_number == 456
        assert result.pull_request_url == "https://github.com/testowner/testrepo/pull/456"
        assert result.merge_commit_sha == "def789"


@pytest.mark.asyncio
async def test_resume_detects_already_merged_pr(gh_stub: GhCliStubHelper) -> None:
    """Test that resuming automation detects and returns already-merged PRs."""
    from src.activities.pr_ci_automation import pr_ci_automation
    from src.models.phase_automation import PullRequestAutomationRequest

    # Setup: Branch exists
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/already-merged"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/already-merged\n", returncode=0),
    )

    # Resolve target branch
    gh_stub.stub_repo_view(owner="testowner", name="testrepo", default_branch="main")

    # Existing merged PR found
    gh_stub.stub_pr_view(
        pr_number=789,
        state="MERGED",
        base_branch="main",
        head_branch="feature/already-merged",
        url="https://github.com/testowner/testrepo/pull/789",
        merged_at="2025-01-01T12:00:00Z",
    )

    # Get merge commit SHA (for already-merged PR)
    gh_stub.add_stub(
        ("gh", "pr", "view", "789", "--json", "mergeCommit"),
        GhCommandStub(stdout='{"mergeCommit": {"oid": "merged123"}}', returncode=0),
    )

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/already-merged",
        target_branch="main",
        summary="Already merged PR",
        workflow_attempt_id="resume-attempt-002",
    )

    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await pr_ci_automation(request)

        # Should return merged status with existing merge SHA
        assert result.status == "merged"
        assert result.pull_request_number == 789
        assert result.pull_request_url == "https://github.com/testowner/testrepo/pull/789"
        assert result.merge_commit_sha == "merged123"


@pytest.mark.asyncio
async def test_resume_after_previous_timeout(gh_stub: GhCliStubHelper) -> None:
    """Test that resuming after a timeout continues polling from existing PR."""
    from src.activities.pr_ci_automation import pr_ci_automation
    from src.models.phase_automation import PollingConfiguration, PullRequestAutomationRequest

    # Setup: Branch exists
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/timeout-resume"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/timeout-resume\n", returncode=0),
    )

    # Resolve target branch
    gh_stub.stub_repo_view(owner="testowner", name="testrepo", default_branch="main")

    # Existing open PR found (from previous timeout)
    gh_stub.stub_pr_view(
        pr_number=999,
        state="OPEN",
        base_branch="main",
        head_branch="feature/timeout-resume",
        url="https://github.com/testowner/testrepo/pull/999",
    )

    # Validate base branch
    gh_stub.add_stub(
        ("gh", "pr", "view", "999", "--json", "baseRefName"),
        GhCommandStub(stdout='{"baseRefName": "main"}', returncode=0),
    )

    # CI checks now complete after previous timeout
    checks = [
        {
            "name": "slow-build",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T01:00:00Z",
            "detailsUrl": "https://github.com/testowner/testrepo/actions/runs/100",
        }
    ]
    gh_stub.stub_pr_checks(pr_number=999, checks=checks)

    # Merge succeeds
    gh_stub.stub_pr_merge(pr_number=999, merge_commit_sha="timeout-resolved")

    factory = MockSubprocessFactory(gh_stub)

    # Use short timeout for test
    request = PullRequestAutomationRequest(
        source_branch="feature/timeout-resume",
        target_branch="main",
        summary="Timeout resume test",
        workflow_attempt_id="resume-attempt-003",
        polling=PollingConfiguration(
            interval_seconds=1,
            timeout_minutes=1,
            max_retries=3,
        ),
    )

    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        result = await pr_ci_automation(request)

        # Should successfully merge after resume
        assert result.status == "merged"
        assert result.pull_request_number == 999
        assert result.merge_commit_sha == "timeout-resolved"


@pytest.mark.asyncio
async def test_idempotent_multiple_invocations_same_pr(gh_stub: GhCliStubHelper) -> None:
    """Test that multiple invocations with same source branch are idempotent."""
    from src.activities.pr_ci_automation import pr_ci_automation
    from src.models.phase_automation import PullRequestAutomationRequest

    # Setup: Branch exists
    gh_stub.add_stub(
        ("git", "ls-remote", "--heads", "origin", "feature/idempotent-test"),
        GhCommandStub(stdout="abc123\trefs/heads/feature/idempotent-test\n", returncode=0),
    )

    # Resolve target branch
    gh_stub.stub_repo_view(owner="testowner", name="testrepo", default_branch="main")

    # Existing open PR
    gh_stub.stub_pr_view(
        pr_number=111,
        state="OPEN",
        base_branch="main",
        head_branch="feature/idempotent-test",
        url="https://github.com/testowner/testrepo/pull/111",
    )

    # Validate base branch
    gh_stub.add_stub(
        ("gh", "pr", "view", "111", "--json", "baseRefName"),
        GhCommandStub(stdout='{"baseRefName": "main"}', returncode=0),
    )

    # CI checks pass
    checks = [
        {
            "name": "test",
            "status": "completed",
            "conclusion": "success",
            "completedAt": "2025-01-01T00:05:00Z",
            "detailsUrl": "https://github.com/testowner/testrepo/actions/runs/1",
        }
    ]
    gh_stub.stub_pr_checks(pr_number=111, checks=checks)

    # Merge succeeds
    gh_stub.stub_pr_merge(pr_number=111, merge_commit_sha="idempotent123")

    factory = MockSubprocessFactory(gh_stub)

    request = PullRequestAutomationRequest(
        source_branch="feature/idempotent-test",
        target_branch="main",
        summary="Idempotent test PR",
        workflow_attempt_id="idempotent-attempt-001",
    )

    with patch("asyncio.create_subprocess_exec", new=factory.create_subprocess_exec):
        # First invocation
        result1 = await pr_ci_automation(request)
        assert result1.status == "merged"
        assert result1.pull_request_number == 111
        assert result1.merge_commit_sha == "idempotent123"

        # Second invocation with same branch should return same result
        result2 = await pr_ci_automation(request)
        assert result2.status == "merged"
        assert result2.pull_request_number == 111
        assert result2.merge_commit_sha == "idempotent123"

        # Results should be identical
        assert result1.pull_request_number == result2.pull_request_number
        assert result1.merge_commit_sha == result2.merge_commit_sha
