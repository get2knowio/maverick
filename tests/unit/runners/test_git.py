"""Unit tests for GitRunner.

Tests all GitRunner methods with mocked CommandRunner to ensure
git operations are executed correctly without real git operations.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.runners.command import CommandRunner
from maverick.runners.git import GitResult, GitRunner
from maverick.runners.models import CommandResult
from maverick.runners.preflight import ValidationResult


@pytest.fixture
def mock_command_runner() -> MagicMock:
    """Create a mock CommandRunner for testing."""
    runner = MagicMock(spec=CommandRunner)
    runner.run = AsyncMock()
    return runner


@pytest.fixture
def git_runner(mock_command_runner: MagicMock) -> GitRunner:
    """Create a GitRunner with mocked command runner."""
    return GitRunner(cwd=Path("/test/project"), command_runner=mock_command_runner)


class TestGitResult:
    """Tests for GitResult dataclass."""

    def test_success_result(self) -> None:
        """Test creating a successful result."""
        result = GitResult(
            success=True,
            output="Switched to branch 'main'",
            error=None,
            duration_ms=50,
        )
        assert result.success is True
        assert result.output == "Switched to branch 'main'"
        assert result.error is None
        assert result.duration_ms == 50

    def test_failed_result(self) -> None:
        """Test creating a failed result."""
        result = GitResult(
            success=False,
            output="",
            error="fatal: A branch named 'main' already exists.",
            duration_ms=10,
        )
        assert result.success is False
        assert result.error == "fatal: A branch named 'main' already exists."

    def test_result_is_frozen(self) -> None:
        """Test that GitResult is immutable."""
        result = GitResult(success=True, output="", error=None, duration_ms=10)
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


class TestGitRunnerInit:
    """Tests for GitRunner initialization."""

    def test_default_initialization(self) -> None:
        """Test GitRunner with default parameters."""
        runner = GitRunner()
        assert runner.cwd is None

    def test_with_cwd(self) -> None:
        """Test GitRunner with working directory."""
        cwd = Path("/project")
        runner = GitRunner(cwd=cwd)
        assert runner.cwd == cwd

    def test_with_custom_command_runner(self, mock_command_runner: MagicMock) -> None:
        """Test GitRunner with injected command runner."""
        runner = GitRunner(command_runner=mock_command_runner)
        assert runner._runner is mock_command_runner


class TestCreateBranch:
    """Tests for GitRunner.create_branch()."""

    @pytest.mark.asyncio
    async def test_create_branch_success(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test successful branch creation."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="Switched to a new branch 'feature-x'",
            stderr="",
            duration_ms=50,
        )

        result = await git_runner.create_branch("feature-x")

        assert result.success is True
        assert "Switched to a new branch" in result.output
        assert result.error is None
        mock_command_runner.run.assert_called_once_with(
            ["git", "checkout", "-b", "feature-x", "HEAD"]
        )

    @pytest.mark.asyncio
    async def test_create_branch_from_ref(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test branch creation from specific ref."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="Switched to a new branch 'feature-x'",
            stderr="",
            duration_ms=50,
        )

        result = await git_runner.create_branch("feature-x", from_ref="main")

        mock_command_runner.run.assert_called_once_with(
            ["git", "checkout", "-b", "feature-x", "main"]
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_create_branch_already_exists(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test branch creation when branch already exists."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=128,
            stdout="",
            stderr="fatal: A branch named 'feature-x' already exists.",
            duration_ms=10,
        )

        result = await git_runner.create_branch("feature-x")

        assert result.success is False
        assert "already exists" in (result.error or "")


class TestCreateBranchWithFallback:
    """Tests for GitRunner.create_branch_with_fallback()."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test fallback not needed when first attempt succeeds."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="Switched to a new branch 'feature-x'",
            stderr="",
            duration_ms=50,
        )

        result = await git_runner.create_branch_with_fallback("feature-x")

        assert result.success is True
        assert mock_command_runner.run.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_on_conflict(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test timestamp suffix fallback on branch conflict."""
        # First call fails with "already exists"
        # Second call succeeds with timestamped name
        mock_command_runner.run.side_effect = [
            CommandResult(
                returncode=128,
                stdout="",
                stderr="fatal: A branch named 'feature-x' already exists.",
                duration_ms=10,
            ),
            CommandResult(
                returncode=0,
                stdout="Switched to a new branch 'feature-x-20231215120000'",
                stderr="",
                duration_ms=50,
            ),
        ]

        result = await git_runner.create_branch_with_fallback("feature-x")

        assert result.success is True
        assert "feature-x-" in result.output  # Contains timestamp suffix
        assert mock_command_runner.run.call_count == 2


class TestCheckout:
    """Tests for GitRunner.checkout()."""

    @pytest.mark.asyncio
    async def test_checkout_branch(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test checking out a branch."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="Switched to branch 'main'",
            stderr="",
            duration_ms=30,
        )

        result = await git_runner.checkout("main")

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(["git", "checkout", "main"])

    @pytest.mark.asyncio
    async def test_checkout_nonexistent(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test checking out nonexistent ref."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="error: pathspec 'nonexistent' did not match any file(s)",
            duration_ms=10,
        )

        result = await git_runner.checkout("nonexistent")

        assert result.success is False
        assert "did not match" in (result.error or "")


class TestCommit:
    """Tests for GitRunner.commit()."""

    @pytest.mark.asyncio
    async def test_commit_success(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test successful commit."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="[main abc1234] Test commit\n 1 file changed",
            stderr="",
            duration_ms=100,
        )

        result = await git_runner.commit("Test commit")

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(
            ["git", "commit", "-m", "Test commit"]
        )

    @pytest.mark.asyncio
    async def test_commit_allow_empty(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test commit with allow_empty flag."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="[main abc1234] Empty commit",
            stderr="",
            duration_ms=50,
        )

        result = await git_runner.commit("Empty commit", allow_empty=True)

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(
            ["git", "commit", "-m", "Empty commit", "--allow-empty"]
        )

    @pytest.mark.asyncio
    async def test_commit_nothing_to_commit(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test commit with no staged changes."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="nothing to commit, working tree clean",
            duration_ms=10,
        )

        result = await git_runner.commit("Test commit")

        assert result.success is False
        assert "nothing to commit" in (result.error or "")


class TestPush:
    """Tests for GitRunner.push()."""

    @pytest.mark.asyncio
    async def test_push_default(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test default push."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="To github.com:user/repo.git\n   abc1234..def5678  main -> main",
            duration_ms=2000,
        )

        result = await git_runner.push()

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(["git", "push", "origin"])

    @pytest.mark.asyncio
    async def test_push_with_upstream(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test push with set upstream flag."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="Branch 'feature' set up to track 'origin/feature'",
            duration_ms=2000,
        )

        result = await git_runner.push(set_upstream=True, branch="feature")

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(
            ["git", "push", "-u", "origin", "feature"]
        )

    @pytest.mark.asyncio
    async def test_push_force(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test force push."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="+ abc1234...def5678 main -> main (forced update)",
            duration_ms=2000,
        )

        result = await git_runner.push(force=True)

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(
            ["git", "push", "--force", "origin"]
        )

    @pytest.mark.asyncio
    async def test_push_rejected(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test push rejection."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="! [rejected] main -> main (non-fast-forward)",
            duration_ms=1000,
        )

        result = await git_runner.push()

        assert result.success is False
        assert "rejected" in (result.error or "")


class TestDiff:
    """Tests for GitRunner.diff()."""

    @pytest.mark.asyncio
    async def test_diff_staged(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test getting staged diff."""
        diff_output = "diff --git a/file.py b/file.py\n+new line"
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout=diff_output,
            stderr="",
            duration_ms=50,
        )

        result = await git_runner.diff()

        assert result == diff_output
        mock_command_runner.run.assert_called_once_with(["git", "diff", "--cached"])

    @pytest.mark.asyncio
    async def test_diff_unstaged(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test getting unstaged diff."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="diff output",
            stderr="",
            duration_ms=50,
        )

        await git_runner.diff(staged=False)

        mock_command_runner.run.assert_called_once_with(["git", "diff", "HEAD"])

    @pytest.mark.asyncio
    async def test_diff_with_base_ref(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test diff against specific base ref."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="diff output",
            stderr="",
            duration_ms=50,
        )

        await git_runner.diff(base="main", staged=False)

        mock_command_runner.run.assert_called_once_with(["git", "diff", "main"])


