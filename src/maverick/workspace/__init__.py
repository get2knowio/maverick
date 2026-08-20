"""The isolated-execution primitive (057-isolated-bead-workspaces).

Public surface per
../../../specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md.
"""

from __future__ import annotations

from maverick.exceptions import (
    IsolationBoundaryError,
    IsolationError,
    IsolationLockedError,
    IsolationProvisioningError,
    IsolationRecoveryRequiredError,
    IsolationUndoFailedError,
)
from maverick.workspace.models import (
    CheckoutPath,
    FoldBackOutcome,
    FoldBackResult,
    IsolationLease,
    IsolationPolicy,
    UnitOfWork,
)
from maverick.workspace.session import (
    IsolationSession,
    assert_checkout,
    register_live_workspace,
    unregister_live_workspace,
)

__all__ = [
    "CheckoutPath",
    "FoldBackOutcome",
    "FoldBackResult",
    "IsolationBoundaryError",
    "IsolationError",
    "IsolationLease",
    "IsolationLockedError",
    "IsolationPolicy",
    "IsolationProvisioningError",
    "IsolationRecoveryRequiredError",
    "IsolationSession",
    "IsolationUndoFailedError",
    "UnitOfWork",
    "assert_checkout",
    "register_live_workspace",
    "unregister_live_workspace",
]
