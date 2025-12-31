"""Tests for GitPython-based GitRepository.

Comprehensive test suite for GitRepository and AsyncGitRepository classes.
Uses temporary git repositories for isolation.
"""

from __future__ import annotations

import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
from git import Repo

from maverick.exceptions import (
    BranchExistsError,
    CheckoutConflictError,
    NoStashError,
    NotARepositoryError,
    NothingToCommitError,
)
from maverick.git import (
    AsyncGitRepository,
    CommitInfo,
    DiffStats,
    GitRepository,
    GitStatus,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository with initial commit.

    Yields:
        Path to the temporary git repository.
    """
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # Initialize git repo using GitPython
    repo = Repo.init(repo_path)

    # Configure git user for commits
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    repo.config_writer().set_value("user", "name", "Test User").release()

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Test Repo\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    yield repo_path


@pytest.fixture
def temp_git_repo_with_remote(
    tmp_path: Path,
) -> Generator[tuple[Path, Path], None, None]:
    """Create a temporary git repository with a bare remote.

    Yields:
        Tuple of (local_repo_path, remote_repo_path).
    """
    # Create bare remote
    remote_path = tmp_path / "remote.git"
    Repo.init(remote_path, bare=True)

    # Create local repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Configure git user
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    repo.config_writer().set_value("user", "name", "Test User").release()

    # Add remote
    repo.create_remote("origin", str(remote_path))

    # Create initial commit and push
    readme = repo_path / "README.md"
    readme.write_text("# Test Repo\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    # Push with tracking - use subprocess for initial push
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD:main"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path, remote_path


@pytest.fixture
def non_git_dir(tmp_path: Path) -> Path:
    """Create a temporary directory that is not a git repository.

    Returns:
        Path to the non-git directory.
    """
    dir_path = tmp_path / "not_a_repo"
    dir_path.mkdir()
    return dir_path


# =============================================================================
# Test Value Objects (Dataclasses)
# =============================================================================


class TestGitStatus:
    """Tests for GitStatus dataclass."""

    def test_gitstatus_is_frozen(self) -> None:
        """GitStatus should be immutable."""
        status = GitStatus(
            staged=("a.py",),
            unstaged=("b.py",),
            untracked=("c.py",),
            branch="main",
            ahead=1,
            behind=0,
        )
        with pytest.raises(AttributeError):
            status.branch = "other"  # type: ignore[misc]

    def test_gitstatus_has_slots(self) -> None:
        """GitStatus should use slots for memory efficiency."""
        assert hasattr(GitStatus, "__slots__")


class TestCommitInfo:
    """Tests for CommitInfo dataclass."""

    def test_commitinfo_is_frozen(self) -> None:
        """CommitInfo should be immutable."""
        info = CommitInfo(
            sha="a" * 40,
            short_sha="a" * 7,
            message="test",
            author="Test",
            date="2025-01-01T00:00:00+00:00",
        )
        with pytest.raises(AttributeError):
            info.message = "changed"  # type: ignore[misc]

    def test_commitinfo_has_slots(self) -> None:
        """CommitInfo should use slots for memory efficiency."""
        assert hasattr(CommitInfo, "__slots__")


class TestDiffStats:
    """Tests for DiffStats dataclass."""

    def test_diffstats_is_frozen(self) -> None:
        """DiffStats should be immutable."""
        stats = DiffStats(
            files_changed=1,
            insertions=10,
            deletions=5,
            file_list=("a.py",),
        )
        with pytest.raises(AttributeError):
            stats.insertions = 20  # type: ignore[misc]

    def test_diffstats_has_slots(self) -> None:
        """DiffStats should use slots for memory efficiency."""
        assert hasattr(DiffStats, "__slots__")


# =============================================================================
# Test Repository Initialization
# =============================================================================


class TestGitRepositoryInit:
    """Tests for GitRepository initialization."""

    def test_init_with_valid_repo(self, temp_git_repo: Path) -> None:
        """Test initialization with valid git repository."""
        repo = GitRepository(temp_git_repo)
        assert repo.path == temp_git_repo

    def test_init_with_string_path(self, temp_git_repo: Path) -> None:
        """Test initialization with string path."""
        repo = GitRepository(str(temp_git_repo))
        assert repo.path == temp_git_repo

    def test_init_raises_not_a_repository_error(self, non_git_dir: Path) -> None:
        """Test initialization raises NotARepositoryError for non-git dir."""
        with pytest.raises(NotARepositoryError) as exc_info:
            GitRepository(non_git_dir)
        assert exc_info.value.path == non_git_dir


# =============================================================================
# Test Repository State
# =============================================================================


class TestCurrentBranch:
    """Tests for current_branch() method."""

    def test_current_branch_returns_branch_name(self, temp_git_repo: Path) -> None:
        """Test current_branch returns correct branch name."""
        # Rename to main for consistency
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        repo = GitRepository(temp_git_repo)
        branch = repo.current_branch()
        assert branch == "main"

    def test_current_branch_returns_sha_for_detached_head(
        self, temp_git_repo: Path
    ) -> None:
        """Test current_branch returns commit SHA for detached HEAD."""
        repo = GitRepository(temp_git_repo)

        # Get HEAD commit hash
        expected_sha = repo.get_head_sha()

        # Detach HEAD
        subprocess.run(
            ["git", "checkout", "--detach"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Re-open repo to get fresh state
        repo = GitRepository(temp_git_repo)
        assert repo.current_branch() == expected_sha


class TestStatus:
    """Tests for status() method."""

    def test_status_returns_gitstatus_with_files(self, temp_git_repo: Path) -> None:
        """Test status returns GitStatus with staged, unstaged, untracked files."""
        repo = GitRepository(temp_git_repo)

        # Create files in different states
        staged_file = temp_git_repo / "staged.py"
        staged_file.write_text("# staged")
        subprocess.run(
            ["git", "add", "staged.py"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        unstaged_file = temp_git_repo / "README.md"
        unstaged_file.write_text("# Modified\n")

        untracked_file = temp_git_repo / "untracked.txt"
        untracked_file.write_text("untracked")

        status = repo.status()

        assert isinstance(status, GitStatus)
        assert "staged.py" in status.staged
        assert "README.md" in status.unstaged
        assert "untracked.txt" in status.untracked


class TestLog:
    """Tests for log() method."""

    def test_log_returns_commitinfo_list(self, temp_git_repo: Path) -> None:
        """Test log returns list of CommitInfo."""
        repo = GitRepository(temp_git_repo)

        # Create additional commits
        for i in range(3):
            file_path = temp_git_repo / f"file{i}.py"
            file_path.write_text(f"# file {i}")
            repo.commit(f"Commit {i}", add_all=True)

        commits = repo.log(n=3)

        assert len(commits) == 3
        assert all(isinstance(c, CommitInfo) for c in commits)
        assert commits[0].message == "Commit 2"  # Most recent first
        assert len(commits[0].sha) == 40
        assert len(commits[0].short_sha) == 7


class TestIsDirty:
    """Tests for is_dirty() method."""

    def test_is_dirty_returns_false_for_clean_repo(self, temp_git_repo: Path) -> None:
        """Test is_dirty returns False for clean repository."""
        repo = GitRepository(temp_git_repo)
        assert repo.is_dirty() is False

    def test_is_dirty_returns_true_with_changes(self, temp_git_repo: Path) -> None:
        """Test is_dirty returns True with uncommitted changes."""
        repo = GitRepository(temp_git_repo)

        # Create untracked file
        (temp_git_repo / "new.txt").write_text("new")

        assert repo.is_dirty() is True


# =============================================================================
# Test Branch Management
# =============================================================================


class TestCreateBranch:
    """Tests for create_branch() method."""

    def test_create_branch_with_checkout_true(self, temp_git_repo: Path) -> None:
        """Test create_branch with checkout=True creates and switches to branch."""
        repo = GitRepository(temp_git_repo)
        repo.create_branch("feature-x", checkout=True)
        assert repo.current_branch() == "feature-x"

    def test_create_branch_with_checkout_false(self, temp_git_repo: Path) -> None:
        """Test create_branch with checkout=False keeps current branch."""
        repo = GitRepository(temp_git_repo)
        # Get current branch
        original = repo.current_branch()
        repo.create_branch("feature-y", checkout=False)
        assert repo.current_branch() == original

    def test_create_branch_raises_branch_exists_error(
        self, temp_git_repo: Path
    ) -> None:
        """Test create_branch raises BranchExistsError for existing branch."""
        repo = GitRepository(temp_git_repo)
        # Rename to main
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        repo = GitRepository(temp_git_repo)

        with pytest.raises(BranchExistsError) as exc_info:
            repo.create_branch("main")
        assert exc_info.value.branch_name == "main"

    def test_create_branch_with_fallback(self, temp_git_repo: Path) -> None:
        """Test create_branch_with_fallback on conflict."""
        repo = GitRepository(temp_git_repo)
        repo.create_branch("feature", checkout=False)

        # Try to create again with fallback
        actual_name = repo.create_branch_with_fallback("feature")

        assert actual_name.startswith("feature-")
        assert repo.current_branch() == actual_name


class TestCheckout:
    """Tests for checkout() method."""

    def test_checkout_switches_to_existing_branch(self, temp_git_repo: Path) -> None:
        """Test checkout switches to existing branch."""
        repo = GitRepository(temp_git_repo)

        # Create a feature branch
        repo.create_branch("feature-z", checkout=False)

        repo.checkout("feature-z")
        assert repo.current_branch() == "feature-z"

    def test_checkout_raises_conflict_error_with_uncommitted_changes(
        self, temp_git_repo: Path
    ) -> None:
        """Test checkout raises CheckoutConflictError on conflicts."""
        repo = GitRepository(temp_git_repo)

        # Create another branch with a different version of README.md
        repo.create_branch("other", checkout=True)
        readme = temp_git_repo / "README.md"
        readme.write_text("# Other branch content\n")
        repo.commit("Other branch commit", add_all=True)

        # Switch back and modify README.md without committing
        repo.checkout("master")
        readme.write_text("# Uncommitted local changes\n")

        # Try to checkout - should fail due to conflict
        with pytest.raises(CheckoutConflictError):
            repo.checkout("other")


# =============================================================================
# Test Commit Operations
# =============================================================================


class TestCommit:
    """Tests for commit() method."""

    def test_commit_with_add_all(self, temp_git_repo: Path) -> None:
        """Test commit with add_all=True stages and commits."""
        repo = GitRepository(temp_git_repo)

        # Make changes
        new_file = temp_git_repo / "new.py"
        new_file.write_text("# new file")

        commit_sha = repo.commit("Add new file", add_all=True)

        assert len(commit_sha) == 40
        assert repo.is_dirty() is False

    def test_commit_returns_commit_sha(self, temp_git_repo: Path) -> None:
        """Test commit returns commit SHA."""
        repo = GitRepository(temp_git_repo)

        new_file = temp_git_repo / "test.py"
        new_file.write_text("# test")

        commit_sha = repo.commit("Test commit", add_all=True)

        assert len(commit_sha) == 40
        assert all(c in "0123456789abcdef" for c in commit_sha)

    def test_commit_raises_nothing_to_commit_error(self, temp_git_repo: Path) -> None:
        """Test commit raises NothingToCommitError when no changes."""
        repo = GitRepository(temp_git_repo)

        with pytest.raises(NothingToCommitError):
            repo.commit("Empty commit")

    def test_commit_allow_empty(self, temp_git_repo: Path) -> None:
        """Test commit with allow_empty=True."""
        repo = GitRepository(temp_git_repo)

        commit_sha = repo.commit("Empty commit", allow_empty=True)
        assert len(commit_sha) == 40


# =============================================================================
# Test Diff Operations
# =============================================================================


class TestDiff:
    """Tests for diff() method."""

    def test_diff_returns_diff_string(self, temp_git_repo: Path) -> None:
        """Test diff returns diff string."""
        repo = GitRepository(temp_git_repo)

        # Make changes
        readme = temp_git_repo / "README.md"
        readme.write_text("# Modified Repo\nNew line\n")

        diff_output = repo.diff()

        assert "README.md" in diff_output
        assert "Modified" in diff_output or "New line" in diff_output

    def test_diff_returns_empty_when_no_changes(self, temp_git_repo: Path) -> None:
        """Test diff returns empty string when no changes."""
        repo = GitRepository(temp_git_repo)
        diff_output = repo.diff()
        assert diff_output == ""


class TestDiffStatsMethod:
    """Tests for diff_stats() method."""

    def test_diff_stats_returns_correct_counts(self, temp_git_repo: Path) -> None:
        """Test diff_stats returns DiffStats with counts."""
        repo = GitRepository(temp_git_repo)

        # Make changes
        readme = temp_git_repo / "README.md"
        readme.write_text("# Modified\nLine 2\nLine 3\n")

        stats = repo.diff_stats()

        assert isinstance(stats, DiffStats)
        assert stats.files_changed == 1
        assert stats.insertions >= 1
        assert "README.md" in stats.file_list

    def test_diff_stats_returns_zero_when_no_changes(self, temp_git_repo: Path) -> None:
        """Test diff_stats returns zero when no changes."""
        repo = GitRepository(temp_git_repo)
        stats = repo.diff_stats()

        assert stats.files_changed == 0
        assert stats.insertions == 0
        assert stats.deletions == 0


# =============================================================================
# Test Stash Operations
# =============================================================================


class TestStash:
    """Tests for stash operations."""

    def test_stash_saves_changes(self, temp_git_repo: Path) -> None:
        """Test stash saves changes and cleans working directory."""
        repo = GitRepository(temp_git_repo)

        # Make changes
        readme = temp_git_repo / "README.md"
        readme.write_text("# Stashed content\n")

        result = repo.stash("WIP: testing stash")

        assert result is True
        assert repo.is_dirty() is False

    def test_stash_returns_false_when_nothing_to_stash(
        self, temp_git_repo: Path
    ) -> None:
        """Test stash returns False when nothing to stash."""
        repo = GitRepository(temp_git_repo)
        result = repo.stash()
        assert result is False

    def test_stash_pop_restores_changes(self, temp_git_repo: Path) -> None:
        """Test stash_pop restores stashed changes."""
        repo = GitRepository(temp_git_repo)

        # Make changes and stash
        readme = temp_git_repo / "README.md"
        original_content = readme.read_text()
        readme.write_text("# Stashed\n")
        repo.stash()

        # Verify clean
        assert readme.read_text() == original_content

        # Pop stash
        repo.stash_pop()

        # Verify changes restored
        assert readme.read_text() == "# Stashed\n"

    def test_stash_pop_raises_no_stash_error(self, temp_git_repo: Path) -> None:
        """Test stash_pop raises NoStashError when no stash exists."""
        repo = GitRepository(temp_git_repo)

        with pytest.raises(NoStashError):
            repo.stash_pop()

    def test_stash_pop_by_message(self, temp_git_repo: Path) -> None:
        """Test stash_pop_by_message finds and pops correct stash."""
        repo = GitRepository(temp_git_repo)

        # Make changes and stash with specific message
        readme = temp_git_repo / "README.md"
        readme.write_text("# First stash\n")
        repo.stash("first-stash")

        readme.write_text("# Second stash\n")
        repo.stash("second-stash")

        # Pop by message
        result = repo.stash_pop_by_message("first-stash")
        assert result is True

    def test_stash_list(self, temp_git_repo: Path) -> None:
        """Test stash_list returns stash entries."""
        repo = GitRepository(temp_git_repo)

        # Create multiple stashes
        for i in range(2):
            readme = temp_git_repo / "README.md"
            readme.write_text(f"# Stash {i}\n")
            repo.stash(f"stash-{i}")

        stashes = repo.stash_list()
        assert len(stashes) >= 2


# =============================================================================
# Test Remote Operations
# =============================================================================


class TestPush:
    """Tests for push() method."""

    def test_push_with_set_upstream(
        self,
        temp_git_repo_with_remote: tuple[Path, Path],
    ) -> None:
        """Test push with set_upstream=True."""
        repo_path, _ = temp_git_repo_with_remote
        repo = GitRepository(repo_path)

        # Create new branch
        repo.create_branch("feature-push", checkout=True)

        # Make a commit
        new_file = repo_path / "feature.py"
        new_file.write_text("# feature")
        repo.commit("Add feature", add_all=True)

        # Push with upstream
        repo.push(set_upstream=True)

        # Verify tracking branch is set (via subprocess since it's easier)
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "origin/feature-push" in result.stdout


class TestPull:
    """Tests for pull() method."""

    def test_pull_fast_forwards(
        self,
        temp_git_repo_with_remote: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        """Test pull fast-forwards with new remote commits."""
        repo_path, remote_path = temp_git_repo_with_remote
        repo = GitRepository(repo_path)

        # Clone to another location and push a commit
        other_clone = tmp_path / "other_clone"
        subprocess.run(
            ["git", "clone", "--branch", "main", str(remote_path), str(other_clone)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "other@example.com"],
            cwd=other_clone,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Other User"],
            cwd=other_clone,
            check=True,
            capture_output=True,
        )
        other_file = other_clone / "other.py"
        other_file.write_text("# from other clone")
        subprocess.run(
            ["git", "add", "."],
            cwd=other_clone,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Commit from other clone"],
            cwd=other_clone,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=other_clone,
            check=True,
            capture_output=True,
        )

        # Pull from original repo - use 'main' branch explicitly
        repo.pull(branch="main")

        # Verify file from other clone exists
        assert (repo_path / "other.py").exists()


# =============================================================================
# Test Repository Information
# =============================================================================


class TestRepositoryInfo:
    """Tests for repository information methods."""

    def test_get_head_sha(self, temp_git_repo: Path) -> None:
        """Test get_head_sha returns correct SHA."""
        repo = GitRepository(temp_git_repo)
        sha = repo.get_head_sha()

        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_get_head_sha_short(self, temp_git_repo: Path) -> None:
        """Test get_head_sha with short=True."""
        repo = GitRepository(temp_git_repo)
        sha = repo.get_head_sha(short=True)

        assert len(sha) == 7

    def test_get_repo_root(self, temp_git_repo: Path) -> None:
        """Test get_repo_root returns correct path."""
        repo = GitRepository(temp_git_repo)
        root = repo.get_repo_root()

        assert root == temp_git_repo

    def test_get_remote_url(
        self,
        temp_git_repo_with_remote: tuple[Path, Path],
    ) -> None:
        """Test get_remote_url returns URL."""
        repo_path, remote_path = temp_git_repo_with_remote
        repo = GitRepository(repo_path)

        url = repo.get_remote_url()
        assert url is not None
        assert str(remote_path) in url

    def test_get_remote_url_returns_none_for_missing_remote(
        self, temp_git_repo: Path
    ) -> None:
        """Test get_remote_url returns None when remote doesn't exist."""
        repo = GitRepository(temp_git_repo)
        url = repo.get_remote_url("nonexistent")
        assert url is None


class TestGetChangedFiles:
    """Tests for get_changed_files() method."""

    def test_get_changed_files_returns_list(self, temp_git_repo: Path) -> None:
        """Test get_changed_files returns list of changed files."""
        repo = GitRepository(temp_git_repo)

        # Create files and add them to git (so they're tracked)
        (temp_git_repo / "file1.py").write_text("# file1")
        (temp_git_repo / "file2.py").write_text("# file2")
        repo.commit("Add files", add_all=True)

        # Now modify them
        (temp_git_repo / "file1.py").write_text("# file1 modified")
        (temp_git_repo / "file2.py").write_text("# file2 modified")

        files = repo.get_changed_files()

        assert len(files) >= 2
        assert any("file1.py" in f for f in files)
        assert any("file2.py" in f for f in files)

    def test_get_changed_files_empty_when_no_changes(self, temp_git_repo: Path) -> None:
        """Test get_changed_files returns empty list when no changes."""
        repo = GitRepository(temp_git_repo)
        files = repo.get_changed_files()
        assert files == []


# =============================================================================
# Test Branch Name Validation
# =============================================================================


class TestBranchValidation:
    """Tests for branch name validation."""

    def test_create_branch_validates_name(self, temp_git_repo: Path) -> None:
        """Test create_branch validates branch name."""
        repo = GitRepository(temp_git_repo)

        invalid_names = [
            "",
            " ",
            "foo bar",
            "-start-dash",
            "end-dot.",
            "invalid/char?",
            "invalid[bracket]",
            "dot..dot",
            "backslash\\",
        ]

        for name in invalid_names:
            with pytest.raises(ValueError):
                repo.create_branch(name)

    def test_checkout_validates_name(self, temp_git_repo: Path) -> None:
        """Test checkout validates branch name."""
        repo = GitRepository(temp_git_repo)

        with pytest.raises(ValueError):
            repo.checkout("-invalid-start")


# =============================================================================
# Async Wrapper Tests
# =============================================================================


class TestAsyncGitRepository:
    """Tests for AsyncGitRepository async wrapper."""

    @pytest.mark.asyncio
    async def test_async_current_branch(self, temp_git_repo: Path) -> None:
        """Test async current_branch."""
        repo = AsyncGitRepository(temp_git_repo)
        branch = await repo.current_branch()
        # Branch name depends on git version (master or main)
        assert branch in ("main", "master")

    @pytest.mark.asyncio
    async def test_async_status(self, temp_git_repo: Path) -> None:
        """Test async status."""
        # Create a file to show in status
        test_file = temp_git_repo / "test.py"
        test_file.write_text("print('test')")

        repo = AsyncGitRepository(temp_git_repo)
        status = await repo.status()

        assert isinstance(status, GitStatus)
        # Branch name depends on git version
        assert status.branch in ("main", "master")
        assert "test.py" in status.untracked

    @pytest.mark.asyncio
    async def test_async_commit(self, temp_git_repo: Path) -> None:
        """Test async commit."""
        test_file = temp_git_repo / "new_file.py"
        test_file.write_text("# New file")

        repo = AsyncGitRepository(temp_git_repo)
        commit_sha = await repo.commit("Add new file", add_all=True)

        assert commit_sha
        assert len(commit_sha) == 40

    @pytest.mark.asyncio
    async def test_async_log(self, temp_git_repo: Path) -> None:
        """Test async log."""
        repo = AsyncGitRepository(temp_git_repo)
        commits = await repo.log(n=5)

        assert isinstance(commits, list)
        assert len(commits) >= 1
        assert all(isinstance(c, CommitInfo) for c in commits)

    @pytest.mark.asyncio
    async def test_async_create_branch(self, temp_git_repo: Path) -> None:
        """Test async create_branch."""
        repo = AsyncGitRepository(temp_git_repo)
        await repo.create_branch("feature-test", checkout=True)

        branch = await repo.current_branch()
        assert branch == "feature-test"

    @pytest.mark.asyncio
    async def test_async_diff(self, temp_git_repo: Path) -> None:
        """Test async diff."""
        readme = temp_git_repo / "README.md"
        readme.write_text("# Modified Repo\n")

        repo = AsyncGitRepository(temp_git_repo)
        diff = await repo.diff()

        assert isinstance(diff, str)
        assert "Modified Repo" in diff

    @pytest.mark.asyncio
    async def test_async_diff_stats(self, temp_git_repo: Path) -> None:
        """Test async diff_stats."""
        readme = temp_git_repo / "README.md"
        readme.write_text("# Modified Repo\nWith extra line\n")

        repo = AsyncGitRepository(temp_git_repo)
        stats = await repo.diff_stats()

        assert isinstance(stats, DiffStats)
        assert stats.files_changed == 1

    @pytest.mark.asyncio
    async def test_async_stash_and_pop(self, temp_git_repo: Path) -> None:
        """Test async stash and stash_pop."""
        readme = temp_git_repo / "README.md"
        original_content = readme.read_text()
        readme.write_text("# Modified content\n")

        repo = AsyncGitRepository(temp_git_repo)

        # Stash changes
        result = await repo.stash("Test stash")
        assert result is True

        # Verify file is reverted
        assert readme.read_text() == original_content

        # Pop stash
        await repo.stash_pop()

        # Verify file has modified content back
        assert readme.read_text() == "# Modified content\n"

    @pytest.mark.asyncio
    async def test_async_exceptions_propagate(self, non_git_dir: Path) -> None:
        """Test exceptions propagate through async wrapper."""
        with pytest.raises(NotARepositoryError):
            AsyncGitRepository(non_git_dir)

    @pytest.mark.asyncio
    async def test_async_operations_dont_block_event_loop(
        self, temp_git_repo: Path
    ) -> None:
        """Test multiple async operations can run concurrently."""
        import asyncio

        repo = AsyncGitRepository(temp_git_repo)

        # Run multiple operations concurrently
        results = await asyncio.gather(
            repo.current_branch(),
            repo.status(),
            repo.log(n=1),
        )

        assert results[0] in ("main", "master")
        assert isinstance(results[1], GitStatus)
        assert isinstance(results[2], list)
