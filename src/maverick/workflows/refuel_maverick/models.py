"""Models for RefuelMaverickWorkflow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class FileScopeSpec(BaseModel):
    """File scope spec produced by the decomposition agent."""

    model_config = ConfigDict(frozen=True)

    create: list[str] = Field(default_factory=list)
    modify: list[str] = Field(default_factory=list)
    protect: list[str] = Field(default_factory=list)


class AcceptanceCriterionSpec(BaseModel):
    """Acceptance criterion spec produced by the decomposition agent."""

    model_config = ConfigDict(frozen=True)

    text: str
    trace_ref: str | None = None


class WorkUnitSpec(BaseModel):
    """Lightweight work unit specification produced by the decomposition agent.

    This is a subset of WorkUnit fields - excludes loader-specific fields
    (source_path, flight_plan) and provider_hints.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Kebab-case identifier")
    sequence: int = Field(ge=1, description="Execution order (>= 1)")
    parallel_group: str | None = Field(default=None)
    depends_on: list[str] = Field(default_factory=list)
    task: str = Field(description="Task description")
    acceptance_criteria: list[AcceptanceCriterionSpec] = Field(default_factory=list)
    file_scope: FileScopeSpec = Field(default_factory=FileScopeSpec)
    instructions: str = Field(default="")
    test_specification: str = Field(default="")
    verification: list[str] = Field(default_factory=list)
    # Decomposer-assigned hint for tier routing (Phase 2 will use this).
    # ``None`` = decomposer did not classify (older runs / fallback).
    complexity: Literal["trivial", "simple", "moderate", "complex"] | None = Field(
        default=None,
        description=(
            "How much model intelligence this bead needs. Set by the "
            "decomposer at outline time. Phase 1: displayed only, no "
            "routing impact. Phase 2: maps to a model tier in "
            "steps.implement.tiers."
        ),
    )

    @field_validator("id")
    @classmethod
    def id_must_be_kebab_case(cls, v: str) -> str:
        """Validate that id matches kebab-case pattern."""
        if not _KEBAB_RE.match(v):
            raise ValueError(f"id must be kebab-case, got: {v!r}")
        return v

    @field_validator("task")
    @classmethod
    def task_must_not_be_empty(cls, v: str) -> str:
        """Reject empty task."""
        if not v.strip():
            raise ValueError("task must not be empty")
        return v

    @field_validator("verification")
    @classmethod
    def verification_must_not_be_empty(cls, v: list[str]) -> list[str]:
        """Reject empty verification list."""
        if not v:
            raise ValueError("verification must not be empty")
        return v


class DecompositionOutput(BaseModel):
    """Agent output schema — the structured result from the decomposition agent step."""

    model_config = ConfigDict(frozen=True)

    work_units: list[WorkUnitSpec] = Field(description="Ordered list of work unit specifications")
    rationale: str = Field(description="Agent's reasoning for the decomposition")

    @field_validator("work_units")
    @classmethod
    def work_units_must_not_be_empty(cls, v: list[WorkUnitSpec]) -> list[WorkUnitSpec]:
        """Reject empty work_units list."""
        if not v:
            raise ValueError("work_units must not be empty")
        return v

    @model_validator(mode="after")
    def work_unit_ids_must_be_unique(self) -> DecompositionOutput:
        """Validate that all work unit IDs are unique."""
        ids = [wu.id for wu in self.work_units]
        seen: set[str] = set()
        for wuid in ids:
            if wuid in seen:
                raise ValueError(f"Duplicate work unit ID: {wuid!r}")
            seen.add(wuid)
        return self


# ---------------------------------------------------------------------------
# Chunked decomposition models (outline → detail)
# ---------------------------------------------------------------------------


