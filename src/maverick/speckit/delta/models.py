"""Frozen Pydantic models for the delta document layer.

See ``specs/059-spec-delta-layer/data-model.md`` "Delta document layer" /
"Impact layer" for the field rules these models encode, and
``contracts/delta-document-format.md`` for the grammar they represent.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maverick.speckit.models import (
    _TASK_ID_RE,  # noqa: SLF001 -- reuse, not reimplement (Guardrail 5)
)
from maverick.speckit.requirements import (
    _REQ_ID_RE,  # noqa: SLF001 -- reuse, not reimplement (Guardrail 5)
)


class DeltaOperation(StrEnum):
    """The four requirement operations a delta document may express
    (FR-001). The value is the literal section keyword in the document —
    a contract string, not an implementation detail."""

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    REMOVED = "REMOVED"
    RENAMED = "RENAMED"


#: Apply order (FR-004a) — a module constant, deliberately NOT enum
#: declaration order, so reordering the enum's members can never
#: silently reorder how a delta applies. Rename first so later
#: operations address the new id; remove before modify so a removed
#: requirement is not first rewritten; add last so a new id cannot
#: collide with one still being removed in the same pass.
OPERATION_ORDER: tuple[DeltaOperation, ...] = (
    DeltaOperation.RENAMED,
    DeltaOperation.REMOVED,
    DeltaOperation.MODIFIED,
    DeltaOperation.ADDED,
)

#: The content-loss guard's shrink threshold (FR-005d) — pinned by both
#: SC-008 (catches truncation) and SC-008a (does not fire on ordinary
#: tightening). A fixed contract constant, never configurable: a tunable
#: guard is one an author turns down the first time it is inconvenient,
#: which is exactly when it is working.
SHRINK_FLOOR: float = 0.6


def _validate_req_id(v: str) -> str:
    if not _REQ_ID_RE.match(v):
        raise ValueError(f"requirement id must match FR-\\d{{3}}[a-z]?, got: {v!r}")
    return v


def _validate_task_id(v: str) -> str:
    if not _TASK_ID_RE.match(v):
        raise ValueError(f"task id must match T\\d{{3,}}, got: {v!r}")
    return v


class RequirementEntry(BaseModel):
    """One ``## <OPERATION> <FR-id>`` section of a delta document.

    ``before``/``after`` are always a **complete** verbatim requirement
    block, never a diff or partial excerpt (FR-002) — a partial excerpt's
    documented failure mode is silently dropping whatever it omits.
    """

    model_config = ConfigDict(frozen=True)

    operation: DeltaOperation
    req_id: str = Field(description="For RENAMED, the *old* id")
    new_req_id: str | None = Field(default=None, description="RENAMED only")
    before: str | None = Field(default=None, description="MODIFIED, REMOVED — verbatim block")
    after: str | None = Field(default=None, description="MODIFIED, ADDED — verbatim block")
    shrink_intended: bool = Field(
        default=False, description="MODIFIED only; the per-entry guard opt-out (FR-005e)"
    )
    line_number: int = Field(ge=1, description="For error messages")

    @model_validator(mode="after")
    def _validate_ids(self) -> RequirementEntry:
        _validate_req_id(self.req_id)
        if self.new_req_id is not None:
            _validate_req_id(self.new_req_id)
        return self

    @model_validator(mode="after")
    def _validate_presence_by_operation(self) -> RequirementEntry:
        op = self.operation
        if op is DeltaOperation.ADDED:
            if self.before is not None:
                raise ValueError("ADDED must not carry a 'before' block")
            if self.after is None:
                raise ValueError("ADDED must carry an 'after' block")
            if self.new_req_id is not None:
                raise ValueError("ADDED must not carry a new_req_id")
        elif op is DeltaOperation.MODIFIED:
            if self.before is None or self.after is None:
                raise ValueError("MODIFIED must carry both 'before' and 'after' blocks")
            if self.new_req_id is not None:
                raise ValueError("MODIFIED must not carry a new_req_id")
        elif op is DeltaOperation.REMOVED:
            if self.before is None:
                raise ValueError("REMOVED must carry a 'before' block")
            if self.after is not None:
                raise ValueError("REMOVED must not carry an 'after' block")
            if self.new_req_id is not None:
                raise ValueError("REMOVED must not carry a new_req_id")
            if self.shrink_intended:
                raise ValueError("shrink_intended only applies to MODIFIED")
        elif op is DeltaOperation.RENAMED:
            if self.before is not None or self.after is not None:
                raise ValueError("RENAMED must carry neither 'before' nor 'after'")
            if self.new_req_id is None:
                raise ValueError("RENAMED must carry a new_req_id (the TO id)")
            if self.shrink_intended:
                raise ValueError("shrink_intended only applies to MODIFIED")
        if op is not DeltaOperation.MODIFIED and self.shrink_intended:
            raise ValueError("shrink_intended only applies to MODIFIED")
        return self


class TaskEntry(BaseModel):
    """One ``## TASKS`` line. Stated by the author, never derived from a
    :class:`RequirementEntry` (FR-007a) — requirement-to-task coverage is
    6.4% in this corpus and cannot be inferred."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["added", "withdrawn"]
    task_id: str = Field(description="Validated ^T\\d{3,}$")
    line: str | None = Field(default=None, description="The full task line, 'added' only")
    line_number: int = Field(default=1, ge=1, description="For error messages")

    @model_validator(mode="after")
    def _validate(self) -> TaskEntry:
        _validate_task_id(self.task_id)
        if self.kind == "added" and self.line is None:
            raise ValueError("an 'added' task entry must carry its full task line")
        if self.kind == "withdrawn" and self.line is not None:
            raise ValueError("a 'withdrawn' task entry must not carry a task line")
        return self


