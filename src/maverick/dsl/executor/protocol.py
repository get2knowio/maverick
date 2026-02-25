"""StepExecutor @runtime_checkable Protocol — no provider-specific imports.

SC-004: This module has zero imports from maverick.agents or claude-agent-sdk.
Alternative provider adapters can implement StepExecutor by satisfying this
protocol alone.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from maverick.dsl.executor.config import StepExecutorConfig
from maverick.dsl.executor.result import ExecutorResult

# EventCallback is defined locally here to avoid a circular import:
#   protocol.py → handlers.base → context.py → protocol.py (TYPE_CHECKING)
# The definition mirrors
# maverick.dsl.serialization.executor.handlers.base.EventCallback.
EventCallback = Callable[[Any], Coroutine[Any, Any, None]]
"""Async callback for streaming events. Called with each ProgressEvent as it arrives."""


@runtime_checkable
class StepExecutor(Protocol):
    """Provider-agnostic protocol for executing agent steps (FR-001).

    A StepExecutor decouples workflow step execution from any specific AI
    provider. Implementations receive a prompt plus execution configuration
    and return a typed ExecutorResult.

    This protocol is async-only (Maverick async-first principle) and has no
    dependencies on provider-specific packages. Alternative provider adapters
    (OpenAI, local models, etc.) can implement this protocol without importing
    maverick.agents or claude-agent-sdk.

    Lifecycle:
        Created once per workflow run, reused across all agent steps.
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
            instructions: Optional system instructions override. None = use
                agent defaults.
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
