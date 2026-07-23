"""Frozen Pydantic models for the Spec Kit parsing layer.

See ``specs/048-speckit-refuel-ingestion/data-model.md`` for the field
rules these models encode.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TASK_ID_RE = re.compile(r"^T\d{3,}$")


class SpeckitTask(BaseModel):
    """One task line parsed from tasks.md."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(description="Matches T\\d{3,}; unique within the feature")
    description: str = Field(description="Full task text after markers")
    completed: bool = Field(description="[x] -> True, [ ] -> False")
    parallel: bool = Field(description="[P] marker present")
    story_id: str | None = Field(default=None, description="From [USn] marker")
    phase_number: int = Field(ge=1, description="Owning phase")
    file_paths: tuple[str, ...] = Field(
        default=(), description="Path tokens extracted from description"
    )
    explicit_deps: tuple[str, ...] = Field(
        default=(), description="Task IDs from 'depends on Txxx' notes"
    )
    line_number: int = Field(ge=1, description="1-based source line in tasks.md")

    @field_validator("task_id")
    @classmethod
    def _task_id_must_match_pattern(cls, v: str) -> str:
        if not _TASK_ID_RE.match(v):
            raise ValueError(f"task_id must match T\\d{{3,}}, got: {v!r}")
        return v

    @field_validator("description")
    @classmethod
    def _description_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be empty")
        return v


class SpeckitPhase(BaseModel):
    """A ``## Phase <n>: <title>`` section from tasks.md."""

    model_config = ConfigDict(frozen=True)

    number: int = Field(ge=1, description="From the phase heading; strictly increasing")
    title: str = Field(default="", description="Heading text after the colon")
    tasks: tuple[SpeckitTask, ...] = Field(default=(), description="In file order")


class ParsedSpec(BaseModel):
    """Extraction from spec.md."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(default="", description="From the H1; fallback handled by caller")
    success_criteria: tuple[str, ...] = Field(
        default=(), description="SC-\\d+ bullets under Success Criteria"
    )
    story_scenarios: dict[str, tuple[str, ...]] = Field(
        default_factory=dict,
        description="Key 'USn' -> that story's Acceptance Scenarios items",
    )


class SpeckitFeature(BaseModel):
    """Aggregate of one feature directory — the output of the parse step."""

    model_config = ConfigDict(frozen=True)

    feature_dir: Path = Field(description="Absolute resolved specs/NNN-name/")
    feature_name: str = Field(description="Directory basename")
    spec: ParsedSpec = Field(description="Required — spec.md must exist")
    phases: tuple[SpeckitPhase, ...] = Field(description="Required — tasks.md must exist")
    story_deps: tuple[tuple[str, str], ...] = Field(
        default=(), description="(dependent_story, blocker_story) pairs"
    )
    has_plan: bool = Field(default=False, description="plan.md present")


__all__ = [
    "ParsedSpec",
    "SpeckitFeature",
    "SpeckitPhase",
    "SpeckitTask",
]
