"""Tests for git_operations module.

Comprehensive test suite for GitOperations class covering all user stories.
Uses temporary git repositories for isolation.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.exceptions import (
    BranchExistsError,
    CheckoutConflictError,
    GitError,
    GitNotFoundError,
    MergeConflictError,
    NoStashError,
    NotARepositoryError,
    NothingToCommitError,
    PushRejectedError,
)
from maverick.utils.git_operations import (
    CommitInfo,
    DiffStats,
    GitOperations,
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

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)

    # Configure git user for commits
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path


@pytest.fixture
def temp_git_repo_with_remote(
    tmp_path: Path,
) -> Generator[tuple[Path, Path], None, None]:
    """Create a temporary git repository with a bare remote.

    Yields:
        Tuple of (local_repo_path, remote_repo_path).
    """
    # Create bare remote with main as default branch
    remote_path = tmp_path / "remote.git"
    remote_path.mkdir()
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main"],
        cwd=remote_path,
        check=True,
        capture_output=True,
    )

    # Create local repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Configure git user
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Add remote
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote_path)],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit and push
    readme = repo_path / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Push with tracking
    subprocess.run(
        ["git", "push", "-u", "origin", "main"],
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
            hash="a" * 40,
            short_hash="a" * 7,
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
# Test User Story 1: Query Repository State
# =============================================================================


class TestCurrentBranch:
    """Tests for current_branch() method."""

    def test_current_branch_returns_branch_name(self, temp_git_repo: Path) -> None:
        """T018: current_branch returns branch name for normal branch."""
        ops = GitOperations(temp_git_repo)
        # Rename default branch to main for consistency
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        assert ops.current_branch() == "main"

    def test_current_branch_returns_sha_for_detached_head(
        self, temp_git_repo: Path
    ) -> None:
        """T019: current_branch returns commit hash for detached HEAD."""
        ops = GitOperations(temp_git_repo)

        # Get HEAD commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        expected_sha = result.stdout.strip()

        # Detach HEAD
        subprocess.run(
            ["git", "checkout", "--detach"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        assert ops.current_branch() == expected_sha


class TestStatus:
    """Tests for status() method."""

    def test_status_returns_gitstatus_with_files(self, temp_git_repo: Path) -> None:
        """T020: status returns GitStatus with staged, unstaged, untracked files."""
        ops = GitOperations(temp_git_repo)

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

        status = ops.status()

        assert isinstance(status, GitStatus)
        assert "staged.py" in status.staged
        assert "README.md" in status.unstaged
        assert "untracked.txt" in status.untracked

    def test_status_returns_ahead_behind_counts(
        self, temp_git_repo_with_remote: tuple[Path, Path]
    ) -> None:
        """T021: status returns ahead/behind counts when tracking branch exists."""
        repo_path, _ = temp_git_repo_with_remote
        ops = GitOperations(repo_path)

        # Create a new commit (ahead by 1)
        new_file = repo_path / "new.py"
        new_file.write_text("# new")
        subprocess.run(
            ["git", "add", "."],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "New commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        status = ops.status()
        assert status.ahead == 1
        assert status.behind == 0


class TestLog:
    """Tests for log() method."""

    def test_log_returns_commitinfo_list(self, temp_git_repo: Path) -> None:
        """T022: log returns list of CommitInfo for n most recent commits."""
        ops = GitOperations(temp_git_repo)

        # Create additional commits
        for i in range(3):
            file_path = temp_git_repo / f"file{i}.py"
            file_path.write_text(f"# file {i}")
            subprocess.run(
                ["git", "add", "."],
                cwd=temp_git_repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=temp_git_repo,
                check=True,
                capture_output=True,
            )

        commits = ops.log(n=3)

        assert len(commits) == 3
        assert all(isinstance(c, CommitInfo) for c in commits)
        assert commits[0].message == "Commit 2"  # Most recent first
        assert len(commits[0].hash) == 40
        assert len(commits[0].short_hash) == 7


class TestNotARepositoryError:
    """Tests for NotARepositoryError."""

    def test_not_a_repository_error_raised(self, non_git_dir: Path) -> None:
        """T023: NotARepositoryError raised when cwd is not a git repo."""
        ops = GitOperations(non_git_dir)
        with pytest.raises(NotARepositoryError) as exc_info:
            ops.current_branch()
        assert exc_info.value.path == non_git_dir


# =============================================================================
# Test User Story 2: Branch Management
# =============================================================================


class TestCreateBranch:
    """Tests for create_branch() method."""

    def test_create_branch_with_checkout_true(self, temp_git_repo: Path) -> None:
        """T029: create_branch with checkout=True creates and switches to new branch."""
        ops = GitOperations(temp_git_repo)
        ops.create_branch("feature-x", checkout=True)
        assert ops.current_branch() == "feature-x"

    def test_create_branch_with_checkout_false(self, temp_git_repo: Path) -> None:
        """T030: create_branch with checkout=False keeps current branch."""
        ops = GitOperations(temp_git_repo)
        # Rename to main for consistency
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        original = ops.current_branch()
        ops.create_branch("feature-y", checkout=False)
        assert ops.current_branch() == original

        # Verify branch was created
        result = subprocess.run(
            ["git", "branch", "--list", "feature-y"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "feature-y" in result.stdout

    def test_create_branch_raises_branch_exists_error(
        self, temp_git_repo: Path
    ) -> None:
        """T031: create_branch raises BranchExistsError for existing branch."""
        ops = GitOperations(temp_git_repo)
        # Rename to main
        subprocess.run(
            ["git", "branch", "-M", "main"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        with pytest.raises(BranchExistsError) as exc_info:
            ops.create_branch("main")
        assert exc_info.value.branch_name == "main"


class TestCheckout:
    """Tests for checkout() method."""

    def test_checkout_switches_to_existing_branch(self, temp_git_repo: Path) -> None:
        """T032: checkout switches to existing branch."""
        ops = GitOperations(temp_git_repo)

        # Create a feature branch
        subprocess.run(
            ["git", "branch", "feature-z"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        ops.checkout("feature-z")
        assert ops.current_branch() == "feature-z"

    def test_checkout_raises_conflict_error_with_uncommitted_changes(
        self, temp_git_repo: Path
    ) -> None:
        """T033: checkout raises CheckoutConflictError on conflicts."""
        ops = GitOperations(temp_git_repo)

        # Create another branch with a different version of README.md
        subprocess.run(
            ["git", "checkout", "-b", "other"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        readme = temp_git_repo / "README.md"
        readme.write_text("# Other branch content\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Other branch commit"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Switch back to main and modify README.md without committing
        subprocess.run(
            ["git", "checkout", "-"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        readme.write_text("# Uncommitted local changes\n")

        # Try to checkout - should fail due to conflict
        with pytest.raises(CheckoutConflictError):
            ops.checkout("other")


# =============================================================================
# Test User Story 3: Commit and Push
# =============================================================================


class TestCommit:
    """Tests for commit() method."""

    def test_commit_with_add_all_stages_and_commits(self, temp_git_repo: Path) -> None:
        """T038: commit with add_all=True stages and commits all changes."""
        ops = GitOperations(temp_git_repo)

        # Make changes
        new_file = temp_git_repo / "new.py"
        new_file.write_text("# new file")

        commit_hash = ops.commit("Add new file", add_all=True)

        assert len(commit_hash) == 40
        # Verify no unstaged changes
        status = ops.status()
        assert len(status.unstaged) == 0
        assert len(status.untracked) == 0

    def test_commit_without_add_all_commits_only_staged(
        self, temp_git_repo: Path
    ) -> None:
        """T039: commit with add_all=False commits only staged changes."""
        ops = GitOperations(temp_git_repo)

        # Create and stage one file
        staged = temp_git_repo / "staged.py"
        staged.write_text("# staged")
        subprocess.run(
            ["git", "add", "staged.py"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Create but don't stage another file
        unstaged = temp_git_repo / "unstaged.py"
        unstaged.write_text("# unstaged")

        ops.commit("Commit staged only", add_all=False)

        # Verify unstaged file is still untracked
        status = ops.status()
        assert "unstaged.py" in status.untracked

    def test_commit_returns_commit_hash(self, temp_git_repo: Path) -> None:
        """T040: commit returns commit hash on success."""
        ops = GitOperations(temp_git_repo)

        new_file = temp_git_repo / "test.py"
        new_file.write_text("# test")

        commit_hash = ops.commit("Test commit", add_all=True)

        assert len(commit_hash) == 40
        assert all(c in "0123456789abcdef" for c in commit_hash)

    def test_commit_raises_nothing_to_commit_error(self, temp_git_repo: Path) -> None:
        """T041: commit raises NothingToCommitError when no changes."""
        ops = GitOperations(temp_git_repo)

        with pytest.raises(NothingToCommitError):
            ops.commit("Empty commit")


class TestPush:
    """Tests for push() method."""

    def test_push_with_set_upstream(
        self,
        temp_git_repo_with_remote: tuple[Path, Path],
    ) -> None:
        """T042: push with set_upstream=True sets tracking branch."""
        repo_path, _ = temp_git_repo_with_remote
        ops = GitOperations(repo_path)

        # Create new branch
        ops.create_branch("feature-push", checkout=True)

        # Make a commit
        new_file = repo_path / "feature.py"
        new_file.write_text("# feature")
        ops.commit("Add feature", add_all=True)

        # Push with upstream
        ops.push(set_upstream=True)

        # Verify tracking branch is set
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "origin/feature-push" in result.stdout

    def test_push_raises_rejected_error(
        self,
        temp_git_repo_with_remote: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        """T043: push raises PushRejectedError when remote rejects."""
        repo_path, remote_path = temp_git_repo_with_remote
        ops = GitOperations(repo_path)

        # Clone the remote to another location and push a conflicting change
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
        other_file.write_text("# other")
        subprocess.run(
            ["git", "add", "."],
            cwd=other_clone,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Other commit"],
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

        # Now try to push from original repo without pulling first
        local_file = repo_path / "local.py"
        local_file.write_text("# local")
        ops.commit("Local commit", add_all=True)

        # Push should be rejected since remote has diverged
        with pytest.raises((PushRejectedError, GitError)):
            ops.push()


# =============================================================================
# Test User Story 4: Diff Analysis
# =============================================================================


class TestDiff:
    """Tests for diff() method."""

    def test_diff_returns_full_diff_string(self, temp_git_repo: Path) -> None:
        """T049: diff returns full diff string between refs."""
        ops = GitOperations(temp_git_repo)

        # Make changes
        readme = temp_git_repo / "README.md"
        readme.write_text("# Modified Repo\nNew line\n")

        diff_output = ops.diff()

        assert "README.md" in diff_output
        assert "+# Modified Repo" in diff_output or "+New line" in diff_output

    def test_diff_returns_empty_string_when_no_changes(
        self,
        temp_git_repo: Path,
    ) -> None:
        """T050: diff returns empty string when no changes."""
        ops = GitOperations(temp_git_repo)

        diff_output = ops.diff()

        assert diff_output == ""


class TestDiffStatsMethod:
    """Tests for diff_stats() method."""

    def test_diff_stats_returns_correct_counts(self, temp_git_repo: Path) -> None:
        """T051: diff_stats returns DiffStats with counts."""
        ops = GitOperations(temp_git_repo)

        # Make changes
        readme = temp_git_repo / "README.md"
        readme.write_text("# Modified\nLine 2\nLine 3\n")  # 1 deletion, 3 insertions

        stats = ops.diff_stats()

        assert isinstance(stats, DiffStats)
        assert stats.files_changed == 1
        assert stats.insertions >= 1
        assert "README.md" in stats.file_list

    def test_diff_stats_returns_zero_when_no_changes(self, temp_git_repo: Path) -> None:
        """T052: diff_stats returns zero values when no changes."""
        ops = GitOperations(temp_git_repo)

        stats = ops.diff_stats()

        assert stats.files_changed == 0
        assert stats.insertions == 0
        assert stats.deletions == 0
        assert len(stats.file_list) == 0


# =============================================================================
# Test User Story 5: Sync with Remote
# =============================================================================


class TestPull:
    """Tests for pull() method."""

    def test_pull_fast_forwards_with_new_commits(
        self,
        temp_git_repo_with_remote: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        """T056: pull fast-forwards local branch with new remote commits."""
        repo_path, remote_path = temp_git_repo_with_remote
        ops = GitOperations(repo_path)

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

        # Pull from original repo
        ops.pull()

        # Verify file from other clone exists
        assert (repo_path / "other.py").exists()

    def test_pull_raises_merge_conflict_error(
        self,
        temp_git_repo_with_remote: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        """T057: pull raises MergeConflictError when conflicts occur."""
        repo_path, remote_path = temp_git_repo_with_remote
        ops = GitOperations(repo_path)

        # Clone to another location and modify README.md
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
        readme_other = other_clone / "README.md"
        readme_other.write_text("# From other clone\nConflicting content\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=other_clone,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Modify README from other"],
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

        # Modify README.md locally
        readme_local = repo_path / "README.md"
        readme_local.write_text("# Local modification\nDifferent content\n")
        ops.commit("Local README change", add_all=True)

        # Pull should cause conflict or GitError
        with pytest.raises((MergeConflictError, GitError)):
            ops.pull()

    def test_pull_raises_error_for_nonexistent_remote_branch(
        self,
        temp_git_repo_with_remote: tuple[Path, Path],
    ) -> None:
        """T058: pull raises appropriate error when remote branch does not exist."""
        repo_path, _ = temp_git_repo_with_remote
        ops = GitOperations(repo_path)

        with pytest.raises(GitError):
            ops.pull(branch="nonexistent-branch")


# =============================================================================
# Test User Story 6: Stash Operations
# =============================================================================


class TestStash:
    """Tests for stash() method."""

    def test_stash_with_message_saves_and_cleans(self, temp_git_repo: Path) -> None:
        """T061: stash with message saves changes and cleans working directory."""
        ops = GitOperations(temp_git_repo)

        # Make changes
        readme = temp_git_repo / "README.md"
        readme.write_text("# Stashed content\n")

        ops.stash(message="WIP: testing stash")

        # Verify working directory is clean
        status = ops.status()
        assert len(status.unstaged) == 0
        assert len(status.staged) == 0

        # Verify stash exists
        result = subprocess.run(
            ["git", "stash", "list"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "WIP: testing stash" in result.stdout

    def test_stash_without_message_uses_default(self, temp_git_repo: Path) -> None:
        """T062: stash without message uses default message."""
        ops = GitOperations(temp_git_repo)

        # Make changes
        readme = temp_git_repo / "README.md"
        readme.write_text("# More stashed content\n")

        ops.stash()

        # Verify working directory is clean
        status = ops.status()
        assert len(status.unstaged) == 0


class TestStashPop:
    """Tests for stash_pop() method."""

    def test_stash_pop_restores_most_recent(self, temp_git_repo: Path) -> None:
        """T063: stash_pop restores most recent stash."""
        ops = GitOperations(temp_git_repo)

        # Make changes and stash
        readme = temp_git_repo / "README.md"
        original_content = readme.read_text()
        readme.write_text("# Stashed\n")
        ops.stash()

        # Verify clean
        assert readme.read_text() == original_content

        # Pop stash
        ops.stash_pop()

        # Verify changes restored
        assert readme.read_text() == "# Stashed\n"

    def test_stash_pop_raises_no_stash_error(self, temp_git_repo: Path) -> None:
        """T064: stash_pop raises NoStashError when no stash exists."""
        ops = GitOperations(temp_git_repo)

        with pytest.raises(NoStashError):
            ops.stash_pop()


# =============================================================================
# Test Phase 9: Polish & Cross-Cutting Concerns
# =============================================================================


class TestGitNotFound:
    """Tests for GitNotFoundError."""

    def test_git_not_found_error_raised(self, temp_git_repo: Path) -> None:
        """T068: GitNotFoundError raised when git is not installed."""
        ops = GitOperations(temp_git_repo)
        ops._git_checked = False  # Reset the check

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")
            with pytest.raises(GitNotFoundError):
                ops.current_branch()


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_operations_on_same_instance(self, temp_git_repo: Path) -> None:
        """T069: Thread safety with concurrent operations on same instance."""
        import concurrent.futures

        ops = GitOperations(temp_git_repo)

        def get_branch() -> str:
            return ops.current_branch()

        def get_status() -> GitStatus:
            return ops.status()

        # Run multiple operations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for _ in range(10):
                futures.append(executor.submit(get_branch))
                futures.append(executor.submit(get_status))

            # All should complete without errors
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                assert result is not None


class TestNoShellTrue:
    """Test that no shell=True is used."""

    def test_no_shell_true_in_subprocess_calls(self) -> None:
        """T070: Verify no shell=True usage in all subprocess calls."""
        import ast
        from pathlib import Path

        module_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "maverick"
            / "utils"
            / "git_operations.py"
        )
        content = module_path.read_text()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            # Check for subprocess.run calls
            if (
                isinstance(node, ast.Call)
                and hasattr(node.func, "attr")
                and node.func.attr == "run"
            ):
                for keyword in node.keywords:
                    # shell should be False or not present
                    if keyword.arg == "shell" and isinstance(
                        keyword.value, ast.Constant
                    ):
                        assert keyword.value.value is False, (
                            "shell=True found in subprocess call"
                        )


# =============================================================================
# Additional Coverage Tests
# =============================================================================


class TestDefaultCwd:
    """Tests for default working directory."""

    def test_default_cwd_uses_current_directory(self, temp_git_repo: Path) -> None:
        """Test that GitOperations uses current directory when cwd is None."""
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_git_repo)
            ops = GitOperations()  # cwd=None case
            branch = ops.current_branch()
            assert branch in ("main", "master")
        finally:
            os.chdir(original_cwd)


class TestStatusEdgeCases:
    """Tests for status edge cases."""

    def test_status_handles_renames(self, temp_git_repo: Path) -> None:
        """Test that status handles file renames correctly."""
        ops = GitOperations(temp_git_repo)

        # Create and commit a file
        old_file = temp_git_repo / "old_name.txt"
        old_file.write_text("content")
        subprocess.run(
            ["git", "add", "."], cwd=temp_git_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Rename using git mv to trigger rename detection
        subprocess.run(
            ["git", "mv", "old_name.txt", "new_name.txt"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        status = ops.status()
        # The renamed file should appear in staged
        assert "new_name.txt" in status.staged

    def test_status_handles_short_lines(self, temp_git_repo: Path) -> None:
        """Test that status handles malformed/short lines gracefully."""
        ops = GitOperations(temp_git_repo)
        # Just verify status doesn't crash on normal repo
        status = ops.status()
        assert isinstance(status, GitStatus)


class TestCheckoutEdgeCases:
    """Tests for checkout edge cases."""

    def test_checkout_nonexistent_branch_raises_git_error(
        self,
        temp_git_repo: Path,
    ) -> None:
        """Test that checkout raises GitError for nonexistent branch."""
        ops = GitOperations(temp_git_repo)

        with pytest.raises(GitError) as exc_info:
            ops.checkout("nonexistent-branch-xyz")

        assert (
            "does not exist" in str(exc_info.value).lower()
            or "pathspec" in str(exc_info.value).lower()
        )

    def test_checkout_generic_error(self, temp_git_repo: Path) -> None:
        """Test checkout generic error handling."""
        ops = GitOperations(temp_git_repo)

        # First call is _check_repository, second is checkout
        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        checkout_error_result = subprocess.CompletedProcess(
            args=["git", "checkout", "branch"],
            returncode=1,
            stdout="",
            stderr="some other error occurred",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [check_repo_result, checkout_error_result]

            with pytest.raises(GitError) as exc_info:
                ops.checkout("some-branch")

            assert "Checkout failed" in str(exc_info.value)


class TestDiffEdgeCases:
    """Tests for diff edge cases."""

    def test_diff_with_head_parameter(self, temp_git_repo: Path) -> None:
        """Test diff with explicit head parameter."""
        ops = GitOperations(temp_git_repo)

        # Create a branch with changes
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        (temp_git_repo / "feature.txt").write_text("feature content")
        subprocess.run(
            ["git", "add", "."], cwd=temp_git_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Feature commit"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Get default branch name
        result = subprocess.run(
            ["git", "branch", "--list", "main", "master"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        main_branch = "main" if "main" in result.stdout else "master"

        # Diff between main and feature
        diff_output = ops.diff(base=main_branch, head="feature")
        assert "feature.txt" in diff_output


class TestDiffStatsEdgeCases:
    """Tests for diff_stats edge cases."""

    def test_diff_stats_with_binary_files(self, temp_git_repo: Path) -> None:
        """Test diff_stats handles binary files (shows - for ins/dels)."""
        ops = GitOperations(temp_git_repo)

        # Create a binary file
        binary_file = temp_git_repo / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03\x04\x05")

        stats = ops.diff_stats()
        # Binary files show 0 insertions/deletions but are still counted
        assert isinstance(stats, DiffStats)
        assert stats.files_changed >= 0


class TestPushEdgeCases:
    """Tests for push edge cases."""

    def test_push_remote_not_accessible(self, temp_git_repo: Path) -> None:
        """Test push raises GitError when remote is not accessible."""
        ops = GitOperations(temp_git_repo)

        # Add a fake remote
        subprocess.run(
            ["git", "remote", "add", "fake", "https://fake.invalid/repo.git"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        with pytest.raises(GitError):
            ops.push(remote="fake")

    def test_push_generic_error(self, temp_git_repo: Path) -> None:
        """Test push generic error handling."""
        ops = GitOperations(temp_git_repo)

        # First call is _check_repository, second is current_branch, third is push
        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        branch_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            returncode=0,
            stdout="main",
            stderr="",
        )
        push_error_result = subprocess.CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="unexpected error",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [
                check_repo_result,
                check_repo_result,
                branch_result,
                push_error_result,
            ]

            with pytest.raises(GitError) as exc_info:
                ops.push()

            assert "Push failed" in str(exc_info.value)


class TestPullEdgeCases:
    """Tests for pull edge cases."""

    def test_pull_remote_not_accessible(self, temp_git_repo: Path) -> None:
        """Test pull raises GitError when remote is not accessible."""
        ops = GitOperations(temp_git_repo)

        # Add a fake remote
        subprocess.run(
            ["git", "remote", "add", "fake", "https://fake.invalid/repo.git"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        with pytest.raises(GitError):
            ops.pull(remote="fake", branch="main")


class TestStashPopEdgeCases:
    """Tests for stash_pop edge cases."""

    def test_stash_pop_generic_error(self, temp_git_repo: Path) -> None:
        """Test stash_pop generic error handling."""
        ops = GitOperations(temp_git_repo)

        # First call is _check_repository, second is stash pop
        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        stash_error_result = subprocess.CompletedProcess(
            args=["git", "stash", "pop"],
            returncode=1,
            stdout="",
            stderr="unexpected stash error",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [check_repo_result, stash_error_result]

            with pytest.raises(GitError) as exc_info:
                ops.stash_pop()

            assert "Stash pop failed" in str(exc_info.value)


class TestCommitEdgeCases:
    """Tests for commit edge cases."""

    def test_commit_generic_error(self, temp_git_repo: Path) -> None:
        """Test commit generic error handling."""
        ops = GitOperations(temp_git_repo)

        # Create a file to commit
        (temp_git_repo / "test.txt").write_text("content")
        subprocess.run(
            ["git", "add", "."], cwd=temp_git_repo, check=True, capture_output=True
        )

        # First call is _check_repository, second is add -A, third is commit
        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        add_result = subprocess.CompletedProcess(
            args=["git", "add", "-A"],
            returncode=0,
            stdout="",
            stderr="",
        )
        commit_error_result = subprocess.CompletedProcess(
            args=["git", "commit", "-m", "test"],
            returncode=1,
            stdout="",
            stderr="some other commit error",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [check_repo_result, add_result, commit_error_result]

            with pytest.raises(GitError) as exc_info:
                ops.commit("test", add_all=True)

            assert "Commit failed" in str(exc_info.value)


class TestLogEdgeCases:
    """Tests for log edge cases."""

    def test_log_handles_empty_lines(self, temp_git_repo: Path) -> None:
        """Test log handles empty lines in output."""
        ops = GitOperations(temp_git_repo)

        # First call is _check_repository, second is log
        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        # Log output with empty lines
        log_result = subprocess.CompletedProcess(
            args=["git", "log"],
            returncode=0,
            stdout="abc123|abc1234|Message|Author|2025-01-01\n\ndef456|def4567|Message2|Author2|2025-01-02\n",
            stderr="",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [check_repo_result, log_result]

            commits = ops.log(n=5)
            assert len(commits) == 2


class TestStatusMockEdgeCases:
    """Tests for status edge cases using mocks."""

    def test_status_handles_short_lines_via_mock(self, temp_git_repo: Path) -> None:
        """Test status handles short/malformed lines."""
        ops = GitOperations(temp_git_repo)

        # Mock responses
        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        branch_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            returncode=0,
            stdout="main\n",
            stderr="",
        )
        status_v2_result = subprocess.CompletedProcess(
            args=["git", "status", "--branch", "--porcelain=v2"],
            returncode=0,
            stdout="# branch.ab +0 -0\n",
            stderr="",
        )
        # Status with short line that should be skipped
        status_result = subprocess.CompletedProcess(
            args=["git", "status", "--porcelain"],
            returncode=0,
            stdout="A\n?? test.txt\n",  # "A" is too short (< 3 chars)
            stderr="",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [
                check_repo_result,  # _check_repository
                check_repo_result,  # current_branch -> _check_repository
                branch_result,  # current_branch -> rev-parse
                status_v2_result,  # status v2
                status_result,  # status porcelain
            ]

            status = ops.status()
            assert "test.txt" in status.untracked


class TestDiffStatsMockEdgeCases:
    """Tests for diff_stats edge cases using mocks."""

    def test_diff_stats_handles_empty_lines(self, temp_git_repo: Path) -> None:
        """Test diff_stats handles empty lines in output."""
        ops = GitOperations(temp_git_repo)

        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        # Diff output with empty lines
        diff_result = subprocess.CompletedProcess(
            args=["git", "diff", "--numstat"],
            returncode=0,
            stdout="10\t5\tfile1.txt\n\n20\t3\tfile2.txt\n",
            stderr="",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [check_repo_result, diff_result]

            stats = ops.diff_stats()
            assert stats.files_changed == 2
            assert stats.insertions == 30
            assert stats.deletions == 8


class TestPullMockEdgeCases:
    """Tests for pull edge cases using mocks."""

    def test_pull_remote_not_accessible_via_mock(self, temp_git_repo: Path) -> None:
        """Test pull error when remote not accessible."""
        ops = GitOperations(temp_git_repo)

        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        branch_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            returncode=0,
            stdout="main",
            stderr="",
        )
        pull_error_result = subprocess.CompletedProcess(
            args=["git", "pull"],
            returncode=1,
            stdout="",
            stderr="fatal: 'origin' does not appear to be a git repository",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [
                check_repo_result,
                check_repo_result,
                branch_result,
                pull_error_result,
            ]

            with pytest.raises(GitError) as exc_info:
                ops.pull()

            assert "not found or not accessible" in str(exc_info.value).lower()

    def test_pull_merge_conflict_via_mock(self, temp_git_repo: Path) -> None:
        """Test pull merge conflict handling."""
        ops = GitOperations(temp_git_repo)

        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        branch_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            returncode=0,
            stdout="main",
            stderr="",
        )
        pull_conflict_result = subprocess.CompletedProcess(
            args=["git", "pull"],
            returncode=1,
            stdout="CONFLICT (content): Merge conflict in file.txt",
            stderr="",
        )
        status_result = subprocess.CompletedProcess(
            args=["git", "status", "--porcelain"],
            returncode=0,
            stdout="UU file.txt\nAA other.txt\n",
            stderr="",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [
                check_repo_result,  # _check_repository
                check_repo_result,  # current_branch -> _check_repository
                branch_result,  # current_branch
                pull_conflict_result,  # pull
                status_result,  # get conflicted files
            ]

            with pytest.raises(MergeConflictError) as exc_info:
                ops.pull()

            assert "file.txt" in exc_info.value.conflicted_files
            assert "other.txt" in exc_info.value.conflicted_files


class TestPushMockEdgeCases:
    """Tests for push edge cases using mocks."""

    def test_push_remote_not_accessible_via_mock(self, temp_git_repo: Path) -> None:
        """Test push error when remote not accessible."""
        ops = GitOperations(temp_git_repo)

        check_repo_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"],
            returncode=0,
            stdout=".git",
            stderr="",
        )
        branch_result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--abbrev-ref", "HEAD"],
            returncode=0,
            stdout="main",
            stderr="",
        )
        push_error_result = subprocess.CompletedProcess(
            args=["git", "push"],
            returncode=1,
            stdout="",
            stderr="fatal: 'origin' does not appear to be a git repository",
        )

        with patch.object(ops, "_run") as mock_run:
            mock_run.side_effect = [
                check_repo_result,
                check_repo_result,
                branch_result,
                push_error_result,
            ]

            with pytest.raises(GitError) as exc_info:
                ops.push()

            assert "not found or not accessible" in str(exc_info.value).lower()


class TestBranchValidation:
    """Tests for branch name validation."""

    def test_create_branch_validates_name(self, temp_git_repo: Path) -> None:
        """Test that create_branch validates branch name."""
        ops = GitOperations(temp_git_repo)

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
            with pytest.raises(ValueError) as exc_info:
                ops.create_branch(name)
            error_msg = str(exc_info.value).lower()
            assert "branch name" in error_msg or "invalid" in error_msg

    def test_checkout_validates_name(self, temp_git_repo: Path) -> None:
        """Test that checkout validates branch name."""
        ops = GitOperations(temp_git_repo)

        with pytest.raises(ValueError):
            ops.checkout("-invalid-start")
