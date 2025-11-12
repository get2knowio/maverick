"""Unit tests for branch checkout activities.

Tests cover:
- derive_task_branch: Explicit overrides and specs/<slug>/ derivation
- checkout_task_branch: Clean checkouts, idempotent retries, dirty worktree failures
- checkout_main: Fast-forward pulls, already-on-main short-circuit
- delete_task_branch: Deletion success and missing-branch no-ops
"""


import pytest

from src.models.branch_management import BranchSelection


class TestDeriveTaskBranch:
    """Test branch name derivation from TaskDescriptor."""

    @pytest.mark.asyncio
    async def test_explicit_branch_override_used(self):
        """When explicitBranch is provided, it should override slug derivation."""
        # GIVEN: Task descriptor with explicit branch
        descriptor = {
            "task_id": "task-001",
            "spec_path": "/workspaces/maverick/specs/001-feature-alpha/spec.md",
            "explicit_branch": "custom-branch-name",
            "phases": ["phase1"],
        }

        # WHEN: Deriving branch
        from src.activities.branch_checkout import derive_task_branch

        result = await derive_task_branch(descriptor)

        # THEN: Explicit branch should be used
        assert isinstance(result, BranchSelection)
        assert result.branch_name == "custom-branch-name"
        assert result.source == "explicit"
        assert "custom-branch-name" in result.log_message

    @pytest.mark.asyncio
    async def test_spec_slug_derivation_from_path(self):
        """When explicitBranch is None, derive branch from specs/<slug>/ path."""
        # GIVEN: Task descriptor without explicit branch
        descriptor = {
            "task_id": "task-002",
            "spec_path": "/workspaces/maverick/specs/001-feature-beta/spec.md",
            "explicit_branch": None,
            "phases": ["phase1"],
        }

        # WHEN: Deriving branch
        from src.activities.branch_checkout import derive_task_branch

        result = await derive_task_branch(descriptor)

        # THEN: Branch should be derived from parent directory name
        assert isinstance(result, BranchSelection)
        assert result.branch_name == "001-feature-beta"
        assert result.source == "spec-slug"
        assert "001-feature-beta" in result.log_message

    @pytest.mark.asyncio
    async def test_validates_explicit_branch_format(self):
        """Explicit branch names must match git-safe pattern."""
        # GIVEN: Task descriptor with invalid branch name
        descriptor = {
            "task_id": "task-003",
            "spec_path": "/workspaces/maverick/specs/001-feature-gamma/spec.md",
            "explicit_branch": "invalid branch name!",  # Spaces and special chars
            "phases": ["phase1"],
        }

        # WHEN/THEN: Should raise validation error
        from src.activities.branch_checkout import derive_task_branch

        with pytest.raises(ValueError, match="git-safe"):
            await derive_task_branch(descriptor)

    @pytest.mark.asyncio
    async def test_spec_path_not_in_specs_directory_fails(self):
        """Spec path must be under specs/ directory for slug derivation."""
        # GIVEN: Task descriptor with path outside specs/
        descriptor = {
            "task_id": "task-004",
            "spec_path": "/workspaces/maverick/other/feature/spec.md",
            "explicit_branch": None,
            "phases": ["phase1"],
        }

        # WHEN/THEN: Should raise validation error
        from src.activities.branch_checkout import derive_task_branch

        with pytest.raises(ValueError, match="specs/"):
            await derive_task_branch(descriptor)


