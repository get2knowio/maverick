"""Unit tests for gather_local_review_context action."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.review import gather_local_review_context


def _make_mock_repo(
    *,
    current_branch: str = "feature/test",
    uncommitted_diff: str = "",
    branch_diff: str = "",
    staged: tuple[str, ...] = (),
    unstaged: tuple[str, ...] = (),
    untracked: tuple[str, ...] = (),
    branch_changed: list[str] | None = None,
    commit_messages: list[str] | None = None,
) -> AsyncMock:
    """Create a mock AsyncGitRepository."""
    mock = AsyncMock()
    mock.current_branch.return_value = current_branch

    async def diff_side_effect(
        base: str = "HEAD",
        head: str | None = None,
        staged: bool = False,
    ) -> str:
        if base == "HEAD":
            return uncommitted_diff
        return branch_diff

    mock.diff.side_effect = diff_side_effect
    mock.get_changed_files.return_value = branch_changed or []
    mock.commit_messages_since.return_value = commit_messages or []

    # status returns a GitStatus-like object
    status_mock = AsyncMock()
    status_mock.staged = staged
    status_mock.unstaged = unstaged
    status_mock.untracked = untracked
    mock.status.return_value = status_mock

    return mock


class TestGatherLocalReviewContext:
    """Tests for gather_local_review_context action."""

    @pytest.mark.asyncio
    async def test_gathers_context_with_combined_diff(self) -> None:
        mock_repo = _make_mock_repo(
            uncommitted_diff="diff --git a/new.py b/new.py\n+new line",
            branch_diff="diff --git a/old.py b/old.py\n+old line",
            staged=("new.py",),
            branch_changed=["old.py"],
        )

        with patch(
            "maverick.library.actions.review.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await gather_local_review_context(base_branch="main")

        assert result.error is None
        assert "new.py" in result.changed_files
        assert "old.py" in result.changed_files
        assert "new line" in result.diff
        assert "old line" in result.diff

    @pytest.mark.asyncio
    async def test_empty_working_tree(self) -> None:
        mock_repo = _make_mock_repo()

        with patch(
            "maverick.library.actions.review.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await gather_local_review_context()

        assert result.error is None
        assert result.changed_files == ()
        assert result.diff == ""

    @pytest.mark.asyncio
    async def test_pr_metadata_is_empty(self) -> None:
        """Local context should have no PR metadata."""
        mock_repo = _make_mock_repo()

        with patch(
            "maverick.library.actions.review.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await gather_local_review_context()

        assert result.pr_metadata.number is None
        assert result.pr_metadata.title is None
        assert result.pr_metadata.base_branch == "main"

    @pytest.mark.asyncio
    async def test_exclude_patterns_applied(self) -> None:
        mock_repo = _make_mock_repo(
            branch_diff=(
                "diff --git a/src/app.py b/src/app.py\n+code\n"
                "diff --git a/specs/plan.md b/specs/plan.md\n+spec"
            ),
            branch_changed=["src/app.py", "specs/plan.md"],
        )

        with patch(
            "maverick.library.actions.review.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await gather_local_review_context()

        # Default exclude_patterns should filter out specs/**
        assert "src/app.py" in result.changed_files
        assert "specs/plan.md" not in result.changed_files

    @pytest.mark.asyncio
    async def test_includes_commit_messages(self) -> None:
        mock_repo = _make_mock_repo(
            commit_messages=["feat: add feature", "fix: bug fix"],
        )

        with patch(
            "maverick.library.actions.review.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await gather_local_review_context()

        assert result.commits == ("feat: add feature", "fix: bug fix")

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self) -> None:
        with patch(
            "maverick.library.actions.review.AsyncGitRepository",
            side_effect=RuntimeError("git not found"),
        ):
            result = await gather_local_review_context()

        assert result.error is not None
        assert "git not found" in result.error
        assert result.changed_files == ()
        assert result.diff == ""

    @pytest.mark.asyncio
    async def test_deduplicates_changed_files(self) -> None:
        """Files appearing in both status and branch diff are deduplicated."""
        mock_repo = _make_mock_repo(
            staged=("shared.py",),
            branch_changed=["shared.py", "other.py"],
        )

        with patch(
            "maverick.library.actions.review.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await gather_local_review_context(exclude_patterns=())

        # shared.py should appear only once
        assert result.changed_files.count("shared.py") == 1
        assert "other.py" in result.changed_files

    @pytest.mark.asyncio
    async def test_custom_exclude_patterns(self) -> None:
        mock_repo = _make_mock_repo(
            branch_changed=["src/app.py", "docs/readme.md"],
        )

        with patch(
            "maverick.library.actions.review.AsyncGitRepository",
            return_value=mock_repo,
        ):
            result = await gather_local_review_context(exclude_patterns=["docs/**"])

        assert "src/app.py" in result.changed_files
        assert "docs/readme.md" not in result.changed_files
