"""Temporary git repository fixtures for testing branch management activities.

Provides pytest fixtures for creating isolated git repositories with commits and branches.
Used by branch checkout activity tests to simulate real git operations.
"""

import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path


class GitRepoFactory:
    """Factory for creating temporary git repositories for tests.

    Provides methods to initialize git repos with commits and branches,
    simulating real-world scenarios for branch management testing.
    """

    def __init__(self, tmp_path: Path) -> None:
        """Initialize factory with a temporary directory.

        Args:
            tmp_path: Base temporary directory from pytest tmp_path fixture
        """
        self.tmp_path = tmp_path
        self.repos_created: list[Path] = []

    def create_repo(
        self,
        name: str = "test-repo",
        initial_branch: str = "main",
        commits: int = 1,
    ) -> Path:
        """Create a new git repository with initial commits.

        Args:
            name: Name of the repository directory
            initial_branch: Name of the initial branch (default: "main")
            commits: Number of initial commits to create (default: 1)

        Returns:
            Path to the created repository root

        Raises:
            subprocess.CalledProcessError: If git commands fail
        """
        repo_path = self.tmp_path / name
        repo_path.mkdir(parents=True, exist_ok=True)
        self.repos_created.append(repo_path)

        # Initialize git repository
        self._run_git(repo_path, ["init", f"--initial-branch={initial_branch}"])

        # Configure git user for commits
        self._run_git(repo_path, ["config", "user.name", "Test User"])
        self._run_git(repo_path, ["config", "user.email", "test@example.com"])

        # Create initial commits
        for i in range(commits):
            commit_file = repo_path / f"commit-{i}.txt"
            commit_file.write_text(f"Commit {i}\n")
            self._run_git(repo_path, ["add", commit_file.name])
            self._run_git(repo_path, ["commit", "-m", f"Initial commit {i}"])

        return repo_path

    def create_branch(
        self,
        repo_path: Path,
        branch_name: str,
        from_ref: str | None = None,
        switch: bool = False,
    ) -> None:
        """Create a new branch in the repository.

        Args:
            repo_path: Path to the git repository
            branch_name: Name of the new branch
            from_ref: Optional ref to branch from (default: current HEAD)
            switch: Whether to switch to the new branch after creation

        Raises:
            subprocess.CalledProcessError: If git commands fail
        """
        cmd = ["branch", branch_name]
        if from_ref:
            cmd.append(from_ref)
        self._run_git(repo_path, cmd)

        if switch:
            self._run_git(repo_path, ["switch", branch_name])

    def add_commit(
        self,
        repo_path: Path,
        message: str = "Test commit",
        file_name: str | None = None,
    ) -> str:
        """Add a new commit to the current branch.

        Args:
            repo_path: Path to the git repository
            message: Commit message
            file_name: Optional specific file name (auto-generated if None)

        Returns:
            Short SHA of the created commit

        Raises:
            subprocess.CalledProcessError: If git commands fail
        """
        if file_name is None:
            # Generate unique file name based on message hash
            file_name = f"file-{hash(message) % 10000}.txt"

        commit_file = repo_path / file_name
        commit_file.write_text(f"{message}\n")
        self._run_git(repo_path, ["add", file_name])
        self._run_git(repo_path, ["commit", "-m", message])

        # Return short SHA
        result = self._run_git(repo_path, ["rev-parse", "--short", "HEAD"])
        return result.stdout.decode("utf-8", errors="replace").strip()

    def get_current_branch(self, repo_path: Path) -> str:
        """Get the name of the currently checked out branch.

        Args:
            repo_path: Path to the git repository

        Returns:
            Name of the current branch

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = self._run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.decode("utf-8", errors="replace").strip()

    def get_current_commit(self, repo_path: Path) -> str:
        """Get the short SHA of the current HEAD commit.

        Args:
            repo_path: Path to the git repository

        Returns:
            Short SHA of HEAD commit

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        result = self._run_git(repo_path, ["rev-parse", "--short", "HEAD"])
        return result.stdout.decode("utf-8", errors="replace").strip()

    def is_worktree_clean(self, repo_path: Path) -> bool:
        """Check if the working tree is clean (no uncommitted changes).

        Args:
            repo_path: Path to the git repository

        Returns:
            True if worktree is clean, False otherwise
        """
        result = self._run_git(repo_path, ["status", "--porcelain"])
        return len(result.stdout.strip()) == 0

    def make_worktree_dirty(self, repo_path: Path, file_name: str = "dirty.txt") -> None:
        """Create an uncommitted change in the working tree.

        Args:
            repo_path: Path to the git repository
            file_name: Name of the file to create/modify
        """
        dirty_file = repo_path / file_name
        dirty_file.write_text("Uncommitted changes\n")

    def cleanup(self) -> None:
        """Clean up all created repositories.

        Removes all repository directories created by this factory.
        """
        for repo_path in self.repos_created:
            if repo_path.exists():
                shutil.rmtree(repo_path)
        self.repos_created.clear()

    def _run_git(self, repo_path: Path, args: list[str]) -> subprocess.CompletedProcess:
        """Run a git command in the repository.

        Args:
            repo_path: Path to the git repository
            args: Git command arguments (without 'git' prefix)

        Returns:
            CompletedProcess instance with command results

        Raises:
            subprocess.CalledProcessError: If git command fails
        """
        return subprocess.run(
            ["git", *args],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
