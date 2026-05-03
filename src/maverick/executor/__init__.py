"""StepExecutor protocol package — public API for maverick.executor.

Exports the public surface for agent step execution under the OpenCode
runtime. The legacy :class:`AcpStepExecutor` and its supporting modules
(``acp.py``, ``acp_client.py``, ``_connection_pool.py``,
``_subprocess.py``, plus ``provider_registry.py`` for ACP provider
binaries and ``_model_resolver.py`` for ACP session model alias
resolution) were deleted in the OpenCode migration; the canonical
implementation now lives in
:class:`maverick.runtime.opencode.OpenCodeStepExecutor`.

Public API:

* :class:`StepExecutor`: Provider-agnostic ``@runtime_checkable`` Protocol.
* :class:`OpenCodeStepExecutor`: OpenCode-backed implementation.
* :class:`ExecutorResult`, :class:`UsageMetadata`: Result types.
* :class:`StepExecutorConfig`, :class:`RetryPolicy`, :class:`StepConfig`:
  Configuration types.
* :data:`DEFAULT_EXECUTOR_CONFIG`: Default 300s timeout config.
"""

from __future__ import annotations

from typing import Any

from maverick.executor.config import (
    DEFAULT_EXECUTOR_CONFIG,
    RetryPolicy,
    StepConfig,
    StepExecutorConfig,
)
from maverick.executor.errors import ExecutorError, OutputSchemaValidationError
from maverick.executor.protocol import EventCallback, StepExecutor
from maverick.executor.result import ExecutorResult, UsageMetadata

__all__ = [
    "StepExecutor",
    "ExecutorResult",
    "StepConfig",
    "StepExecutorConfig",
    "RetryPolicy",
    "UsageMetadata",
    "DEFAULT_EXECUTOR_CONFIG",
    "ExecutorError",
    "OutputSchemaValidationError",
    "EventCallback",
    "create_default_executor",
    "create_opencode_executor",
]


def create_default_executor(
    *,
    server_handle: Any = None,
) -> Any:
    """Return the default :class:`StepExecutor` (OpenCode-backed).

    Callers that need a custom server handle (e.g. when invoked inside
    an :func:`actor_pool` context) pass it via ``server_handle``;
    otherwise the executor lazily spawns its own OpenCode subprocess
    and tears it down on :meth:`cleanup`.
    """
    from maverick.config import load_config
    from maverick.runtime.opencode import OpenCodeStepExecutor

    config = load_config()
    return OpenCodeStepExecutor(
        global_max_tokens=config.model.max_tokens,
        server_handle=server_handle,
    )


# Alias retained for callers that explicitly want the OpenCode executor.
create_opencode_executor = create_default_executor
