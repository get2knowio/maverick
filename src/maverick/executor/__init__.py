"""Step configuration types.

This package's earlier ``StepExecutor`` Protocol and friends were
removed once long-running personas migrated to typed-payload airframe
agents in :mod:`maverick.agents.personas`. What remains is the
``StepConfig`` carrier still used at the workflow → actor boundary to
thread per-actor overrides (timeout, allowed_tools, prompt_suffix,
retry_policy) without leaking the airframe binding through the actor
shell.
"""

from __future__ import annotations

from maverick.executor.config import (
    DEFAULT_EXECUTOR_CONFIG,
    RetryPolicy,
    StepConfig,
    StepExecutorConfig,
)

__all__ = [
    "DEFAULT_EXECUTOR_CONFIG",
    "RetryPolicy",
    "StepConfig",
    "StepExecutorConfig",
]
