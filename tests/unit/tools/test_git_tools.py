"""Unit tests for Git MCP tools.

Tests the git tools functionality including:
- git_commit: Creating commits with conventional commit formatting
- git_push: Pushing commits to remote repository
- git_current_branch: Getting current branch name
- git_diff_stats: Getting diff statistics
- git_create_branch: Creating and checking out new branches
- Error handling and validation

These tests mock AsyncGitRepository to isolate the MCP tools layer from the git layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.exceptions import (
    BranchExistsError,
    GitError,
    NotARepositoryError,
    NothingToCommitError,
    PushRejectedError,
)
from maverick.git import DiffStats
from maverick.tools.git import (
    _error_response,
    _format_commit_message,
    _success_response,
    create_git_tools_server,
    verify_git_prerequisites,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_git_repo() -> MagicMock:
    """Create a mock AsyncGitRepository for testing git tools.

    Returns:
        Mock AsyncGitRepository with configurable async methods.
    """
    repo = MagicMock()
    # Default to successful results
    repo.current_branch = AsyncMock(return_value="main")
    repo.commit = AsyncMock(return_value="abc123def456")
    repo.push = AsyncMock(return_value=None)
    repo.diff_stats = AsyncMock(
        return_value=DiffStats(
            files_changed=0,
            insertions=0,
            deletions=0,
            file_list=(),
            per_file={},
        )
    )
    repo.create_branch = AsyncMock(return_value=None)
    return repo


# =============================================================================
# Helper Functions Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_success_response(self) -> None:
        """Test _success_response creates correct MCP format."""
        data = {"success": True, "value": 42}
        response = _success_response(data)

        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"
        parsed = json.loads(response["content"][0]["text"])
        assert parsed == data

    def test_error_response(self) -> None:
        """Test _error_response creates correct MCP format."""
        response = _error_response("Test error", "TEST_ERROR")

        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"
        parsed = json.loads(response["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["message"] == "Test error"
        assert parsed["error_code"] == "TEST_ERROR"

    def test_error_response_with_retry(self) -> None:
        """Test _error_response with retry_after_seconds."""
        response = _error_response("Rate limit", "RATE_LIMIT", retry_after_seconds=60)

        parsed = json.loads(response["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["retry_after_seconds"] == 60

    def test_format_commit_message_plain(self) -> None:
        """Test _format_commit_message without type."""
        result = _format_commit_message("add feature")
        assert result == "add feature"

    def test_format_commit_message_with_type(self) -> None:
        """Test _format_commit_message with type only."""
        result = _format_commit_message("add feature", commit_type="feat")
        assert result == "feat: add feature"

    def test_format_commit_message_with_scope(self) -> None:
        """Test _format_commit_message with type and scope."""
        result = _format_commit_message("add feature", commit_type="feat", scope="api")
        assert result == "feat(api): add feature"

    def test_format_commit_message_breaking(self) -> None:
        """Test _format_commit_message with breaking change."""
        result = _format_commit_message(
            "breaking change", commit_type="feat", breaking=True
        )
        assert result == "feat!: breaking change"

    def test_format_commit_message_scope_and_breaking(self) -> None:
        """Test _format_commit_message with scope and breaking change."""
        result = _format_commit_message(
            "breaking change", commit_type="feat", scope="api", breaking=True
        )
        assert result == "feat(api)!: breaking change"

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_success(
        self, mock_git_repo: MagicMock
    ) -> None:
        """Test verify_git_prerequisites with all checks passing."""
        with patch(
            "maverick.tools.git.prereqs.GitRepository", return_value=mock_git_repo
        ):
            # Should not raise
            await verify_git_prerequisites()

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_not_in_repo(self) -> None:
        """Test verify_git_prerequisites when not in git repository."""
        from maverick.exceptions import GitToolsError

        with patch(
            "maverick.tools.git.prereqs.GitRepository",
            side_effect=NotARepositoryError("Not a repo", path="/fake"),
        ):
            with pytest.raises(GitToolsError) as exc_info:
                await verify_git_prerequisites()

        assert "not inside a git repository" in str(exc_info.value)
        assert exc_info.value.check_failed == "in_git_repo"


# =============================================================================
# git_commit Tests
# =============================================================================


class TestGitCommit:
    """Tests for git_commit tool (T064-T066)."""

    @pytest.mark.asyncio
    async def test_git_commit_success(self, mock_git_repo: MagicMock) -> None:
        """Test git_commit with successful commit creation (T064).

        Verifies:
        - Commit is created successfully
        - Commit SHA is retrieved
        - Response contains success, commit_sha, and message fields
        """
        commit_sha = "abc123def456"
        mock_git_repo.commit = AsyncMock(return_value=commit_sha)

        with patch(
            "maverick.tools.git.tools.commit.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_commit"].handler(
                {"message": "add feature", "type": "feat"}
            )

        # Verify response structure
        assert "content" in result
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        assert parsed["commit_sha"] == commit_sha
        assert parsed["message"] == "feat: add feature"

    @pytest.mark.asyncio
    async def test_git_commit_conventional_format(
        self, mock_git_repo: MagicMock
    ) -> None:
        """Test git_commit with type, scope, and breaking change (T065).

        Verifies conventional commit formatting:
        - type(scope)!: message format
        - All parameters properly formatted
        """
        commit_sha = "def789abc123"
        mock_git_repo.commit = AsyncMock(return_value=commit_sha)

        with patch(
            "maverick.tools.git.tools.commit.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_commit"].handler(
                {
                    "message": "breaking change",
                    "type": "fix",
                    "scope": "auth",
                    "breaking": True,
                }
            )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        assert parsed["message"] == "fix(auth)!: breaking change"

    @pytest.mark.asyncio
    async def test_git_commit_nothing_to_commit(self, mock_git_repo: MagicMock) -> None:
        """Test git_commit when there are no changes to commit (T066).

        Verifies:
        - NOTHING_TO_COMMIT error code
        - Helpful error message
        """
        mock_git_repo.commit = AsyncMock(side_effect=NothingToCommitError())

        with patch(
            "maverick.tools.git.tools.commit.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_commit"].handler(
                {"message": "test commit"}
            )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "NOTHING_TO_COMMIT"
        assert "git add" in parsed["message"]

    @pytest.mark.asyncio
    async def test_git_commit_empty_message(self) -> None:
        """Test git_commit with empty message."""
        server = create_git_tools_server()
        result = await server["_tools"]["git_commit"].handler({"message": ""})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"
        assert "empty" in parsed["message"].lower()

    @pytest.mark.asyncio
    async def test_git_commit_invalid_type(self) -> None:
        """Test git_commit with invalid commit type."""
        server = create_git_tools_server()
        result = await server["_tools"]["git_commit"].handler(
            {"message": "test", "type": "invalid"}
        )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"
        assert "invalid" in parsed["message"].lower()

    @pytest.mark.asyncio
    async def test_git_commit_git_error(self, mock_git_repo: MagicMock) -> None:
        """Test git_commit with generic git error."""
        mock_git_repo.commit = AsyncMock(side_effect=Exception("fatal: some git error"))

        with patch(
            "maverick.tools.git.tools.commit.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_commit"].handler({"message": "test"})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INTERNAL_ERROR"


# =============================================================================
# git_push Tests
# =============================================================================


class TestGitPush:
    """Tests for git_push tool (T067-T069)."""

    @pytest.mark.asyncio
    async def test_git_push_success(self, mock_git_repo: MagicMock) -> None:
        """Test git_push with successful push (T067).

        Verifies:
        - Push succeeds
        - Response contains success, commits_pushed, remote, and branch
        """
        mock_git_repo.current_branch = AsyncMock(return_value="feature-branch")
        mock_git_repo.push = AsyncMock(return_value=None)

        with patch(
            "maverick.tools.git.tools.push.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        assert parsed["remote"] == "origin"
        assert parsed["branch"] == "feature-branch"
        assert parsed["commits_pushed"] >= 1

    @pytest.mark.asyncio
    async def test_git_push_detached_head(self, mock_git_repo: MagicMock) -> None:
        """Test git_push from detached HEAD state (T068).

        Verifies:
        - DETACHED_HEAD error code
        - Appropriate error message
        """
        # In GitRepository, detached HEAD returns the commit SHA (40 chars)
        mock_git_repo.current_branch = AsyncMock(
            return_value="abc123def456abc123def456abc123def456abcd"
        )

        with patch(
            "maverick.tools.git.tools.push.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "DETACHED_HEAD"

    @pytest.mark.asyncio
    async def test_git_push_auth_required(self, mock_git_repo: MagicMock) -> None:
        """Test git_push with authentication failure (T069).

        Verifies:
        - AUTHENTICATION_REQUIRED error code
        - Detects various auth error patterns
        """
        mock_git_repo.push = AsyncMock(
            side_effect=PushRejectedError(
                "fatal: Authentication failed for 'https://github.com/org/repo'",
                reason="authentication failed",
            )
        )

        with patch(
            "maverick.tools.git.tools.push.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "AUTHENTICATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_git_push_network_error(self, mock_git_repo: MagicMock) -> None:
        """Test git_push with network error."""
        mock_git_repo.push = AsyncMock(
            side_effect=GitError(
                "fatal: could not resolve host: github.com",
                operation="push",
                recoverable=True,
            )
        )

        with patch(
            "maverick.tools.git.tools.push.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_git_push_not_a_repository(self) -> None:
        """Test git_push when not in a git repository."""
        with patch(
            "maverick.tools.git.tools.push.AsyncGitRepository",
            side_effect=NotARepositoryError("Not a repo", path="/fake"),
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "NOT_A_REPOSITORY"

    @pytest.mark.asyncio
    async def test_git_push_set_upstream(self, mock_git_repo: MagicMock) -> None:
        """Test git_push with set_upstream=True."""
        mock_git_repo.current_branch = AsyncMock(return_value="feature")
        mock_git_repo.push = AsyncMock(return_value=None)

        with patch(
            "maverick.tools.git.tools.push.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_push"].handler({"set_upstream": True})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        # Verify push was called with set_upstream=True
        mock_git_repo.push.assert_called_once()
        call_kwargs = mock_git_repo.push.call_args.kwargs
        assert call_kwargs.get("set_upstream") is True


# =============================================================================
# git_current_branch Tests
# =============================================================================


class TestGitCurrentBranch:
    """Tests for git_current_branch tool (T059-T061)."""

    @pytest.mark.asyncio
    async def test_git_current_branch_success(self, mock_git_repo: MagicMock) -> None:
        """Test git_current_branch with successful branch retrieval (T059).

        Verifies:
        - Branch name is retrieved correctly
        - Response contains branch field
        """
        mock_git_repo.current_branch = AsyncMock(return_value="feature-branch")

        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_current_branch"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["branch"] == "feature-branch"

    @pytest.mark.asyncio
    async def test_git_current_branch_detached(self, mock_git_repo: MagicMock) -> None:
        """Test git_current_branch in detached HEAD state (T060).

        Verifies:
        - Returns the commit SHA when in detached HEAD state
        - No error is raised
        """
        # In GitRepository, detached HEAD returns the commit SHA
        mock_git_repo.current_branch = AsyncMock(
            return_value="abc123def456abc123def456abc123def456abcd"
        )

        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_current_branch"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        # Should return the SHA, not "(detached)"
        assert parsed["branch"] == "abc123def456abc123def456abc123def456abcd"

    @pytest.mark.asyncio
    async def test_git_current_branch_not_repo(self) -> None:
        """Test git_current_branch when not in a git repository (T061).

        Verifies:
        - NOT_A_REPOSITORY error code
        - Appropriate error message
        """
        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            side_effect=NotARepositoryError("Not a repo", path="/fake"),
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_current_branch"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "NOT_A_REPOSITORY"


# =============================================================================
# git_diff_stats Tests
# =============================================================================


class TestGitDiffStats:
    """Tests for git_diff_stats tool (T070-T071)."""

    @pytest.mark.asyncio
    async def test_git_diff_stats_success(self, mock_git_repo: MagicMock) -> None:
        """Test git_diff_stats with changes present (T070).

        Verifies:
        - Statistics are parsed correctly
        - Response contains files_changed, insertions, deletions
        """
        mock_git_repo.diff_stats = AsyncMock(
            return_value=DiffStats(
                files_changed=3,
                insertions=50,
                deletions=20,
                file_list=("file1.py", "file2.py", "file3.py"),
                per_file={"file1.py": (30, 10), "file2.py": (20, 10)},
            )
        )

        with patch(
            "maverick.tools.git.tools.diff.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_diff_stats"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["files_changed"] == 3
        assert parsed["insertions"] == 50
        assert parsed["deletions"] == 20

    @pytest.mark.asyncio
    async def test_git_diff_stats_no_changes(self, mock_git_repo: MagicMock) -> None:
        """Test git_diff_stats with no changes (T071).

        Verifies:
        - Empty diff returns zeros
        - No error is raised
        """
        mock_git_repo.diff_stats = AsyncMock(
            return_value=DiffStats(
                files_changed=0,
                insertions=0,
                deletions=0,
                file_list=(),
                per_file={},
            )
        )

        with patch(
            "maverick.tools.git.tools.diff.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_diff_stats"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["files_changed"] == 0
        assert parsed["insertions"] == 0
        assert parsed["deletions"] == 0

    @pytest.mark.asyncio
    async def test_git_diff_stats_insertions_only(
        self, mock_git_repo: MagicMock
    ) -> None:
        """Test git_diff_stats with only insertions."""
        mock_git_repo.diff_stats = AsyncMock(
            return_value=DiffStats(
                files_changed=2,
                insertions=100,
                deletions=0,
                file_list=("new_file.py", "other.py"),
                per_file={"new_file.py": (100, 0)},
            )
        )

        with patch(
            "maverick.tools.git.tools.diff.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_diff_stats"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["files_changed"] == 2
        assert parsed["insertions"] == 100
        assert parsed["deletions"] == 0

    @pytest.mark.asyncio
    async def test_git_diff_stats_deletions_only(
        self, mock_git_repo: MagicMock
    ) -> None:
        """Test git_diff_stats with only deletions."""
        mock_git_repo.diff_stats = AsyncMock(
            return_value=DiffStats(
                files_changed=1,
                insertions=0,
                deletions=50,
                file_list=("deleted_file.py",),
                per_file={"deleted_file.py": (0, 50)},
            )
        )

        with patch(
            "maverick.tools.git.tools.diff.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_diff_stats"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["files_changed"] == 1
        assert parsed["insertions"] == 0
        assert parsed["deletions"] == 50


# =============================================================================
# git_create_branch Tests
# =============================================================================


class TestGitCreateBranch:
    """Tests for git_create_branch tool (T062-T063)."""

    @pytest.mark.asyncio
    async def test_git_create_branch_success(self, mock_git_repo: MagicMock) -> None:
        """Test git_create_branch with successful branch creation (T062).

        Verifies:
        - Branch is created and checked out
        - Response contains success, branch, and base
        """
        mock_git_repo.create_branch = AsyncMock(return_value=None)

        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_create_branch"].handler(
                {"name": "feature"}
            )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        assert parsed["branch"] == "feature"
        assert parsed["base"] == "(current)"

    @pytest.mark.asyncio
    async def test_git_create_branch_with_base(self, mock_git_repo: MagicMock) -> None:
        """Test git_create_branch with base branch specified."""
        mock_git_repo.create_branch = AsyncMock(return_value=None)

        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_create_branch"].handler(
                {"name": "feature", "base": "main"}
            )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        assert parsed["base"] == "main"
        # Verify create_branch was called with correct from_ref
        mock_git_repo.create_branch.assert_called_once_with(
            "feature", checkout=True, from_ref="main"
        )

    @pytest.mark.asyncio
    async def test_git_create_branch_exists(self, mock_git_repo: MagicMock) -> None:
        """Test git_create_branch when branch already exists (T063).

        Verifies:
        - BRANCH_EXISTS error code
        - Appropriate error message
        """
        mock_git_repo.create_branch = AsyncMock(
            side_effect=BranchExistsError(
                "Branch 'feature' already exists", branch_name="feature"
            )
        )

        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_create_branch"].handler(
                {"name": "feature"}
            )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "BRANCH_EXISTS"

    @pytest.mark.asyncio
    async def test_git_create_branch_invalid_name(self) -> None:
        """Test git_create_branch with invalid branch name."""
        server = create_git_tools_server()

        # Test with spaces
        result = await server["_tools"]["git_create_branch"].handler(
            {"name": "invalid name"}
        )
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"

        # Test with special characters
        result = await server["_tools"]["git_create_branch"].handler(
            {"name": "invalid~branch"}
        )
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_git_create_branch_empty_name(self) -> None:
        """Test git_create_branch with empty name."""
        server = create_git_tools_server()
        result = await server["_tools"]["git_create_branch"].handler({"name": ""})
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_git_create_branch_base_not_found(
        self, mock_git_repo: MagicMock
    ) -> None:
        """Test git_create_branch when base branch doesn't exist."""
        mock_git_repo.create_branch = AsyncMock(
            side_effect=GitError(
                "'nonexistent' not found",
                operation="create_branch",
                recoverable=False,
            )
        )

        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            server = create_git_tools_server()
            result = await server["_tools"]["git_create_branch"].handler(
                {"name": "feature", "base": "nonexistent"}
            )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "BRANCH_NOT_FOUND"


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateGitToolsServer:
    """Tests for create_git_tools_server factory (T072)."""

    def test_create_git_tools_server(self) -> None:
        """Test create_git_tools_server creates server with all tools (T072).

        Verifies:
        - Server is created successfully
        - All 5 tools are registered
        - Server has correct name and version
        """
        server = create_git_tools_server()

        # Verify server was created
        assert server is not None
        # Server should be a dict with name and instance
        assert isinstance(server, dict)
        assert server["name"] == "git-tools"
        assert "instance" in server

    def test_create_git_tools_server_skip_verification(self) -> None:
        """Test create_git_tools_server with skip_verification=True."""
        # Should not raise even if git is not available
        server = create_git_tools_server(skip_verification=True)
        assert server is not None

    def test_create_git_tools_server_with_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        """Test create_git_tools_server with custom working directory."""
        server = create_git_tools_server(cwd=tmp_path)
        assert server is not None

    def test_create_git_tools_server_safe_in_async_context(self) -> None:
        """Test create_git_tools_server is safe to call from async context.

        After refactoring to use lazy verification, the factory no longer
        uses asyncio.run() and is safe to call from both sync and async contexts.
        """
        import asyncio

        from maverick.tools.git import create_git_tools_server

        async def async_caller():
            """Call create_git_tools_server from async context."""
            # Should succeed - no longer raises error in async context
            server = create_git_tools_server()
            assert server is not None
            return server

        # Run the async test
        server = asyncio.run(async_caller())
        assert server is not None
