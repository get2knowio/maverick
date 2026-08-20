"""Isolated-execution primitive exceptions (057-isolated-bead-workspaces).

See specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md for
the behavioral contract each of these enforces.
"""

from __future__ import annotations

from maverick.exceptions.base import MaverickError


class IsolationError(MaverickError):
    """Base exception for the isolated-execution primitive."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class IsolationProvisioningError(IsolationError):
    """A workspace could not be created, reused, or seeded.

    Raised before any agent runs (contract C3) — its message distinguishes
    "could not isolate" (this error) from "the work failed" (an agent or
    verification error), so callers never conflate the two failure modes.

    Attributes:
        workspace_path: The workspace path provisioning was attempting.
    """

    def __init__(self, message: str, *, workspace_path: str | None = None) -> None:
        self.workspace_path = workspace_path
        super().__init__(message)


class IsolationBoundaryError(IsolationError):
    """A bd, ledger, or commit-graph call targeted a live workspace path.

    Raised by `assert_checkout` (contract C6, FR-021) — the runtime layer
    of the bd-stays-out invariant's three-layer enforcement (research.md
    R9): type-level (`CheckoutPath`), this runtime guard, and a
    repository-wide test.

    Attributes:
        path: The offending path.
        workspace_root: The live workspace root it resolved inside.
    """

    def __init__(self, message: str, *, path: str, workspace_root: str) -> None:
        self.path = path
        self.workspace_root = workspace_root
        super().__init__(message)


class IsolationLockedError(IsolationError):
    """Another isolated run already holds this checkout's run lock.

    Raised by `IsolationSession.__aenter__` (contract C1, FR-048). Isolated
    runs are hard-exclusive per checkout — unlike `notify`'s benign
    concurrent-evaluation skip, two isolated fly runs can destroy each
    other's work inside the undo window.

    Attributes:
        pid: The pid holding the lock.
    """

    def __init__(self, message: str, *, pid: int) -> None:
        self.pid = pid
        super().__init__(message)


class IsolationRecoveryRequiredError(IsolationError):
    """A prior run's application journal was left uncleared.

    Raised by `IsolationSession.__aenter__` (contract C2, FR-049) when an
    `ApplicationRecord` from a crashed run is found on entry. No automatic
    rollback is ever performed — an automatic rollback would discard
    whatever the user did in the checkout since the crash.

    Attributes:
        unit_key: Which unit was mid-application.
        operation: Which direction was in flight (``"fold-back"`` or
            ``"undo"``).
        workspace_path: Where the delta still lives.
        restore_operation_id: The jj operation to rewind to — the recovery
            handle handed to the user.
    """

    def __init__(
        self,
        message: str,
        *,
        unit_key: str,
        operation: str,
        workspace_path: str,
        restore_operation_id: str,
    ) -> None:
        self.unit_key = unit_key
        self.operation = operation
        self.workspace_path = workspace_path
        self.restore_operation_id = restore_operation_id
        super().__init__(message)


class IsolationUndoFailedError(IsolationError):
    """`jj op restore` failed while undoing a fold-back.

    The worst state this feature can produce (data-model.md `IsolationLease`
    state diagram): unverified work may be stranded in the checkout. Never
    swallowed, never silently retried (contract C5, FR-018) — the caller
    must halt the run; no further unit may begin.

    Attributes:
        workspace_path: Where the rejected delta still lives.
        restore_operation_id: The operation the restore was attempting to
            reach.
    """

    def __init__(
        self,
        message: str,
        *,
        workspace_path: str,
        restore_operation_id: str,
    ) -> None:
        self.workspace_path = workspace_path
        self.restore_operation_id = restore_operation_id
        super().__init__(message)


__all__ = [
    "IsolationBoundaryError",
    "IsolationError",
    "IsolationLockedError",
    "IsolationProvisioningError",
    "IsolationRecoveryRequiredError",
    "IsolationUndoFailedError",
]
