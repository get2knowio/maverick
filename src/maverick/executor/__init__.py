"""StepExecutor protocol package — public API for maverick.executor.

Long-running personas go through typed-payload airframe agents in
:mod:`maverick.agents.personas`. The protocol types here are retained
so :class:`maverick.executor.config.StepConfig` keeps its existing
module path for callers that still build step-config dataclasses.

Public API:

* :class:`StepExecutor`: Provider-agnostic ``@runtime_checkable`` Protocol.
* :class:`ExecutorResult`, :class:`UsageMetadata`: Result types.
* :class:`StepExecutorConfig`, :class:`RetryPolicy`, :class:`StepConfig`:
  Configuration types.
* :data:`DEFAULT_EXECUTOR_CONFIG`: Default 300s timeout config.
"""

from __future__ import annotations

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
    "DEFAULT_EXECUTOR_CONFIG",
    "EventCallback",
    "ExecutorError",
    "ExecutorResult",
    "OutputSchemaValidationError",
    "RetryPolicy",
    "StepConfig",
    "StepExecutor",
    "StepExecutorConfig",
    "UsageMetadata",
]