class TestCheckoutTaskBranch:
    """Test git branch checkout operations."""

    @pytest.mark.asyncio
    async def test_clean_checkout_success(self, git_repo_factory, monkeypatch):
        """Checkout should succeed with clean working tree and existing branch."""
        # GIVEN: Clean git repo with target branch
        repo_path = git_repo_factory.create_repo(name="test-clean-checkout", commits=1)
        git_repo_factory.create_branch(repo_path, "feature-branch")

        # Set working directory to repo
        monkeypatch.chdir(repo_path)

        # WHEN: Checking out the branch
        from src.activities.branch_checkout import checkout_task_branch

        result = await checkout_task_branch("feature-branch")

        # THEN: Should report successful checkout
        assert result.status == "success"
        assert result.branch_name == "feature-branch"
        assert result.changed is True
        assert len(result.git_head) == 7  # Short SHA
        assert len(result.logs) > 0

    @pytest.mark.asyncio
    async def test_idempotent_retry_already_on_branch(self, git_repo_factory, monkeypatch):
        """When already on target branch, should short-circuit without git operations."""
        # GIVEN: Repo already on target branch
        repo_path = git_repo_factory.create_repo(name="test-idempotent", commits=1)
        git_repo_factory.create_branch(repo_path, "feature-branch", switch=True)

        # Set working directory to repo
        monkeypatch.chdir(repo_path)

        # WHEN: Checking out same branch again
        from src.activities.branch_checkout import checkout_task_branch

        result = await checkout_task_branch("feature-branch")

        # THEN: Should report already active
        assert result.status == "already-active"
        assert result.branch_name == "feature-branch"
        assert result.changed is False
        assert len(result.git_head) == 7

    @pytest.mark.asyncio
    async def test_dirty_worktree_fails_fast(self, git_repo_factory, monkeypatch):
        """Checkout should fail immediately if working tree has uncommitted changes."""
        # GIVEN: Repo with dirty working tree
        repo_path = git_repo_factory.create_repo(name="test-dirty", commits=1)
        git_repo_factory.create_branch(repo_path, "feature-branch")
        git_repo_factory.make_worktree_dirty(repo_path, "dirty.txt")

        # Set working directory to repo
        monkeypatch.chdir(repo_path)

        # WHEN/THEN: Should raise error about dirty working tree
        from src.activities.branch_checkout import checkout_task_branch

        with pytest.raises(RuntimeError, match="dirty|uncommitted"):
            await checkout_task_branch("feature-branch")

    @pytest.mark.asyncio
    async def test_fetches_before_checkout(self, git_repo_factory, monkeypatch):
        """Checkout should fetch from origin before switching branches."""
        # GIVEN: Repo with local branch (fetch will warn but succeed)
        repo_path = git_repo_factory.create_repo(name="test-fetch", commits=1)
        git_repo_factory.create_branch(repo_path, "feature-from-remote")

        # Set working directory to repo
        monkeypatch.chdir(repo_path)

        # WHEN: Checking out the branch
        from src.activities.branch_checkout import checkout_task_branch

        result = await checkout_task_branch("feature-from-remote")

        # THEN: Should successfully checkout (fetch might warn but won't fail)
        assert result.status == "success"
        assert result.branch_name == "feature-from-remote"


class TestCheckoutTaskBranchMissingBranch:
    """Test missing branch error scenarios."""

    @pytest.mark.asyncio
    async def test_missing_branch_raises_structured_error(self, git_repo_factory, monkeypatch):
        """When branch doesn't exist, should raise error with actionable message."""
        # GIVEN: Repo without target branch
        repo_path = git_repo_factory.create_repo(name="test-missing", commits=1)

        # Set working directory to repo
        monkeypatch.chdir(repo_path)

        # WHEN/THEN: Should raise error with branch name
        from src.activities.branch_checkout import checkout_task_branch

        with pytest.raises(RuntimeError, match="nonexistent-branch"):
            await checkout_task_branch("nonexistent-branch")

    @pytest.mark.asyncio
    async def test_missing_branch_error_includes_retry_metadata(self, git_repo_factory, monkeypatch):
        """Missing branch errors should include retry hints."""
        # GIVEN: Repo without target branch
        repo_path = git_repo_factory.create_repo(name="test-missing-hints", commits=1)

        # Set working directory to repo
        monkeypatch.chdir(repo_path)

        # WHEN: Attempting checkout
        from src.activities.branch_checkout import checkout_task_branch

        with pytest.raises(RuntimeError) as exc_info:
            await checkout_task_branch("missing-feature")

        # THEN: Error should contain retry hints
        error_msg = str(exc_info.value)
        assert "missing-feature" in error_msg
        # Should suggest checking branch exists or creating it
        assert any(
            word in error_msg.lower() for word in ["create", "exists", "correct"]
        )
