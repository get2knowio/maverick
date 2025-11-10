"""Data models for branch management operations.

Defines dataclasses for branch selection, checkout results, and execution context
used by branch checkout activities and workflows.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class BranchSelection:
    """Result of deriving a task branch name.

    Attributes:
        branch_name: The resolved branch name to use
        source: How the branch was determined (explicit or spec-slug)
        log_message: Human-readable explanation of branch selection

    Invariants:
        - branch_name must be non-empty
    """

    branch_name: str
    source: Literal["explicit", "spec-slug"]
    log_message: str

    def __post_init__(self) -> None:
        """Validate branch selection."""
        if not self.branch_name or not self.branch_name.strip():
            raise ValueError("branch_name must be non-empty")


@dataclass(frozen=True)
class CheckoutResult:
    """Result of checking out a task branch.

    Attributes:
        branch_name: Name of the branch checked out
        changed: True if checkout occurred, False if already active
        status: Outcome of checkout operation
        git_head: Short SHA of HEAD after checkout
        logs: Sanitized git CLI output summaries

    Invariants:
        - branch_name must be non-empty
    """

    branch_name: str
    changed: bool
    status: Literal["success", "already-active"]
    git_head: str
    logs: list[str]

    def __post_init__(self) -> None:
        """Validate checkout result."""
        if not self.branch_name or not self.branch_name.strip():
            raise ValueError("branch_name must be non-empty")


@dataclass(frozen=True)
class MainCheckoutResult:
    """Result of checking out and updating main branch.

    Attributes:
        status: Outcome of main checkout operation
        git_head: Short SHA of HEAD after checkout
        pull_fast_forwarded: True if pull fast-forwarded
        logs: Sanitized git CLI output summaries
    """

    status: Literal["success", "already-on-main"]
    git_head: str
    pull_fast_forwarded: bool
    logs: list[str]


@dataclass(frozen=True)
class DeletionResult:
    """Result of deleting a task branch.

    Attributes:
        status: Outcome of deletion operation
        reason: Explanation of deletion result
        logs: Sanitized git CLI output summaries
    """

    status: Literal["deleted", "missing"]
    reason: str
    logs: list[str]


@dataclass
class BranchExecutionContext:
    """Execution context for branch orchestration.

    Captures per-task branch state persisted in workflow history.

    Attributes:
        resolved_branch: Final branch name selected for the task
        checkout_status: Status of latest checkout attempt
        checkout_message: Human-readable note or failure reason
        last_checkout_at: Workflow time when checkout succeeded
        cleanup_status: Status of checkout_main/delete_task_branch sequence
        cleanup_message: Additional context about cleanup results

    Invariants:
        - checkout_status="complete" requires resolved_branch and last_checkout_at
        - cleanup_status!="pending" requires checkout_status="complete"
    """

    resolved_branch: str
    checkout_status: Literal["pending", "complete", "failed"]
    checkout_message: str | None
    last_checkout_at: datetime | None
    cleanup_status: Literal["pending", "complete", "failed"]
    cleanup_message: str | None

    def __post_init__(self) -> None:
        """Validate branch execution context."""
        # Validate complete checkout requirements
        if self.checkout_status == "complete":
            if not self.resolved_branch or not self.resolved_branch.strip():
                raise ValueError(
                    "checkout_status=complete requires resolved_branch to be non-empty"
                )
            if self.last_checkout_at is None:
                raise ValueError(
                    "checkout_status=complete requires last_checkout_at to be set"
                )

        # Validate cleanup prerequisites
        if self.cleanup_status != "pending":
            if self.checkout_status != "complete":
                raise ValueError(
                    "cleanup_status!=pending requires checkout_status=complete"
                )