class TestAdd:
    """Tests for GitRunner.add()."""

    @pytest.mark.asyncio
    async def test_add_all(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test staging all changes."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=50,
        )

        result = await git_runner.add(add_all=True)

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(["git", "add", "-A"])

    @pytest.mark.asyncio
    async def test_add_specific_paths(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test staging specific files."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=50,
        )

        result = await git_runner.add(paths=["file1.py", "file2.py"])

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(
            ["git", "add", "file1.py", "file2.py"]
        )

    @pytest.mark.asyncio
    async def test_add_default(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test default add behavior (current directory)."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=50,
        )

        result = await git_runner.add()

        assert result.success is True
        mock_command_runner.run.assert_called_once_with(["git", "add", "."])


class TestStatus:
    """Tests for GitRunner.status()."""

    @pytest.mark.asyncio
    async def test_status_clean(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test status with clean working tree."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            duration_ms=30,
        )

        result = await git_runner.status()

        assert result.success is True
        assert result.output == ""
        mock_command_runner.run.assert_called_once_with(
            ["git", "status", "--porcelain"]
        )

    @pytest.mark.asyncio
    async def test_status_with_changes(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test status with uncommitted changes."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=0,
            stdout="M  file.py\n?? new_file.py",
            stderr="",
            duration_ms=30,
        )

        result = await git_runner.status()

        assert result.success is True
        assert "M  file.py" in result.output
        assert "?? new_file.py" in result.output


