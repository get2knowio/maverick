"""StepExecutor protocol package — public API for maverick.executor.

Exports the complete public API for agent step execution:
- StepExecutor: Provider-agnostic @runtime_checkable Protocol
- ClaudeStepExecutor: Claude Agent SDK adapter
- ExecutorResult, UsageMetadata: Result types
- StepExecutorConfig, RetryPolicy: Configuration types
- DEFAULT_EXECUTOR_CONFIG: Default 300s timeout config
"""

from __future__ import annotations

from maverick.executor.claude import ClaudeStepExecutor
from maverick.executor.config import (
    DEFAULT_EXECUTOR_CONFIG,
    IMPLEMENTER_AGENT_NAME,
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
    "ClaudeStepExecutor",
    "DEFAULT_EXECUTOR_CONFIG",
    "IMPLEMENTER_AGENT_NAME",
    "ExecutorError",
    "OutputSchemaValidationError",
    "EventCallback",
]
