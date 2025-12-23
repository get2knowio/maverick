"""Unit tests for Git MCP tools.

Tests the git tools functionality including:
- git_commit: Creating commits with conventional commit formatting
- git_push: Pushing commits to remote repository
- git_current_branch: Getting current branch name
- git_diff_stats: Getting diff statistics
- git_create_branch: Creating and checking out new branches
- Error handling and validation
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.exceptions import GitToolsError
from maverick.tools.git import (
    _error_response,
    _format_commit_message,
    _run_git_command,
    _success_response,
    create_git_tools_server,
    verify_git_prerequisites,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_subprocess() -> MagicMock:
    """Create a mock subprocess for testing git commands (T058).

    Returns:
        Mock subprocess with configurable stdout, stderr, and returncode.
    """
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    return mock_proc


@pytest.fixture
def mock_create_subprocess_exec(mock_subprocess: MagicMock) -> AsyncMock:
    """Create a mock for asyncio.create_subprocess_exec (T058).

    Args:
        mock_subprocess: Mock subprocess to return.

    Returns:
        AsyncMock that returns the mock subprocess.
    """
    return AsyncMock(return_value=mock_subprocess)


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
        response = _error_response(
            "Rate limit", "RATE_LIMIT", retry_after_seconds=60)

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
        result = _format_commit_message(
            "add feature", commit_type="feat", scope="api")
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
    async def test_run_git_command_success(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test _run_git_command with successful execution."""
        mock_subprocess.communicate.return_value = (b"output\n", b"")
        mock_subprocess.returncode = 0

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            stdout, stderr, returncode = await _run_git_command("status")

        assert stdout == "output"
        assert stderr == ""
        assert returncode == 0
        mock_create_subprocess_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_git_command_with_stderr(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test _run_git_command with stderr output."""
        mock_subprocess.communicate.return_value = (b"", b"error output\n")
        mock_subprocess.returncode = 1

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            stdout, stderr, returncode = await _run_git_command("commit")

        assert stdout == ""
        assert stderr == "error output"
        assert returncode == 1

    @pytest.mark.asyncio
    async def test_run_git_command_timeout(
        self, mock_create_subprocess_exec: AsyncMock
    ) -> None:
        """Test _run_git_command with timeout."""
        # Mock communicate to raise TimeoutError
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_create_subprocess_exec.return_value = mock_proc

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            with pytest.raises(asyncio.TimeoutError):
                await _run_git_command("status", timeout=0.1)

        # Verify process was killed
        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_success(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test verify_git_prerequisites with all checks passing."""
        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            # Should not raise
            await verify_git_prerequisites()

        # Should be called twice: once for git --version, once for git rev-parse
        assert mock_create_subprocess_exec.call_count == 2

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_git_not_installed(
        self, mock_create_subprocess_exec: AsyncMock
    ) -> None:
        """Test verify_git_prerequisites when git is not installed."""
        mock_create_subprocess_exec.side_effect = FileNotFoundError

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            with pytest.raises(GitToolsError) as exc_info:
                await verify_git_prerequisites()

        assert "not installed" in str(exc_info.value)
        assert exc_info.value.check_failed == "git_installed"

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_not_in_repo(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test verify_git_prerequisites when not in git repository."""

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args:
                # rev-parse fails
                proc = MagicMock()
                proc.returncode = 1
                proc.communicate = AsyncMock(
                    return_value=(b"", b"fatal: not a git repository")
                )
                return proc
            # git --version succeeds
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
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
    async def test_git_commit_success(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_commit with successful commit creation (T064).

        Verifies:
        - Commit is created successfully
        - Commit SHA is retrieved
        - Response contains success, commit_sha, and message fields
        """
        # First call: git commit
        # Second call: git rev-parse HEAD
        commit_sha = "abc123def456"
        mock_subprocess.communicate.side_effect = [
            (b"[main abc123d] feat: add feature\n", b""),
            (f"{commit_sha}\n".encode(), b""),
        ]
        mock_subprocess.returncode = 0

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_commit"].handler(
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
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_commit with type, scope, and breaking change (T065).

        Verifies conventional commit formatting:
        - type(scope)!: message format
        - All parameters properly formatted
        """
        commit_sha = "def789abc123"
        mock_subprocess.communicate.side_effect = [
            (b"[main def789a] fix(auth)!: breaking change\n", b""),
            (f"{commit_sha}\n".encode(), b""),
        ]
        mock_subprocess.returncode = 0

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_commit"].handler(
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
    async def test_git_commit_nothing_to_commit(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_commit when there are no changes to commit (T066).

        Verifies:
        - NOTHING_TO_COMMIT error code
        - Helpful error message
        """
        mock_subprocess.communicate.return_value = (
            b"",
            b"nothing to commit, working tree clean",
        )
        mock_subprocess.returncode = 1

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_commit"].handler(
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
        result = await server["tools"]["git_commit"].handler({"message": ""})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"
        assert "empty" in parsed["message"].lower()

    @pytest.mark.asyncio
    async def test_git_commit_invalid_type(self) -> None:
        """Test git_commit with invalid commit type."""
        server = create_git_tools_server()
        result = await server["tools"]["git_commit"].handler(
            {"message": "test", "type": "invalid"}
        )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"
        assert "invalid" in parsed["message"].lower()

    @pytest.mark.asyncio
    async def test_git_commit_timeout(
        self, mock_create_subprocess_exec: AsyncMock
    ) -> None:
        """Test git_commit timeout handling."""
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()
        mock_create_subprocess_exec.return_value = mock_proc

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_commit"].handler({"message": "test"})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_git_commit_git_error(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_commit with generic git error."""
        mock_subprocess.communicate.return_value = (
            b"",
            b"fatal: some git error",
        )
        mock_subprocess.returncode = 1

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_commit"].handler({"message": "test"})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "GIT_ERROR"


# =============================================================================
# git_push Tests
# =============================================================================


class TestGitPush:
    """Tests for git_push tool (T067-T069)."""

    @pytest.mark.asyncio
    async def test_git_push_success(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_push with successful push (T067).

        Verifies:
        - Push succeeds
        - Response contains success, commits_pushed, remote, and branch
        """

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args:
                # Get current branch
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(b"feature-branch\n", b""))
                return proc
            if "push" in args:
                # Push succeeds
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(
                        b"",
                        (
                            b"To github.com:org/repo\n"
                            b"   abc123..def456  feature-branch -> feature-branch\n"
                        ),
                    )
                )
                return proc
            # git --version and rev-parse --git-dir
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        assert parsed["remote"] == "origin"
        assert parsed["branch"] == "feature-branch"
        assert parsed["commits_pushed"] >= 1

    @pytest.mark.asyncio
    async def test_git_push_detached_head(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_push from detached HEAD state (T068).

        Verifies:
        - DETACHED_HEAD error code
        - Appropriate error message
        """

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args and "--abbrev-ref" in args:
                # Return HEAD for detached HEAD state
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"HEAD\n", b""))
                return proc
            # Other commands succeed
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "DETACHED_HEAD"

    @pytest.mark.asyncio
    async def test_git_push_auth_required(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_push with authentication failure (T069).

        Verifies:
        - AUTHENTICATION_REQUIRED error code
        - Detects various auth error patterns
        """

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args and "--abbrev-ref" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"main\n", b""))
                return proc
            if "push" in args:
                proc = MagicMock()
                proc.returncode = 1
                proc.communicate = AsyncMock(
                    return_value=(
                        b"",
                        b"fatal: Authentication failed for 'https://github.com/org/repo'\n",
                    )
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "AUTHENTICATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_git_push_network_error(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_push with network error."""

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args and "--abbrev-ref" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"main\n", b""))
                return proc
            if "push" in args:
                proc = MagicMock()
                proc.returncode = 1
                proc.communicate = AsyncMock(
                    return_value=(
                        b"", b"fatal: could not resolve host: github.com\n")
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_git_push_not_a_repository(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_push when not in a git repository."""

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args and "--git-dir" in args:
                # Not a git repo
                proc = MagicMock()
                proc.returncode = 1
                proc.communicate = AsyncMock(
                    return_value=(b"", b"fatal: not a git repository\n")
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_push"].handler({"set_upstream": False})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "NOT_A_REPOSITORY"

    @pytest.mark.asyncio
    async def test_git_push_set_upstream(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_push with set_upstream=True."""

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args and "--abbrev-ref" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"feature\n", b""))
                return proc
            if "push" in args:
                # Verify -u flag is present
                assert "-u" in args
                assert "origin" in args
                assert "feature" in args
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(
                        b"",
                        (
                            b"Branch 'feature' set up to track remote branch "
                            b"'feature' from 'origin'.\n"
                        ),
                    )
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_push"].handler({"set_upstream": True})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True


