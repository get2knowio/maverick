"""
StepExecutor Protocol Contract
================================

This file is the canonical interface contract for the StepExecutor protocol
(Feature 032). It defines the complete public API for the maverick.dsl.executor
package.

This contract is:
- Imported by unit tests to verify all implementations satisfy it
- Used as the implementation reference for both ClaudeStepExecutor and any
  future provider adapters
- Kept in sync with data-model.md

SC-002: A new provider adapter can be implemented by satisfying this contract
alone — no imports from maverick.agents or claude-agent-sdk required.
SC-004: The protocol and supporting types have no provider-specific dependencies.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ValidationError

# ---------------------------------------------------------------------------
# Public API exported from maverick.dsl.executor
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Tenacity retry parameters for executor-level retry (FR-003).

    Maps directly to tenacity:
        stop_after_attempt(max_attempts)
        wait_exponential(multiplier=1, min=wait_min, max=wait_max)

    Attributes:
        max_attempts: Maximum number of total attempts (initial + retries).
        wait_min: Minimum wait between retries in seconds.
        wait_max: Maximum wait between retries in seconds.
    """

    max_attempts: int = 3
    wait_min: float = 1.0
    wait_max: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "max_attempts": self.max_attempts,
            "wait_min": self.wait_min,
            "wait_max": self.wait_max,
        }


@dataclass(frozen=True, slots=True)
class StepExecutorConfig:
    """Per-step execution configuration (FR-003).

    All fields default to None, meaning "use provider/agent defaults". The
    executor only enforces a setting when it is explicitly non-None.

    Attributes:
        timeout: Timeout in seconds. None = provider default (300s recommended).
        retry_policy: When set, the executor applies this retry policy at the
            outermost scope; agent-level internal retries do not apply.
        model: Model identifier override (e.g. 'claude-opus-4-6'). None = inherit.
        temperature: Sampling temperature override. None = inherit.
        max_tokens: Max output tokens override. None = inherit.
    """

    timeout: int | None = None
    retry_policy: RetryPolicy | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "timeout": self.timeout,
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy else None,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


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


# NOTE: AgentStreamChunk is from maverick.dsl.events — used in ExecutorResult.events
# We use a forward reference here to keep this contract file self-contained
AgentStreamChunkType = Any  # type alias; real code uses AgentStreamChunk


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
    events: tuple[AgentStreamChunkType, ...]  # tuple for frozen-dataclass safety

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "output": self.output,
            "success": self.success,
            "usage": self.usage.to_dict() if self.usage else None,
            "events": [
                e.to_dict() if hasattr(e, "to_dict") else str(e) for e in self.events
            ],
        }


# ---------------------------------------------------------------------------
# EventCallback type alias (mirrors handlers/base.py definition)
# ---------------------------------------------------------------------------

EventCallback = Callable[
    [Any],  # ProgressEvent
    Coroutine[Any, Any, None],
]


# ---------------------------------------------------------------------------
# StepExecutor Protocol (FR-001)
# ---------------------------------------------------------------------------


@runtime_checkable
class StepExecutor(Protocol):
    """Provider-agnostic protocol for executing agent steps (FR-001).

    A StepExecutor decouples workflow step execution from any specific AI
    provider. Implementations receive a prompt plus execution configuration
    and return a typed ExecutorResult.

    This protocol is async-only (Maverick async-first principle) and has no
    dependencies on provider-specific packages. Alternative provider adapters
    can be implemented by satisfying this protocol without importing
    maverick.agents or claude-agent-sdk.

    Lifecycle:
        Created once per workflow run, reused across all agent steps.

    Implementation notes for new providers:
        - `prompt` is provider-defined. For Claude it is a rich Python object
          (ImplementerContext, etc.). For other providers it may be a string.
        - `agent_name` identifies the logical agent persona/capability.
        - `instructions` and `allowed_tools` are optional overrides; providers
          may use them or derive equivalents from agent_name.
        - Emit AgentStreamChunk events via event_callback as output is produced.
        - Validate output against output_schema using Pydantic; raise
          OutputSchemaValidationError on mismatch.
    """

    async def execute(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt: Any,
        instructions: str | None = None,
        allowed_tools: list[str] | None = None,
        cwd: Path | None = None,
        output_schema: type[BaseModel] | None = None,
        config: StepExecutorConfig | None = None,
        event_callback: EventCallback | None = None,
    ) -> ExecutorResult:
        """Execute an agent step and return a typed result.

        Args:
            step_name: DSL step name for observability logging.
            agent_name: Registered agent name (registry key or persona ID).
            prompt: Provider-specific context/prompt. For Claude: rich Python
                object (e.g. ImplementerContext). For generic providers: str.
            instructions: Optional system instructions override. None = use agent
                defaults.
            allowed_tools: Optional tool list override. None = use agent defaults.
            cwd: Working directory for file-system operations. None = cwd of
                caller (not recommended; always pass explicit cwd in workspaces).
            output_schema: Optional Pydantic BaseModel subclass. When provided,
                agent output is validated and ExecutorResult.output contains a
                validated instance on success.
            config: Execution configuration (timeout, retry, model overrides).
                None = use DEFAULT_EXECUTOR_CONFIG.
            event_callback: Async callback for streaming events. When provided,
                AgentStreamChunk events are forwarded in real-time as they arrive.

        Returns:
            ExecutorResult with output, success status, usage, and events.

        Raises:
            OutputSchemaValidationError: Agent output failed output_schema validation.
            ReferenceResolutionError: Agent not found in provider registry.
            AgentError: Agent execution failed (wraps provider-specific errors).
        """
        ...


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------


class ExecutorError(Exception):
    """Base class for StepExecutor errors."""


class OutputSchemaValidationError(ExecutorError):
    """Raised when agent output fails output_schema validation (FR-007).

    Attributes:
        step_name: Name of the DSL step that produced invalid output.
        schema_type: The Pydantic model class used for validation.
        validation_errors: The Pydantic ValidationError details.
    """

    def __init__(
        self,
        step_name: str,
        schema_type: type[BaseModel],
        validation_errors: ValidationError,
    ) -> None:
        self.step_name = step_name
        self.schema_type = schema_type
        self.validation_errors = validation_errors
        super().__init__(
            f"Step '{step_name}' output failed validation against "
            f"{schema_type.__name__}: {validation_errors}"
        )


# ---------------------------------------------------------------------------
# Default configuration constant
# ---------------------------------------------------------------------------

DEFAULT_EXECUTOR_CONFIG = StepExecutorConfig(timeout=300)
"""Default executor config: 300s timeout, no model/retry overrides."""
