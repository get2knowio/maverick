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

from maverick.executor.config import StepConfig
from maverick.executor.result import ExecutorResult

# EventCallback is defined locally here to avoid a circular import:
#   protocol.py → handlers.base → context.py → protocol.py (TYPE_CHECKING)
# The definition mirrors
# maverick.executor.protocol.EventCallback.
EventCallback = Callable[[Any], Coroutine[Any, Any, None]]
"""Async callback for streaming events. Called with each ProgressEvent as it arrives."""


@runtime_checkable
class StepExecutor(Protocol):
    """Provider-agnostic protocol for executing agent steps.

    A StepExecutor decouples workflow step execution from any specific AI
    provider. Implementations receive a prompt plus execution configuration
    and return a typed ExecutorResult.

    This protocol is async-only (Maverick async-first principle) and has no
    dependencies on provider-specific packages. Alternative provider
    adapters (OpenAI, local models, etc.) can implement this protocol
    without importing :mod:`maverick.agents` or anything provider-specific.

    The canonical entry point is :meth:`execute_named` — callers pass
    the bundled persona name (e.g. ``"maverick.curator"``) plus the
    per-call user prompt, and the implementation routes through the
    OpenCode HTTP runtime.

    Lifecycle:
        Created once per workflow run, reused across all agent steps.
    """

    async def execute_named(
        self,
        *,
        agent: str,
        user_prompt: str,
        step_name: str = "execute_named",
        result_model: type[BaseModel] | None = None,
        cwd: Path | None = None,
        config: StepConfig | None = None,
        timeout: float | None = None,
    ) -> ExecutorResult:
        """Execute a bundled OpenCode markdown persona and return a typed result.

        Args:
            agent: Bundled persona name, e.g. ``"maverick.curator"``.
            user_prompt: The per-call user message body (already templated
                by the caller).
            step_name: Logical step name used for logging and for titling
                the OpenCode session.
            result_model: Optional Pydantic model to force structured
                output (``format=json_schema``). When ``None``, the
                assistant's plain text is returned.
            cwd: Optional working directory hint.
            config: Execution configuration (timeout, retry, provider /
                model overrides).
            timeout: Per-call wallclock budget (seconds).

        Returns:
            :class:`ExecutorResult` carrying either the validated payload
            (when ``result_model`` was set) or the plain-text response.

        Raises:
            OutputSchemaValidationError: ``result_model`` was set and the
                response payload didn't validate.
            AgentError: Agent execution failed.
        """
        ...
