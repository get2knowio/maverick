"""Agent result dataclasses.

This module defines AgentUsage and AgentResult dataclasses for representing
agent execution outcomes in a structured, type-safe manner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.exceptions import AgentError


@dataclass(frozen=True, slots=True)
class AgentUsage:
    """Usage statistics for agent execution (FR-014).

    This is an immutable value object that captures token usage, cost,
    and timing information from a Claude agent execution.

    Attributes:
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        total_cost_usd: Total cost in USD (may be None if unavailable).
        duration_ms: Execution duration in milliseconds.

    Example:
        ```python
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )
        print(f"Total tokens: {usage.total_tokens}")  # 300
        ```
    """

    input_tokens: int
    output_tokens: int
    total_cost_usd: float | None
    duration_ms: int

    def __post_init__(self) -> None:
        """Validate field values after initialization."""
        if self.input_tokens < 0:
            raise ValueError("input_tokens must be non-negative")
        if self.output_tokens < 0:
            raise ValueError("output_tokens must be non-negative")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if self.total_cost_usd is not None and self.total_cost_usd < 0:
            raise ValueError("total_cost_usd must be non-negative")

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output)."""
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Structured result from agent execution (FR-008).

    .. deprecated::
        Prefer agent-specific typed result models (e.g. ``FixerResult``,
        ``FixResult``, ``ImplementationResult``) which provide structured
        fields instead of opaque ``output: str``. ``AgentResult`` remains
        for agents that have not yet migrated to typed contracts.

    This is an immutable value object that represents the outcome of an
    agent's execute() method. It contains the success status, output text,
    any errors that occurred, usage statistics, and arbitrary metadata.

    Attributes:
        success: Whether execution succeeded.
        output: Text output from agent.
        metadata: Arbitrary metadata (session_id, etc.).
        errors: Errors encountered during execution.
        usage: Usage statistics.

    Example:
        ```python
        # Success case
        result = AgentResult.success_result(
            output="Analysis complete",
            usage=usage,
            metadata={"session_id": "abc123"},
        )

        # Failure case
        result = AgentResult.failure_result(
            errors=[AgentError("Something went wrong")],
            usage=usage,
        )
        ```
    """

    success: bool
    output: str
    usage: AgentUsage
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[AgentError] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate that failed results have at least one error."""
        if not self.success and not self.errors:
            raise ValueError("Failed results must have at least one error")

    @classmethod
    def success_result(
        cls,
        output: str,
        usage: AgentUsage,
        metadata: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Create a successful result.

        Args:
            output: Text output from agent.
            usage: Usage statistics.
            metadata: Optional metadata dictionary.

        Returns:
            AgentResult with success=True.
        """
        return cls(
            success=True,
            output=output,
            usage=usage,
            metadata=metadata or {},
            errors=[],
        )

    @classmethod
    def failure_result(
        cls,
        errors: list[AgentError],
        usage: AgentUsage,
        output: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentResult:
        """Create a failed result.

        Args:
            errors: List of errors (must have at least one).
            usage: Usage statistics.
            output: Optional partial output.
            metadata: Optional metadata dictionary.

        Returns:
            AgentResult with success=False.

        Raises:
            ValueError: If errors list is empty.
        """
        if not errors:
            raise ValueError("Failed results must have at least one error")
        return cls(
            success=False,
            output=output,
            usage=usage,
            metadata=metadata or {},
            errors=errors,
        )
