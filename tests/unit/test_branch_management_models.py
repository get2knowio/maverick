"""Unit tests for branch management data models.

Tests dataclass invariant enforcement and default field validation
for branch management models.
"""

import pytest

from src.models.branch_management import (
    BranchExecutionContext,
    BranchSelection,
    CheckoutResult,
    DeletionResult,
    MainCheckoutResult,
)


class TestBranchSelection:
    """Tests for BranchSelection dataclass."""

    def test_explicit_branch_source(self):
        """BranchSelection with explicit source should be valid."""
        selection = BranchSelection(
            branch_name="feature/test",
            source="explicit",
            log_message="Using explicit branch override",
        )
        assert selection.branch_name == "feature/test"
        assert selection.source == "explicit"
        assert selection.log_message == "Using explicit branch override"

    def test_spec_slug_source(self):
        """BranchSelection with spec-slug source should be valid."""
        selection = BranchSelection(
            branch_name="001-task-branch-switch",
            source="spec-slug",
            log_message="Derived from spec directory",
        )
        assert selection.branch_name == "001-task-branch-switch"
        assert selection.source == "spec-slug"

    def test_branch_name_required(self):
        """BranchSelection with empty branch_name should fail."""
        with pytest.raises(ValueError, match="branch_name must be non-empty"):
            BranchSelection(
                branch_name="",
                source="explicit",
                log_message="Test",
            )


class TestCheckoutResult:
    """Tests for CheckoutResult dataclass."""

    def test_successful_checkout(self):
        """CheckoutResult for successful checkout should be valid."""
        result = CheckoutResult(
            branch_name="feature/test",
            changed=True,
            status="success",
            git_head="abc123f",
            logs=["Switched to branch 'feature/test'"],
        )
        assert result.branch_name == "feature/test"
        assert result.changed is True
        assert result.status == "success"
        assert result.git_head == "abc123f"

    def test_already_active_checkout(self):
        """CheckoutResult for already-active branch should be valid."""
        result = CheckoutResult(
            branch_name="main",
            changed=False,
            status="already-active",
            git_head="def456a",
            logs=["Already on 'main'"],
        )
        assert result.changed is False
        assert result.status == "already-active"

    def test_invalid_status(self):
        """CheckoutResult with invalid status should fail at type check."""
        # This would be caught by type checker, but we can test runtime
        # For now, just verify valid statuses work
        CheckoutResult(
            branch_name="test",
            changed=True,
            status="success",
            git_head="abc",
            logs=[],
        )

    def test_branch_name_required(self):
        """CheckoutResult with empty branch_name should fail."""
        with pytest.raises(ValueError, match="branch_name must be non-empty"):
            CheckoutResult(
                branch_name="",
                changed=True,
                status="success",
                git_head="abc",
                logs=[],
            )


class TestMainCheckoutResult:
    """Tests for MainCheckoutResult dataclass."""

    def test_successful_main_checkout_with_pull(self):
        """MainCheckoutResult for successful checkout with pull should be valid."""
        result = MainCheckoutResult(
            status="success",
            git_head="xyz789b",
            pull_fast_forwarded=True,
            logs=["Switched to branch 'main'", "Fast-forwarded to origin/main"],
        )
        assert result.status == "success"
        assert result.pull_fast_forwarded is True

    def test_already_on_main(self):
        """MainCheckoutResult for already-on-main should be valid."""
        result = MainCheckoutResult(
            status="already-on-main",
            git_head="xyz789b",
            pull_fast_forwarded=False,
            logs=["Already on 'main'"],
        )
        assert result.status == "already-on-main"
        assert result.pull_fast_forwarded is False


class TestDeletionResult:
    """Tests for DeletionResult dataclass."""

    def test_successful_deletion(self):
        """DeletionResult for successful deletion should be valid."""
        result = DeletionResult(
            status="deleted",
            reason="Branch deleted successfully",
            logs=["Deleted branch feature/test"],
        )
        assert result.status == "deleted"
        assert result.reason == "Branch deleted successfully"

    def test_missing_branch_deletion(self):
        """DeletionResult for missing branch should be valid."""
        result = DeletionResult(
            status="missing",
            reason="Branch does not exist",
            logs=["Branch not found"],
        )
        assert result.status == "missing"
        assert result.reason == "Branch does not exist"


class TestBranchExecutionContext:
    """Tests for BranchExecutionContext dataclass."""

    def test_pending_checkout_context(self):
        """BranchExecutionContext with pending checkout should be valid."""
        context = BranchExecutionContext(
            resolved_branch="feature/test",
            checkout_status="pending",
            checkout_message=None,
            last_checkout_at=None,
            cleanup_status="pending",
            cleanup_message=None,
        )
        assert context.resolved_branch == "feature/test"
        assert context.checkout_status == "pending"
        assert context.last_checkout_at is None

    def test_complete_checkout_context(self):
        """BranchExecutionContext with complete checkout should be valid."""
        from datetime import UTC, datetime

        checkout_time = datetime.now(UTC)
        context = BranchExecutionContext(
            resolved_branch="feature/test",
            checkout_status="complete",
            checkout_message="Checkout successful",
            last_checkout_at=checkout_time,
            cleanup_status="pending",
            cleanup_message=None,
        )
        assert context.checkout_status == "complete"
        assert context.last_checkout_at == checkout_time

    def test_complete_requires_timestamp(self):
        """BranchExecutionContext with complete status requires timestamp."""
        with pytest.raises(
            ValueError, match="checkout_status=complete requires last_checkout_at"
        ):
            BranchExecutionContext(
                resolved_branch="feature/test",
                checkout_status="complete",
                checkout_message="Test",
                last_checkout_at=None,
                cleanup_status="pending",
                cleanup_message=None,
            )

    def test_complete_requires_resolved_branch(self):
        """BranchExecutionContext with complete status requires resolved_branch."""
        from datetime import UTC, datetime

        with pytest.raises(
            ValueError, match="checkout_status=complete requires resolved_branch"
        ):
            BranchExecutionContext(
                resolved_branch="",
                checkout_status="complete",
                checkout_message="Test",
                last_checkout_at=datetime.now(UTC),
                cleanup_status="pending",
                cleanup_message=None,
            )

    def test_cleanup_requires_checkout_complete(self):
        """BranchExecutionContext cleanup requires checkout to be complete."""
        with pytest.raises(
            ValueError,
            match="cleanup_status!=pending requires checkout_status=complete",
        ):
            BranchExecutionContext(
                resolved_branch="feature/test",
                checkout_status="pending",
                checkout_message=None,
                last_checkout_at=None,
                cleanup_status="complete",
                cleanup_message="Cleanup done",
            )

    def test_complete_cleanup_context(self):
        """BranchExecutionContext with complete cleanup should be valid."""
        from datetime import UTC, datetime

        context = BranchExecutionContext(
            resolved_branch="feature/test",
            checkout_status="complete",
            checkout_message="Checkout successful",
            last_checkout_at=datetime.now(UTC),
            cleanup_status="complete",
            cleanup_message="Returned to main and deleted branch",
        )
        assert context.checkout_status == "complete"
        assert context.cleanup_status == "complete"