class WorkUnitOutline(BaseModel):
    """Lightweight work unit produced by the outline pass.

    Contains structural information (ID, task, dependencies, file scope) but
    omits large text fields (instructions, acceptance_criteria, verification)
    to fit within the output token window.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Kebab-case identifier")
    sequence: int = Field(ge=1, description="Execution order (>= 1)")
    parallel_group: str | None = Field(default=None)
    depends_on: list[str] = Field(default_factory=list)
    task: str = Field(description="Task description")
    file_scope: FileScopeSpec = Field(default_factory=FileScopeSpec)

    @field_validator("id")
    @classmethod
    def id_must_be_kebab_case(cls, v: str) -> str:
        """Validate that id matches kebab-case pattern."""
        if not _KEBAB_RE.match(v):
            raise ValueError(f"id must be kebab-case, got: {v!r}")
        return v

    @field_validator("task")
    @classmethod
    def task_must_not_be_empty(cls, v: str) -> str:
        """Reject empty task."""
        if not v.strip():
            raise ValueError("task must not be empty")
        return v


class DecompositionOutline(BaseModel):
    """Agent output schema for the outline pass of chunked decomposition.

    Contains a lightweight list of work unit skeletons (IDs, tasks,
    dependencies, file scopes) plus the decomposition rationale. Designed
    to always fit within the output token window even for large flight plans.
    """

    model_config = ConfigDict(frozen=True)

    work_units: list[WorkUnitOutline] = Field(description="Ordered list of work unit outlines")
    rationale: str = Field(description="Agent's reasoning for the decomposition")

    @field_validator("work_units")
    @classmethod
    def work_units_must_not_be_empty(
        cls,
        v: list[WorkUnitOutline],
    ) -> list[WorkUnitOutline]:
        """Reject empty work_units list."""
        if not v:
            raise ValueError("work_units must not be empty")
        return v

    @model_validator(mode="after")
    def work_unit_ids_must_be_unique(self) -> DecompositionOutline:
        """Validate that all work unit IDs are unique."""
        ids = [wu.id for wu in self.work_units]
        seen: set[str] = set()
        for wuid in ids:
            if wuid in seen:
                raise ValueError(f"Duplicate work unit ID: {wuid!r}")
            seen.add(wuid)
        return self


class WorkUnitDetail(BaseModel):
    """Detailed fields for a single work unit produced by the detail pass.

    Keyed by ``id`` to merge with the corresponding ``WorkUnitOutline``.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Must match a WorkUnitOutline.id")
    instructions: str = Field(description="Implementation guidance")
    test_specification: str = Field(default="")
    acceptance_criteria: list[AcceptanceCriterionSpec] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)

    @field_validator("verification")
    @classmethod
    def verification_must_not_be_empty(cls, v: list[str]) -> list[str]:
        """Reject empty verification list."""
        if not v:
            raise ValueError("verification must not be empty")
        return v


class DetailBatchOutput(BaseModel):
    """Agent output schema for a detail pass batch."""

    model_config = ConfigDict(frozen=True)

    details: list[WorkUnitDetail] = Field(
        description="Detail entries for the requested work units"
    )


@dataclass(frozen=True, slots=True)
class RefuelMaverickResult:
    """Final output from RefuelMaverickWorkflow.

    Attributes:
        work_units_written: Count of work unit files written.
        work_units_dir: Output directory path string.
        epic: Created epic bead info dict (None on failure).
        work_beads: Tuple of created work bead dicts.
        dependencies: Tuple of wired dependency dicts.
        errors: Collected non-fatal errors.
        coverage_warnings: SC coverage warnings (non-blocking).
    """

    work_units_written: int
    work_units_dir: str
    epic: dict[str, Any] | None
    work_beads: tuple[dict[str, Any], ...]
    dependencies: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]
    coverage_warnings: tuple[str, ...]
    run_id: str = ""
    briefing_path: str | None = None
    cross_plan_deps: tuple[dict[str, Any], ...] = ()
    cross_plan_dep_errors: tuple[str, ...] = ()
    suggested_cross_plan_deps: tuple[str, ...] = ()
    open_bead_overlap_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary for WorkflowResult.final_output."""
        return {
            "work_units_written": self.work_units_written,
            "work_units_dir": self.work_units_dir,
            "epic": self.epic,
            "work_beads": list(self.work_beads),
            "dependencies": list(self.dependencies),
            "errors": list(self.errors),
            "coverage_warnings": list(self.coverage_warnings),
            "run_id": self.run_id,
            "briefing_path": self.briefing_path,
            "cross_plan_deps": list(self.cross_plan_deps),
            "cross_plan_dep_errors": list(self.cross_plan_dep_errors),
            "suggested_cross_plan_deps": list(self.suggested_cross_plan_deps),
            "open_bead_overlap_count": self.open_bead_overlap_count,
        }
