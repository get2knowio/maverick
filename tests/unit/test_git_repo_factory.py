"""Unit tests for git_repo_factory fixture.

Tests the GitRepoFactory helper and pytest fixture for creating
temporary git repositories used in branch management tests.
"""




def test_git_repo_factory_creates_repo(git_repo_factory):
    """Test that factory creates a git repository with initial commits."""
    repo_path = git_repo_factory.create_repo(name="test-repo", commits=2)

    assert repo_path.exists()
    assert (repo_path / ".git").exists()

    # Verify initial branch
    current_branch = git_repo_factory.get_current_branch(repo_path)
    assert current_branch == "main"


def test_git_repo_factory_creates_branch(git_repo_factory):
    """Test that factory can create and switch to branches."""
    repo_path = git_repo_factory.create_repo(name="test-repo")

    # Create and switch to new branch
    git_repo_factory.create_branch(repo_path, "feature-branch", switch=True)

    current_branch = git_repo_factory.get_current_branch(repo_path)
    assert current_branch == "feature-branch"


def test_git_repo_factory_adds_commits(git_repo_factory):
    """Test that factory can add commits to repositories."""
    repo_path = git_repo_factory.create_repo(name="test-repo")

    # Add a commit and get its SHA
    sha = git_repo_factory.add_commit(repo_path, message="Test commit")

    assert len(sha) > 0
    assert sha == git_repo_factory.get_current_commit(repo_path)


def test_git_repo_factory_detects_clean_worktree(git_repo_factory):
    """Test that factory correctly detects clean working tree."""
    repo_path = git_repo_factory.create_repo(name="test-repo")

    # Initially clean
    assert git_repo_factory.is_worktree_clean(repo_path)

    # Make it dirty
    git_repo_factory.make_worktree_dirty(repo_path)
    assert not git_repo_factory.is_worktree_clean(repo_path)


def test_git_repo_factory_cleanup(git_repo_factory):
    """Test that factory cleans up created repositories."""
    repo_path = git_repo_factory.create_repo(name="test-repo")
    assert repo_path.exists()

    # Cleanup is automatic via fixture, but we can test manual cleanup
    git_repo_factory.cleanup()
    assert not repo_path.exists()


def test_git_repo_factory_custom_initial_branch(git_repo_factory):
    """Test that factory can create repo with custom initial branch."""
    repo_path = git_repo_factory.create_repo(
        name="test-repo", initial_branch="develop"
    )

    current_branch = git_repo_factory.get_current_branch(repo_path)
    assert current_branch == "develop"


def test_git_repo_factory_create_branch_from_ref(git_repo_factory):
    """Test that factory can create branch from specific ref."""
    repo_path = git_repo_factory.create_repo(name="test-repo", commits=2)

    # Get the first commit SHA
    git_repo_factory.create_branch(repo_path, "temp", switch=False)

    # Create another branch
    git_repo_factory.create_branch(repo_path, "feature", from_ref="HEAD~1")

    # Switch to it and verify it's one commit behind
    git_repo_factory._run_git(repo_path, ["switch", "feature"])
    feature_sha = git_repo_factory.get_current_commit(repo_path)

    git_repo_factory._run_git(repo_path, ["switch", "main"])
    main_sha = git_repo_factory.get_current_commit(repo_path)

    assert feature_sha != main_sha
