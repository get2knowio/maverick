"""Models for GenerateFlightPlanWorkflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FlightPlanOutput(BaseModel):
    """Agent output schema for flight-plan generation.

    Represents the structured output from the FlightPlanGeneratorAgent.
    Each field maps to a section of the Maverick flight plan format.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Kebab-case flight plan name")
    version: str = Field(default="1", description="Version string")
    objective: str = Field(description="High-level objective text")
    success_criteria: list[str] = Field(
        description="Success criteria texts (all unchecked)"
    )
    in_scope: list[str] = Field(description="Items explicitly in scope")
    out_of_scope: list[str] = Field(description="Items explicitly out of scope")
    boundaries: list[str] = Field(description="Scope boundary conditions")
    context: str = Field(default="", description="Background context")
    constraints: list[str] = Field(
        default_factory=list, description="Technical constraints"
    )
    notes: str = Field(default="", description="Additional notes")

    @field_validator("notes", mode="before")
    @classmethod
    def coerce_notes_list(cls, v: str | list[str]) -> str:
        """Accept a list of strings and join them into a single string."""
        if isinstance(v, list):
            return "\n".join(v)
        return v

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """Reject empty name."""
        if not v.strip():
            raise ValueError("name must not be empty")
        return v

    @field_validator("objective")
    @classmethod
    def objective_must_not_be_empty(cls, v: str) -> str:
        """Reject empty objective."""
        if not v.strip():
            raise ValueError("objective must not be empty")
        return v

    @field_validator("success_criteria")
    @classmethod
    def success_criteria_must_not_be_empty(cls, v: list[str]) -> list[str]:
        """Reject empty success_criteria list."""
        if not v:
            raise ValueError("success_criteria must not be empty")
        return v

    @field_validator("in_scope")
    @classmethod
    def in_scope_must_not_be_empty(cls, v: list[str]) -> list[str]:
        """Reject empty in_scope list."""
        if not v:
            raise ValueError("in_scope must not be empty")
        return v


@dataclass(frozen=True, slots=True)
class GenerateFlightPlanResult:
    """Final output from GenerateFlightPlanWorkflow.

    Attributes:
        flight_plan_path: Path to the written flight plan file.
        name: Flight plan name.
        success_criteria_count: Number of success criteria generated.
        validation_passed: Whether the generated plan passed validation.
    """

    flight_plan_path: str
    name: str
    success_criteria_count: int
    validation_passed: bool
    briefing_generated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dictionary for WorkflowResult.final_output."""
        return {
            "flight_plan_path": self.flight_plan_path,
            "name": self.name,
            "success_criteria_count": self.success_criteria_count,
            "validation_passed": self.validation_passed,
            "briefing_generated": self.briefing_generated,
        }
