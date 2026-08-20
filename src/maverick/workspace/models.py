"""Typed models for the isolated-execution primitive.

Frozen dataclasses with ``to_dict()`` (Guardrail X.3 — no ad-hoc
``dict[str, Any]`` on a public surface). Persisted types carry
``schema_version`` (see ``journal.py``'s ``ApplicationRecord``, not defined
here — this module holds only the primitive's core, non-persisted types).
See ../../../specs/057-isolated-bead-workspaces/data-model.md for the
authoritative contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import NewType

__all__ = [
    "CheckoutPath",
    "FoldBackOutcome",
    "FoldBackResult",
    "IsolationLease",
    "IsolationPolicy",
    "UnitOfWork",
    "is_path_safe_slug",
]

#: Distinct from a plain ``Path`` so a workspace path cannot be passed where
#: a checkout is required — mypy rejects the mismatch under strict mode
#: (research.md R9 layer 1, FR-022, contract C6).
CheckoutPath = NewType("CheckoutPath", Path)

#: Path-safe slug: non-empty, no path separators, no leading dot — the same
#: rule spec_chain's ``is_valid_feature_slug`` enforces (models.py), reused
#: here for ``IsolationPolicy.workflow`` so a value can never traverse
#: outside the workspace root when a path is built from it.
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def is_path_safe_slug(value: str) -> bool:
    """Whether *value* is a non-empty, filesystem-safe slug."""
    return bool(value) and _SLUG_RE.match(value) is not None


def _fold_fileset_entry_is_safe(entry: str) -> bool:
    """Whether a ``fold_scope``/``fold_exclusions`` fileset entry cannot
    escape the workspace root: no absolute path, no ``..`` traversal
    segment. A leading ``~`` (jj's fileset negation, e.g. ``"~.maverick"``)
    is stripped before checking."""
    stripped = entry.lstrip("~")
    if not stripped:
        return False
    candidate = Path(stripped)
    return not candidate.is_absolute() and ".." not in candidate.parts


class FoldBackOutcome(Enum):
    """Distinguishable fold-back results (data-model.md, FR-009/FR-019).

    ``EMPTY`` is a success (a genuinely empty delta, FR-006), kept distinct
    from ``APPLIED`` so a fold-back that silently skipped the workspace
    snapshot (research.md R3) is visible in logs rather than looking like
    an ordinary no-op. ``REJECTED`` is set by the consumer after
    environment-level checks fail and undo completes — distinguishable
    from ``CONFLICT`` (fold-back mechanics) and ``DISCARDED`` (agent
    failure).
    """

    APPLIED = "applied"
    EMPTY = "empty"
    CONFLICT = "conflict"
    DISCARDED = "discarded"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class UnitOfWork:
    """The smallest thing isolated and folded back as one.

    A bead in fly, a chain step in the spec chain. Not persisted — it
    exists for the duration of one lease.

    Attributes:
        key: Workspace identity within the workflow. Bead id / feature
            slug. Path-safe.
        label: Human-readable, for progress output.
        seed_inputs: Files copied in that are absent from committed
            history (FR-004) — e.g. the chain's PRD.
    """

    key: str
    label: str
    seed_inputs: tuple[Path, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "seed_inputs": tuple(str(p) for p in self.seed_inputs),
        }


@dataclass(frozen=True, slots=True)
class IsolationPolicy:
    """How a consumer wants isolation to behave.

    Constructed once per run and reused per unit; the only place fly and
    the spec chain genuinely differ.

    Attributes:
        workflow: Path segment and log field: ``"fly"``, ``"spec-chain"``.
        root: Workspace root. From ``WorkspaceConfig.root``;
            ``~/.maverick/workspaces`` by default.
        reuse: Reuse an existing workspace for the same key instead of
            recreating (chain: yes; fly: no).
        retain_on_failure: Keep the workspace when the unit fails — it is
            the only copy of the partial output (chain: yes; fly: no).
        fold_scope: jj filesets bounding what may fold back. Empty means
            "everything not excluded". The chain passes
            ``("specs/<feature-dir>",)``.
        fold_exclusions: Always applied, always includes ``~.maverick`` and
            the protected set (R11).

    Raises:
        ValueError: ``workflow`` is not a path-safe slug, ``root`` is not
            absolute, or a ``fold_scope``/``fold_exclusions`` entry could
            escape the workspace root.
    """

    workflow: str
    root: Path
    reuse: bool = True
    retain_on_failure: bool = False
    fold_scope: tuple[str, ...] = ()
    fold_exclusions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not is_path_safe_slug(self.workflow):
            raise ValueError(
                "IsolationPolicy.workflow must be a non-empty, path-safe slug "
                f"(letters, digits, hyphen, underscore; no path separators or "
                f"leading dots), got {self.workflow!r}"
            )
        if not self.root.is_absolute():
            raise ValueError(f"IsolationPolicy.root must be absolute, got {self.root!r}")
        for entry in (*self.fold_scope, *self.fold_exclusions):
            if not _fold_fileset_entry_is_safe(entry):
                raise ValueError(
                    "IsolationPolicy fold_scope/fold_exclusions entry "
                    f"{entry!r} could escape the workspace root"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "workflow": self.workflow,
            "root": str(self.root),
            "reuse": self.reuse,
            "retain_on_failure": self.retain_on_failure,
            "fold_scope": self.fold_scope,
            "fold_exclusions": self.fold_exclusions,
        }


@dataclass(frozen=True, slots=True)
class IsolationLease:
    """A live, provisioned workspace.

    Yielded by ``IsolationSession.lease()`` and invalid after that context
    exits.

    Attributes:
        unit: The unit this backs.
        workspace_path: Where the agent works.
        workspace_name: jj workspace name (directory basename) — the
            ``<name>@`` revset the fold-back reads.
        checkout: Distinct type so a workspace path cannot be passed where
            a checkout is required (R9, FR-022).
        created_at: Injected, never ``datetime.now()`` inside the
            primitive — the clock seam 054 established.
    """

    unit: UnitOfWork
    workspace_path: Path
    workspace_name: str
    checkout: CheckoutPath
    created_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "unit": self.unit.to_dict(),
            "workspace_path": str(self.workspace_path),
            "workspace_name": self.workspace_name,
            "checkout": str(Path(self.checkout)),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class FoldBackResult:
    """The typed outcome FR-009 requires.

    Success, discard, conflict, and verification rejection must be
    distinguishable, and ``applied_paths`` must be reported.

    Attributes:
        outcome: See :class:`FoldBackOutcome`.
        applied_paths: Repo-relative posix paths written to the checkout.
        conflicting_paths: Populated only on ``CONFLICT``; never empty when
            it is (SC-005).
        restore_operation_id: The jj operation captured before the
            application — the undo handle.
        diagnostic: Human-readable; names conflicting paths on ``CONFLICT``.
        duration_seconds: Feeds the FR-050 budget assertion.
    """

    outcome: FoldBackOutcome
    applied_paths: tuple[str, ...] = ()
    conflicting_paths: tuple[str, ...] = ()
    restore_operation_id: str = ""
    diagnostic: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "applied_paths": self.applied_paths,
            "conflicting_paths": self.conflicting_paths,
            "restore_operation_id": self.restore_operation_id,
            "diagnostic": self.diagnostic,
            "duration_seconds": self.duration_seconds,
        }
