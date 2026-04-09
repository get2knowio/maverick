"""ExecutorResult and UsageMetadata frozen dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.events import AgentStreamChunk


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    """Token/cost metadata from a model invocation (FR-002).

    Attributes:
        input_tokens: Tokens in the prompt.
        output_tokens: Tokens in the completion.
        cache_read_tokens: Tokens served from cache.
        cache_write_tokens: Tokens written to cache.
        total_cost_usd: Total cost in USD, if available from the provider.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_cost_usd": self.total_cost_usd,
        }


@dataclass(frozen=True, slots=True)
class ExecutorResult:
    """Typed result from StepExecutor.execute() (FR-002).

    Attributes:
        output: The agent's result. When output_schema was provided and validation
            succeeded, this is a validated Pydantic model instance. Otherwise
            it is the raw result from agent.execute().
        success: True if execution completed without errors.
        usage: Token/cost metadata, or None if the provider does not supply it.
        events: AgentStreamChunk events collected during streaming execution.
            Also forwarded in real-time via event_callback when provided.
    """

    output: Any
    success: bool
    usage: UsageMetadata | None
    events: tuple[AgentStreamChunk, ...]
    model_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "output": self.output,
            "success": self.success,
            "usage": self.usage.to_dict() if self.usage else None,
            "events": [e.to_dict() if hasattr(e, "to_dict") else str(e) for e in self.events],
        }