class DeltaDocument(BaseModel):
    """A parsed delta document — the unit ``delta validate``/``apply`` act on."""

    model_config = ConfigDict(frozen=True)

    path: Path = Field(description="Where it was read from — decides pending vs. applied")
    title: str = Field(description="From the '# Delta: ...' heading")
    target_feature: str = Field(description="Resolved through detect.resolve_feature")
    requirement_entries: tuple[RequirementEntry, ...] = Field(default=(), description="File order")
    task_entries: tuple[TaskEntry, ...] = Field(default=(), description="File order")
    sequence: int = Field(ge=0, description="Numeric filename prefix; archive ordering")

    @property
    def is_applied(self) -> bool:
        """Location is the state, never a marker inside the document (FR-023)."""
        return self.path.parent.name == "archive"

    @property
    def is_empty(self) -> bool:
        """FR-005: both entry tuples empty -> rejected at validation.

        A delta with requirement entries and no task entries is *not*
        empty and applies quietly (FR-007b) — the dominant corpus shape.
        """
        return not self.requirement_entries and not self.task_entries


class Impact(BaseModel):
    """A collision between a ``WITHDRAWN``/``ADDED`` task entry and
    existing bead work, detected before any apply rewrite.

    Every constructed :class:`Impact` blocks the apply by construction —
    ``impacts.py`` never builds one for an open, unstarted bead (that is
    the clean case a later ``refuel --speckit`` simply closes with no
    fuss). ``task_id`` is empty only for ``reason="unstamped"``: the
    research R7 hazard is a bead under the epic carrying no recorded
    task identity at all, so there is no task id to attribute it to —
    it is still reported, never closed and never ignored (FR-020).
    """

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(default="", description="Empty only when reason is 'unstamped'")
    bead_id: str
    bead_status: str
    reason: Literal["in-flight", "closed", "unstamped"]

    @model_validator(mode="after")
    def _validate(self) -> Impact:
        if self.reason != "unstamped" and not self.task_id:
            raise ValueError("task_id is required unless reason is 'unstamped'")
        return self


class Acknowledgement(BaseModel):
    """An impact's state *at the time it was cleared* (FR-015a) — so the
    archive answers "what was knowingly overridden", not merely "an
    override happened"."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    bead_id: str
    bead_status: str
    acknowledged_at: str = Field(description="UTC ISO-8601")


class ApplicationRecord(BaseModel):
    """Appended to a delta document as it moves to ``deltas/archive/``
    (FR-022) — the archive is readable without any other source."""

    model_config = ConfigDict(frozen=True)

    applied_at: str = Field(description="UTC ISO-8601")
    counts: dict[str, int] = Field(description="Per operation, all four keys, zeros included")
    task_counts: dict[str, int] = Field(description="'added' / 'withdrawn' keys")
    acknowledgements: tuple[Acknowledgement, ...] = Field(default=())
    shrink_intended_ids: tuple[str, ...] = Field(
        default=(), description="Which reductions were *declared* rather than caught (FR-005e)"
    )


__all__ = [
    "SHRINK_FLOOR",
    "Acknowledgement",
    "ApplicationRecord",
    "DeltaDocument",
    "DeltaOperation",
    "Impact",
    "OPERATION_ORDER",
    "RequirementEntry",
    "TaskEntry",
]