class TestTimeout:
    """Tests for timeout handling."""

    @pytest.mark.asyncio
    async def test_command_timeout(
        self, git_runner: GitRunner, mock_command_runner: MagicMock
    ) -> None:
        """Test handling of command timeout."""
        mock_command_runner.run.return_value = CommandResult(
            returncode=-1,
            stdout="",
            stderr="Command timed out",
            duration_ms=30000,
            timed_out=True,
        )

        result = await git_runner.push()

        assert result.success is False
        assert result.error == "Command timed out"


class TestGitRunnerValidate:
    """Tests for GitRunner.validate()."""

    @pytest.mark.asyncio
    @patch("maverick.runners.git.shutil.which")
    async def test_validate_success(
        self, mock_which: MagicMock, mock_command_runner: MagicMock
    ) -> None:
        """Test validate success with all checks passing."""
        mock_which.return_value = "/usr/bin/git"

        # Mock git rev-parse --is-inside-work-tree (success)
        # Mock git rev-parse --git-dir (for conflict check)
        # Mock git config user.name (success)
        # Mock git config user.email (success)
        mock_command_runner.run = AsyncMock(
            side_effect=[
                CommandResult(returncode=0, stdout="true", stderr="", duration_ms=10),
                CommandResult(returncode=0, stdout=".git", stderr="", duration_ms=10),
                CommandResult(
                    returncode=0, stdout="Test User", stderr="", duration_ms=10
                ),
                CommandResult(
                    returncode=0, stdout="test@example.com", stderr="", duration_ms=10
                ),
            ]
        )

        runner = GitRunner(
            cwd=Path("/test/project"), command_runner=mock_command_runner
        )

        # Mock Path.exists() for conflict markers to return False
        with patch.object(Path, "exists", return_value=False):
            result = await runner.validate()

        assert result.success is True
        assert result.component == "GitRunner"
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    @patch("maverick.runners.git.shutil.which")
    async def test_validate_git_not_on_path(
        self, mock_which: MagicMock, mock_command_runner: MagicMock
    ) -> None:
        """Test validate failure when git is not on PATH."""
        mock_which.return_value = None

        runner = GitRunner(
            cwd=Path("/test/project"), command_runner=mock_command_runner
        )
        result = await runner.validate()

        assert result.success is False
        assert result.component == "GitRunner"
        assert any("not found on PATH" in error for error in result.errors)
        # Should not call any git commands since git is not available
        mock_command_runner.run.assert_not_called()

    @pytest.mark.asyncio
    @patch("maverick.runners.git.shutil.which")
    async def test_validate_not_in_repository(
        self, mock_which: MagicMock, mock_command_runner: MagicMock
    ) -> None:
        """Test validate failure when not inside a git repository."""
        mock_which.return_value = "/usr/bin/git"

        # Mock git rev-parse --is-inside-work-tree (failure)
        mock_command_runner.run = AsyncMock(
            return_value=CommandResult(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
                duration_ms=10,
            )
        )

        runner = GitRunner(
            cwd=Path("/test/project"), command_runner=mock_command_runner
        )
        result = await runner.validate()

        assert result.success is False
        assert any("Not inside a git repository" in error for error in result.errors)

    @pytest.mark.asyncio
    @patch("maverick.runners.git.shutil.which")
    async def test_validate_merge_conflict_state(
        self, mock_which: MagicMock, mock_command_runner: MagicMock
    ) -> None:
        """Test validate failure when repository is in merge conflict state."""
        mock_which.return_value = "/usr/bin/git"

        # Mock successful git commands
        mock_command_runner.run = AsyncMock(
            side_effect=[
                CommandResult(returncode=0, stdout="true", stderr="", duration_ms=10),
                CommandResult(returncode=0, stdout=".git", stderr="", duration_ms=10),
                CommandResult(
                    returncode=0, stdout="Test User", stderr="", duration_ms=10
                ),
                CommandResult(
                    returncode=0, stdout="test@example.com", stderr="", duration_ms=10
                ),
            ]
        )

        runner = GitRunner(
            cwd=Path("/test/project"), command_runner=mock_command_runner
        )

        # Mock Path.exists() to return True for MERGE_HEAD
        def mock_exists(self: Path) -> bool:
            return "MERGE_HEAD" in str(self)

        with patch.object(Path, "exists", mock_exists):
            result = await runner.validate()

        assert result.success is False
        assert any("merge head" in error.lower() for error in result.errors)

    @pytest.mark.asyncio
    @patch("maverick.runners.git.shutil.which")
    async def test_validate_user_name_not_configured(
        self, mock_which: MagicMock, mock_command_runner: MagicMock
    ) -> None:
        """Test validate failure when user.name is not configured."""
        mock_which.return_value = "/usr/bin/git"

        mock_command_runner.run = AsyncMock(
            side_effect=[
                CommandResult(returncode=0, stdout="true", stderr="", duration_ms=10),
                CommandResult(returncode=0, stdout=".git", stderr="", duration_ms=10),
                CommandResult(
                    returncode=1, stdout="", stderr="", duration_ms=10
                ),  # user.name fails
                CommandResult(
                    returncode=0, stdout="test@example.com", stderr="", duration_ms=10
                ),
            ]
        )

        runner = GitRunner(
            cwd=Path("/test/project"), command_runner=mock_command_runner
        )

        with patch.object(Path, "exists", return_value=False):
            result = await runner.validate()

        assert result.success is False
        assert any("user.name is not configured" in error for error in result.errors)

    @pytest.mark.asyncio
    @patch("maverick.runners.git.shutil.which")
    async def test_validate_user_email_not_configured(
        self, mock_which: MagicMock, mock_command_runner: MagicMock
    ) -> None:
        """Test validate failure when user.email is not configured."""
        mock_which.return_value = "/usr/bin/git"

        mock_command_runner.run = AsyncMock(
            side_effect=[
                CommandResult(returncode=0, stdout="true", stderr="", duration_ms=10),
                CommandResult(returncode=0, stdout=".git", stderr="", duration_ms=10),
                CommandResult(
                    returncode=0, stdout="Test User", stderr="", duration_ms=10
                ),
                CommandResult(
                    returncode=1, stdout="", stderr="", duration_ms=10
                ),  # user.email fails
            ]
        )

        runner = GitRunner(
            cwd=Path("/test/project"), command_runner=mock_command_runner
        )

        with patch.object(Path, "exists", return_value=False):
            result = await runner.validate()

        assert result.success is False
        assert any("user.email is not configured" in error for error in result.errors)

    @pytest.mark.asyncio
    @patch("maverick.runners.git.shutil.which")
    async def test_validate_returns_validation_result(
        self, mock_which: MagicMock, mock_command_runner: MagicMock
    ) -> None:
        """Test that validate() returns correct ValidationResult type."""
        mock_which.return_value = "/usr/bin/git"

        mock_command_runner.run = AsyncMock(
            side_effect=[
                CommandResult(returncode=0, stdout="true", stderr="", duration_ms=10),
                CommandResult(returncode=0, stdout=".git", stderr="", duration_ms=10),
                CommandResult(
                    returncode=0, stdout="Test User", stderr="", duration_ms=10
                ),
                CommandResult(
                    returncode=0, stdout="test@example.com", stderr="", duration_ms=10
                ),
            ]
        )

        runner = GitRunner(
            cwd=Path("/test/project"), command_runner=mock_command_runner
        )

        with patch.object(Path, "exists", return_value=False):
            result = await runner.validate()

        assert isinstance(result, ValidationResult)
        assert hasattr(result, "success")
        assert hasattr(result, "component")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert hasattr(result, "duration_ms")
        assert result.duration_ms >= 0
