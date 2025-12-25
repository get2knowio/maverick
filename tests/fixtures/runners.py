"""Mock fixtures for Maverick runners.

This module provides mock implementations of runner components for testing
workflows without real command execution, git operations, or GitHub API calls.

Provides:
- mock_git_repo: Mock AsyncGitRepository with configurable results
- mock_validation_runner: Mock ValidationRunner with configurable validation results
- mock_github_runner: Mock GitHubCLIRunner with configurable GitHub operations
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from maverick.git import DiffStats, GitStatus
from maverick.runners.models import (
    GitHubIssue,
    PullRequest,
    StageResult,
    ValidationOutput,
)


@pytest.fixture
def mock_git_repo() -> MagicMock:
    """Fixture providing a mock AsyncGitRepository instance.

    Returns:
        MagicMock configured with AsyncMock methods matching AsyncGitRepository API.
        All operations default to successful execution.

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_workflow(mock_git_repo):
        ...     # Default: all operations succeed
        ...     await mock_git_repo.create_branch("feature-x")
        ...     sha = await mock_git_repo.commit("test commit")
        ...     assert sha == "abc1234def5678"
        ...
        ...     # Configure specific behavior
        ...     from maverick.exceptions import NothingToCommitError
        ...     mock_git_repo.commit.side_effect = NothingToCommitError()
    """
    repo = MagicMock()

    # Configure path property
    type(repo).path = PropertyMock(return_value=Path.cwd())

    # Configure async methods with default successful results
    repo.current_branch = AsyncMock(return_value="test-branch")

    repo.status = AsyncMock(
        return_value=GitStatus(
            staged=("src/file.py",),
            unstaged=(),
            untracked=("tests/test_file.py",),
            branch="test-branch",
            ahead=0,
            behind=0,
        )
    )

    repo.is_dirty = AsyncMock(return_value=True)

    repo.create_branch = AsyncMock(return_value=None)

    repo.create_branch_with_fallback = AsyncMock(return_value="test-branch")

    repo.checkout = AsyncMock(return_value=None)

    repo.get_head_sha = AsyncMock(return_value="abc1234def5678")

    repo.add = AsyncMock(return_value=None)

    repo.add_all = AsyncMock(return_value=None)

    repo.commit = AsyncMock(return_value="abc1234def5678")

    repo.push = AsyncMock(return_value=None)

    repo.pull = AsyncMock(return_value=None)

    repo.fetch = AsyncMock(return_value=None)

    repo.diff = AsyncMock(
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

    repo.diff_stats = AsyncMock(
        return_value=DiffStats(
            files_changed=1,
            insertions=3,
            deletions=0,
            file_list=("src/file.py",),
            per_file={"src/file.py": (3, 0)},
        )
    )

    repo.get_changed_files = AsyncMock(return_value=["src/file.py"])

    repo.stash = AsyncMock(return_value=True)

    repo.stash_pop = AsyncMock(return_value=None)

    repo.stash_list = AsyncMock(return_value=[])

    repo.stash_pop_by_message = AsyncMock(return_value=False)

    repo.get_remote_url = AsyncMock(return_value="https://github.com/test/repo.git")

    repo.get_repo_root = AsyncMock(return_value=Path.cwd())

    repo.commit_messages = AsyncMock(return_value=["Initial commit", "Add feature"])

    repo.commit_messages_since = AsyncMock(return_value=["Add feature"])

    return repo


# Alias for backward compatibility
mock_git_runner = mock_git_repo


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
