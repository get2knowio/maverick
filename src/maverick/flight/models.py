"""Frozen Pydantic models for Flight Plan and Work Unit documents.

Provides the canonical data model for the maverick.flight package:
- FlightPlan — master plan with objectives, success criteria, and scope
- WorkUnit — individual unit of work linked to a flight plan

All models use ConfigDict(frozen=True) to prevent accidental mutation.
Use model_copy(update={...}) to create modified instances.

Public API:
    SuccessCriterion, CompletionStatus, Scope, FlightPlan
    AcceptanceCriterion, FileScope, WorkUnit
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from maverick.logging import get_logger

logger = get_logger(__name__)

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TRACE_REF_RE = re.compile(r"^SC-[\w-]+(,\s*SC-[\w-]+)*$")
_TRACE_REF_RANGE_RE = re.compile(r"^SC-(\d+)\s+through\s+SC-(\d+)$", re.IGNORECASE)


def _normalize_trace_ref(v: str) -> str:
    """Normalize AI-generated trace_ref variants to canonical comma-separated form.

    Handles range notation like ``SC-1 through SC-14`` by expanding to
    ``SC-1, SC-2, ..., SC-14``.
    """
    m = _TRACE_REF_RANGE_RE.match(v.strip())
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        return ", ".join(f"SC-{i}" for i in range(start, end + 1))
    return v


# ---------------------------------------------------------------------------
# FlightPlan models
# ---------------------------------------------------------------------------


class SuccessCriterion(BaseModel):
    """A single success criterion for a Flight Plan.

    Attributes:
        text: Non-empty criterion text.
        checked: Whether this criterion is complete.
    """

    model_config = ConfigDict(frozen=True)

    text: str = Field(description="Criterion text")
    checked: bool = Field(description="Whether this criterion is checked")

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        """Reject empty text."""
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


class CompletionStatus(BaseModel):
    """Completion status derived from a FlightPlan's success criteria.

    Attributes:
        checked: Number of checked criteria.
        total: Total number of criteria.
        percentage: Checked/total*100, or None when total is zero.
    """

    model_config = ConfigDict(frozen=True)

    checked: int = Field(ge=0, description="Number of checked criteria")
    total: int = Field(ge=0, description="Total number of criteria")
    percentage: float | None = Field(description="Completion percentage (None if no criteria)")

    @field_validator("percentage")
    @classmethod
    def percentage_must_be_in_range(cls, v: float | None) -> float | None:
        """Validate that percentage is between 0.0 and 100.0 when set."""
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError(f"percentage must be between 0.0 and 100.0, got: {v}")
        return v


class Scope(BaseModel):
    """Scope definition for a Flight Plan.

    Attributes:
        in_scope: Items explicitly in scope.
        out_of_scope: Items explicitly out of scope.
        boundaries: Boundary conditions that define the scope.
    """

    model_config = ConfigDict(frozen=True)

    in_scope: tuple[str, ...] = Field(description="Items in scope")
    out_of_scope: tuple[str, ...] = Field(description="Items out of scope")
    boundaries: tuple[str, ...] = Field(description="Scope boundaries")


class FlightPlan(BaseModel):
    """Master plan describing objectives, success criteria, and scope.

    Attributes:
        name: Non-empty plan identifier (from YAML frontmatter).
        version: Non-empty version string (from YAML frontmatter).
        created: Creation date (from YAML frontmatter ``created``).
        tags: Classification tags (from YAML frontmatter ``tags``).
        objective: High-level objective text (from ``## Objective``).
        success_criteria: Measurable success criteria (from ``## Success Criteria``).
        scope: In/out-of-scope and boundary definitions (from ``## Scope``).
        context: Optional background context (from ``## Context``).
        constraints: Optional constraints list (from ``## Constraints``).
        notes: Optional additional notes (from ``## Notes``).
        source_path: Path to the source ``.md`` file, set by the loader.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Flight plan name")
    version: str = Field(description="Version string")
    created: date = Field(description="Creation date")
    tags: tuple[str, ...] = Field(description="Classification tags")
    depends_on_plans: tuple[str, ...] = Field(
        default=(),
        description="Names of flight plans this plan depends on",
    )
    objective: str = Field(description="Plan objective")
    success_criteria: tuple[SuccessCriterion, ...] = Field(description="Success criteria")
    scope: Scope = Field(description="Scope definition")
    context: str = Field(default="", description="Background context")
    constraints: tuple[str, ...] = Field(default=(), description="Constraints")
    verification_properties: str = Field(
        default="",
        description="Executable test code derived from success criteria",
    )
    notes: str = Field(default="", description="Additional notes")
    source_path: Path | None = Field(default=None, description="Source file path")

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """Reject empty name."""
        if not v.strip():
            raise ValueError("name must not be empty")
        return v

    @field_validator("version")
    @classmethod
    def version_must_not_be_empty(cls, v: str) -> str:
        """Reject empty version."""
        if not v.strip():
            raise ValueError("version must not be empty")
        return v

    @field_validator("objective")
    @classmethod
    def objective_must_not_be_empty(cls, v: str) -> str:
        """Reject empty objective."""
        if not v.strip():
            raise ValueError("objective must not be empty")
        return v

    @property
    def completion(self) -> CompletionStatus:
        """Compute completion status from success criteria.

        Returns:
            CompletionStatus with checked count, total count, and percentage.
            percentage is None when total == 0.
        """
        total = len(self.success_criteria)
        checked = sum(1 for c in self.success_criteria if c.checked)
        percentage: float | None = (checked / total * 100) if total > 0 else None
        return CompletionStatus(checked=checked, total=total, percentage=percentage)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the model to a JSON-compatible dictionary.

        Returns:
            Dict with all fields serialised:
            - date → ISO string
            - tuple → list
            - nested models → dict
            - Path → string or None
        """
        return {
            "name": self.name,
            "version": self.version,
            "created": self.created.isoformat(),
            "tags": list(self.tags),
            "depends_on_plans": list(self.depends_on_plans),
            "objective": self.objective,
            "success_criteria": [
                {"text": sc.text, "checked": sc.checked} for sc in self.success_criteria
            ],
            "scope": {
                "in_scope": list(self.scope.in_scope),
                "out_of_scope": list(self.scope.out_of_scope),
                "boundaries": list(self.scope.boundaries),
            },
            "context": self.context,
            "constraints": list(self.constraints),
            "notes": self.notes,
            "source_path": str(self.source_path) if self.source_path else None,
        }


# ---------------------------------------------------------------------------
# WorkUnit models
# ---------------------------------------------------------------------------


class AcceptanceCriterion(BaseModel):
    """A single acceptance criterion for a Work Unit.

    Attributes:
        text: Non-empty criterion text.
        trace_ref: Optional ``SC-###`` reference to a FlightPlan SuccessCriterion.
    """

    model_config = ConfigDict(frozen=True)

    text: str = Field(description="Criterion text")
    trace_ref: str | None = Field(default=None, description="Optional SC-### trace reference")

    @field_validator("text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        """Reject empty text."""
        if not v.strip():
            raise ValueError("text must not be empty")
        return v

    @field_validator("trace_ref")
    @classmethod
    def trace_ref_must_match_format(cls, v: str | None) -> str | None:
        """Validate that trace_ref matches SC-\\d+ format when set.

        Empty string and whitespace-only string normalise to ``None``
        (i.e. "no trace ref"). Some agents emit ``""`` for "I have
        nothing to trace this to" instead of omitting the field; treating
        that as ``None`` lets the model accept the payload instead of
        crashing the validator (which used to surface only as a generic
        ``error_type="other"`` and burn fix rounds).
        """
        if v is None:
            return None
        if not v.strip():
            return None
        v = _normalize_trace_ref(v)
        if not _TRACE_REF_RE.match(v):
            raise ValueError(f"trace_ref must match SC-<id> format, got: {v!r}")
        return v


class FileScope(BaseModel):
    """File scope for a Work Unit — which files to create, modify, or protect.

    Attributes:
        create: Files to create.
        modify: Files to modify.
        protect: Files that must not be changed.
    """

    model_config = ConfigDict(frozen=True)

    create: tuple[str, ...] = Field(description="Files to create")
    modify: tuple[str, ...] = Field(description="Files to modify")
    protect: tuple[str, ...] = Field(description="Files to protect")


class WorkUnit(BaseModel):
    """A single unit of work linked to a Flight Plan.

    Attributes:
        id: Kebab-case work unit identifier.
        flight_plan: Non-empty name of the parent FlightPlan.
        sequence: Positive execution sequence number (>= 1).
        parallel_group: Optional group label for parallel execution.
        depends_on: IDs of work units that must complete first.
        task: Task description text.
        acceptance_criteria: Measurable acceptance criteria.
        file_scope: Files to create, modify, and protect.
        instructions: Implementation instructions.
        verification: Verification command strings.
        provider_hints: Optional hints for the implementation agent.
        source_path: Path to the source ``.md`` file, set by the loader.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Kebab-case work unit ID")
    flight_plan: str = Field(description="Parent flight plan name")
    sequence: int = Field(description="Positive execution sequence number")
    parallel_group: str | None = Field(
        default=None, description="Optional parallel execution group"
    )
    depends_on: tuple[str, ...] = Field(default=(), description="IDs of prerequisite work units")
    task: str = Field(description="Task description")
    acceptance_criteria: tuple[AcceptanceCriterion, ...] = Field(description="Acceptance criteria")
    file_scope: FileScope = Field(description="File scope definition")
    instructions: str = Field(description="Implementation instructions")
    test_specification: str = Field(
        default="", description="Failing test the implementer must make pass"
    )
    verification: tuple[str, ...] = Field(description="Verification commands")
    provider_hints: str | None = Field(
        default=None, description="Optional hints for the implementation agent"
    )
    source_path: Path | None = Field(default=None, description="Source file path")
    # Decomposer-assigned tier hint for downstream model routing.
    # ``None`` = decomposer did not classify (older runs / fallback).
    # Phase 1: persisted in the work-unit markdown frontmatter only.
    # Phase 2: ``steps.implement.tiers`` will route per complexity.
    complexity: Literal["trivial", "simple", "moderate", "complex"] | None = Field(
        default=None,
        description=(
            "How much model intelligence this bead needs. trivial / simple / "
            "moderate / complex. None = unclassified."
        ),
    )

    @field_validator("id")
    @classmethod
    def id_must_be_kebab_case(cls, v: str) -> str:
        """Validate that id matches kebab-case pattern."""
        if not _KEBAB_RE.match(v):
            raise ValueError(
                f"id must match kebab-case pattern ^[a-z0-9]+(-[a-z0-9]+)*$, got: {v!r}"
            )
        return v

    @field_validator("depends_on")
    @classmethod
    def depends_on_must_be_kebab_case(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        """Validate that each depends_on entry matches kebab-case pattern."""
        for entry in v:
            if not _KEBAB_RE.match(entry):
                raise ValueError(
                    f"depends_on entries must match kebab-case pattern "
                    f"^[a-z0-9]+(-[a-z0-9]+)*$, got: {entry!r}"
                )
        return v

    @field_validator("sequence")
    @classmethod
    def sequence_must_be_positive(cls, v: int) -> int:
        """Validate that sequence is >= 1."""
        if v < 1:
            raise ValueError(f"sequence must be >= 1, got: {v}")
        return v

    @field_validator("flight_plan")
    @classmethod
    def flight_plan_must_not_be_empty(cls, v: str) -> str:
        """Reject empty flight_plan."""
        if not v.strip():
            raise ValueError("flight_plan must not be empty")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Serialize the model to a JSON-compatible dictionary.

        Returns:
            Dict with all fields serialised:
            - tuple → list
            - nested models → dict
            - Path → string or None
        """
        return {
            "id": self.id,
            "flight_plan": self.flight_plan,
            "sequence": self.sequence,
            "parallel_group": self.parallel_group,
            "depends_on": list(self.depends_on),
            "task": self.task,
            "acceptance_criteria": [
                {"text": ac.text, "trace_ref": ac.trace_ref} for ac in self.acceptance_criteria
            ],
            "file_scope": {
                "create": list(self.file_scope.create),
                "modify": list(self.file_scope.modify),
                "protect": list(self.file_scope.protect),
            },
            "instructions": self.instructions,
            "verification": list(self.verification),
            "provider_hints": self.provider_hints,
            "source_path": str(self.source_path) if self.source_path else None,
        }


# ---------------------------------------------------------------------------
# Resolver models
# ---------------------------------------------------------------------------


class ExecutionBatch(BaseModel):
    """A batch of work units that can execute concurrently.

    Units within a batch share the same dependency tier and optionally the
    same ``parallel_group``. All units in a batch can start once the
    preceding batch completes.

    Attributes:
        units: Work units that belong to this batch.
        parallel_group: Shared parallel group ID, or ``None`` for ungrouped.
    """

    model_config = ConfigDict(frozen=True)

    units: tuple[WorkUnit, ...] = Field(description="Work units in this batch")
    parallel_group: str | None = Field(default=None, description="Shared parallel group ID")

    @field_validator("units")
    @classmethod
    def units_must_not_be_empty(cls, v: tuple[WorkUnit, ...]) -> tuple[WorkUnit, ...]:
        """Reject empty units tuple."""
        if not v:
            raise ValueError("units must not be empty")
        return v


class ExecutionOrder(BaseModel):
    """Topologically sorted sequence of execution batches.

    Produced by :func:`resolve_execution_order`. Each batch in ``batches``
    must complete before the next batch begins. Units within a single batch
    are safe to run concurrently.

    Attributes:
        batches: Ordered tuple of :class:`ExecutionBatch` instances.
    """

    model_config = ConfigDict(frozen=True)

    batches: tuple[ExecutionBatch, ...] = Field(description="Ordered execution batches")


__all__ = [
    "AcceptanceCriterion",
    "CompletionStatus",
    "ExecutionBatch",
    "ExecutionOrder",
    "FileScope",
    "FlightPlan",
    "Scope",
    "SuccessCriterion",
    "WorkUnit",
]
