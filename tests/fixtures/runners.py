"""Mock fixtures for Maverick runners.

This module provides mock implementations of runner components for testing
workflows without real command execution, git operations, or GitHub API calls.

Provides:
- mock_git_runner: Mock GitRunner with configurable results
- mock_validation_runner: Mock ValidationRunner with configurable validation results
- mock_github_runner: Mock GitHubCLIRunner with configurable GitHub operations
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from maverick.runners.git import GitResult
from maverick.runners.models import (
    GitHubIssue,
    PullRequest,
    StageResult,
    ValidationOutput,
)


@pytest.fixture
def mock_git_runner() -> MagicMock:
    """Fixture providing a mock GitRunner instance.

    Returns:
        MagicMock configured with AsyncMock methods that return GitResult instances.
        All operations default to successful execution.

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_workflow(mock_git_runner):
        ...     # Default: all operations succeed
        ...     result = await mock_git_runner.create_branch("feature-x")
        ...     assert result.success
        ...
        ...     # Configure specific behavior
        ...     mock_git_runner.commit.return_value = GitResult(
        ...         success=False, output="", error="Nothing to commit", duration_ms=50
        ...     )
        ...     result = await mock_git_runner.commit("test commit")
        ...     assert not result.success
    """
    runner = MagicMock()

    # Configure async methods with default successful results
    runner.create_branch = AsyncMock(
        return_value=GitResult(
            success=True,
            output="Switched to a new branch 'test-branch'",
            error=None,
            duration_ms=100,
        )
    )

    runner.create_branch_with_fallback = AsyncMock(
        return_value=GitResult(
            success=True,
            output="Switched to a new branch 'test-branch'",
            error=None,
            duration_ms=100,
        )
    )

    runner.checkout = AsyncMock(
        return_value=GitResult(
            success=True,
            output="Switched to branch 'main'",
            error=None,
            duration_ms=50,
        )
    )

    runner.commit = AsyncMock(
        return_value=GitResult(
            success=True,
            output="[main abc1234] test commit",
            error=None,
            duration_ms=150,
        )
    )

    runner.push = AsyncMock(
        return_value=GitResult(
            success=True,
            output="To github.com:test/repo.git\n   abc1234..def5678  main -> main",
            error=None,
            duration_ms=1000,
        )
    )

    runner.add = AsyncMock(
        return_value=GitResult(
            success=True,
            output="",
            error=None,
            duration_ms=50,
        )
    )

    runner.status = AsyncMock(
        return_value=GitResult(
            success=True,
            output=" M src/file.py\n?? tests/test_file.py",
            error=None,
            duration_ms=50,
        )
    )

    runner.diff = AsyncMock(
        return_value="diff --git a/src/file.py b/src/file.py\n"
        "index abc1234..def5678 100644\n"
        "--- a/src/file.py\n"
        "+++ b/src/file.py\n"
        "@@ -10,3 +10,6 @@ def foo():\n"
        "     pass\n"
        "+\n"
        "+def bar():\n"
        "+    pass\n"
    )

    # Set cwd property
    runner.cwd = None

    return runner


@pytest.fixture
def mock_validation_runner() -> MagicMock:
    """Fixture providing a mock ValidationRunner instance.

    Returns:
        MagicMock configured with AsyncMock.run() that returns ValidationOutput.
        Default behavior: all stages pass successfully.

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_validation(mock_validation_runner):
        ...     # Default: validation passes
        ...     result = await mock_validation_runner.run()
        ...     assert result.success
        ...
        ...     # Configure specific behavior
        ...     mock_validation_runner.run.return_value = ValidationOutput(
        ...         success=False,
        ...         stages=(
        ...             StageResult(
        ...                 stage_name="format",
        ...                 passed=False,
        ...                 output="formatting errors found",
        ...                 duration_ms=200,
        ...                 fix_attempts=1,
        ...                 errors=(),
        ...             ),
        ...         ),
        ...         total_duration_ms=500,
        ...     )
        ...     result = await mock_validation_runner.run()
        ...     assert not result.success
    """
    runner = MagicMock()

    # Configure default successful validation
    runner.run = AsyncMock(
        return_value=ValidationOutput(
            success=True,
            stages=(
                StageResult(
                    stage_name="format",
                    passed=True,
                    output="All files formatted correctly",
                    duration_ms=250,
                    fix_attempts=0,
                    errors=(),
                ),
                StageResult(
                    stage_name="lint",
                    passed=True,
                    output="No linting issues found",
                    duration_ms=500,
                    fix_attempts=0,
                    errors=(),
                ),
                StageResult(
                    stage_name="test",
                    passed=True,
                    output="All tests passed",
                    duration_ms=2000,
                    fix_attempts=0,
                    errors=(),
                ),
            ),
            total_duration_ms=2750,
        )
    )

    return runner


@pytest.fixture
def mock_github_runner() -> MagicMock:
    """Fixture providing a mock GitHubCLIRunner instance.

    Returns:
        MagicMock configured with AsyncMock methods for GitHub operations.
        Default behavior: successful PR creation and issue retrieval.

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_pr_creation(mock_github_runner):
        ...     # Default: PR created successfully
        ...     pr = await mock_github_runner.create_pr(
        ...         title="Test PR",
        ...         body="Description",
        ...     )
        ...     assert pr.number == 42
        ...
        ...     # Configure specific behavior
        ...     mock_github_runner.list_issues.return_value = [
        ...         GitHubIssue(
        ...             number=123,
        ...             title="Bug: Something broke",
        ...             body="Details here",
        ...             labels=("bug", "priority:high"),
        ...             state="open",
        ...             assignees=(),
        ...             url="https://github.com/test/repo/issues/123",
        ...         )
        ...     ]
        ...     issues = await mock_github_runner.list_issues(label="bug")
        ...     assert len(issues) == 1
    """
    runner = MagicMock()

    # Configure create_pr
    runner.create_pr = AsyncMock(
        return_value=PullRequest(
            number=42,
            title="Test PR",
            body="PR description",
            state="open",
            url="https://github.com/test/repo/pull/42",
            head_branch="feature-branch",
            base_branch="main",
            mergeable=True,
            draft=False,
        )
    )

    # Configure update_pr
    runner.update_pr = AsyncMock(
        return_value=PullRequest(
            number=42,
            title="Updated Test PR",
            body="Updated PR description",
            state="open",
            url="https://github.com/test/repo/pull/42",
            head_branch="feature-branch",
            base_branch="main",
            mergeable=True,
            draft=False,
        )
    )

    # Configure get_pr
    runner.get_pr = AsyncMock(
        return_value=PullRequest(
            number=42,
            title="Test PR",
            body="PR description",
            state="open",
            url="https://github.com/test/repo/pull/42",
            head_branch="feature-branch",
            base_branch="main",
            mergeable=True,
            draft=False,
        )
    )

    # Configure list_issues
    runner.list_issues = AsyncMock(
        return_value=[
            GitHubIssue(
                number=100,
                title="Example Issue 1",
                body="Issue description 1",
                labels=("bug", "good-first-issue"),
                state="open",
                assignees=(),
                url="https://github.com/test/repo/issues/100",
            ),
            GitHubIssue(
                number=101,
                title="Example Issue 2",
                body="Issue description 2",
                labels=("enhancement",),
                state="open",
                assignees=("test-user",),
                url="https://github.com/test/repo/issues/101",
            ),
        ]
    )

    # Configure get_issue
    runner.get_issue = AsyncMock(
        return_value=GitHubIssue(
            number=100,
            title="Example Issue",
            body="Issue description",
            labels=("bug",),
            state="open",
            assignees=(),
            url="https://github.com/test/repo/issues/100",
        )
    )

    # Configure close_issue
    runner.close_issue = AsyncMock(return_value=None)

    # Configure add_label
    runner.add_label = AsyncMock(return_value=None)

    # Configure remove_label
    runner.remove_label = AsyncMock(return_value=None)

    return runner