# =============================================================================
# git_current_branch Tests
# =============================================================================


class TestGitCurrentBranch:
    """Tests for git_current_branch tool (T059-T061)."""

    @pytest.mark.asyncio
    async def test_git_current_branch_success(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_current_branch with successful branch retrieval (T059).

        Verifies:
        - Branch name is retrieved correctly
        - Response contains branch field
        """

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args and "--abbrev-ref" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(b"feature-branch\n", b""))
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_current_branch"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["branch"] == "feature-branch"

    @pytest.mark.asyncio
    async def test_git_current_branch_detached(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_current_branch in detached HEAD state (T060).

        Verifies:
        - Returns "(detached)" when in detached HEAD state
        - No error is raised
        """

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args and "--abbrev-ref" in args:
                # Return "HEAD" for detached HEAD
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"HEAD\n", b""))
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_current_branch"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["branch"] == "(detached)"

    @pytest.mark.asyncio
    async def test_git_current_branch_not_repo(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_current_branch when not in a git repository (T061).

        Verifies:
        - NOT_A_REPOSITORY error code
        - Appropriate error message
        """

        async def side_effect(*args, **kwargs):
            if "rev-parse" in args and "--git-dir" in args:
                # Not a git repo
                proc = MagicMock()
                proc.returncode = 1
                proc.communicate = AsyncMock(
                    return_value=(b"", b"fatal: not a git repository\n")
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_current_branch"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "NOT_A_REPOSITORY"


# =============================================================================
# git_diff_stats Tests
# =============================================================================


class TestGitDiffStats:
    """Tests for git_diff_stats tool (T070-T071)."""

    @pytest.mark.asyncio
    async def test_git_diff_stats_success(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_diff_stats with changes present (T070).

        Verifies:
        - Statistics are parsed correctly
        - Response contains files_changed, insertions, deletions
        """

        async def side_effect(*args, **kwargs):
            if "diff" in args and "--shortstat" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(
                        b" 3 files changed, 50 insertions(+), 20 deletions(-)\n",
                        b"",
                    )
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_diff_stats"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["files_changed"] == 3
        assert parsed["insertions"] == 50
        assert parsed["deletions"] == 20

    @pytest.mark.asyncio
    async def test_git_diff_stats_no_changes(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_diff_stats with no changes (T071).

        Verifies:
        - Empty diff returns zeros
        - No error is raised
        """

        async def side_effect(*args, **kwargs):
            if "diff" in args and "--shortstat" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(return_value=(b"", b""))
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_diff_stats"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["files_changed"] == 0
        assert parsed["insertions"] == 0
        assert parsed["deletions"] == 0

    @pytest.mark.asyncio
    async def test_git_diff_stats_insertions_only(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_diff_stats with only insertions."""

        async def side_effect(*args, **kwargs):
            if "diff" in args and "--shortstat" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(
                        b" 2 files changed, 100 insertions(+)\n", b"")
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_diff_stats"].handler({})

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["files_changed"] == 2
        assert parsed["insertions"] == 100
        assert parsed["deletions"] == 0

    @pytest.mark.asyncio
    async def test_git_diff_stats_deletions_only(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_diff_stats with only deletions."""

        async def side_effect(*args, **kwargs):
            if "diff" in args and "--shortstat" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(b" 1 file changed, 50 deletions(-)\n", b"")
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_diff_stats"].handler({})

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
    async def test_git_create_branch_success(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_create_branch with successful branch creation (T062).

        Verifies:
        - Branch is created and checked out
        - Response contains success, branch, and base
        """

        async def side_effect(*args, **kwargs):
            if "checkout" in args and "-b" in args:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(b"Switched to a new branch 'feature'\n", b"")
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_create_branch"].handler(
                {"name": "feature"}
            )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        assert parsed["branch"] == "feature"
        assert parsed["base"] == "(current)"

    @pytest.mark.asyncio
    async def test_git_create_branch_with_base(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_create_branch with base branch specified."""

        async def side_effect(*args, **kwargs):
            if "checkout" in args and "-b" in args:
                # Verify base branch is in args
                assert "main" in args
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate = AsyncMock(
                    return_value=(b"Switched to a new branch 'feature'\n", b"")
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_create_branch"].handler(
                {"name": "feature", "base": "main"}
            )

        parsed = json.loads(result["content"][0]["text"])
        assert parsed["success"] is True
        assert parsed["base"] == "main"

    @pytest.mark.asyncio
    async def test_git_create_branch_exists(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_create_branch when branch already exists (T063).

        Verifies:
        - BRANCH_EXISTS error code
        - Appropriate error message
        """

        async def side_effect(*args, **kwargs):
            if "checkout" in args and "-b" in args:
                proc = MagicMock()
                proc.returncode = 1
                proc.communicate = AsyncMock(
                    return_value=(
                        b"",
                        b"fatal: A branch named 'feature' already exists.\n",
                    )
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_create_branch"].handler(
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
        result = await server["tools"]["git_create_branch"].handler(
            {"name": "invalid name"}
        )
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"

        # Test with special characters
        result = await server["tools"]["git_create_branch"].handler(
            {"name": "invalid~branch"}
        )
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_git_create_branch_empty_name(self) -> None:
        """Test git_create_branch with empty name."""
        server = create_git_tools_server()
        result = await server["tools"]["git_create_branch"].handler({"name": ""})
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["isError"] is True
        assert parsed["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_git_create_branch_base_not_found(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test git_create_branch when base branch doesn't exist."""

        async def side_effect(*args, **kwargs):
            if "checkout" in args and "-b" in args:
                proc = MagicMock()
                proc.returncode = 1
                proc.communicate = AsyncMock(
                    return_value=(b"", b"fatal: 'nonexistent' not found\n")
                )
                return proc
            return mock_subprocess

        mock_create_subprocess_exec.side_effect = side_effect

        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
            server = create_git_tools_server()
            result = await server["tools"]["git_create_branch"].handler(
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

    def test_create_git_tools_server(
        self, mock_create_subprocess_exec: AsyncMock, mock_subprocess: MagicMock
    ) -> None:
        """Test create_git_tools_server creates server with all tools (T072).

        Verifies:
        - Server is created successfully
        - All 5 tools are registered
        - Server has correct name and version
        """
        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
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
        mock_create_subprocess_exec: AsyncMock,
        mock_subprocess: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test create_git_tools_server with custom working directory."""
        with patch("asyncio.create_subprocess_exec", mock_create_subprocess_exec):
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
