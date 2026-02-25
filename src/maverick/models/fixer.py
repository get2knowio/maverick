"""FixerResult model for FixerAgent typed output.

This module defines the structured output contract for the FixerAgent,
replacing the opaque AgentResult.output string with typed fields.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FixerResult(BaseModel):
    """Typed output contract for FixerAgent.

    Replaces ``AgentResult`` with opaque ``output: str`` for the FixerAgent,
    providing structured fields that downstream workflows can inspect
    without string parsing.

    Attributes:
        success: Whether the fix attempt succeeded.
        summary: Human-readable description of what was done.
        files_mentioned: Best-effort list of files the agent mentioned
            modifying.  Not authoritative -- workflows use ``git diff``
            for ground truth.
        error_details: Error description when ``success`` is False.
            Must be non-empty when ``success`` is False.
    """

    model_config = ConfigDict(frozen=True)

    success: bool = Field(description="Whether the fix attempt succeeded")
    summary: str = Field(description="Human-readable description of what was done")
    files_mentioned: list[str] = Field(
        default_factory=list,
        description=(
            "Best-effort list of files the agent mentioned modifying. "
            "Not authoritative — workflows use git diff for ground truth."
        ),
    )
    error_details: str | None = Field(
        default=None,
        description="Error description if success=False",
    )

    @model_validator(mode="after")
    def _error_details_required_on_failure(self) -> FixerResult:
        """Validate that error_details is provided when success is False."""
        if not self.success and not self.error_details:
            raise ValueError("error_details must be non-empty when success is False")
        return self

    def to_dict(self) -> dict[str, object]:
        """Alias for ``model_dump()`` for backward compatibility."""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> FixerResult:
        """Alias for ``model_validate()`` for backward compatibility."""
        return cls.model_validate(data)
