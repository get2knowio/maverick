"""StepExecutor protocol package — public API for maverick.dsl.executor.

Exports the complete public API for agent step execution:
- StepExecutor: Provider-agnostic @runtime_checkable Protocol
- ClaudeStepExecutor: Claude Agent SDK adapter
- ExecutorResult, UsageMetadata: Result types
- StepExecutorConfig, RetryPolicy: Configuration types
- DEFAULT_EXECUTOR_CONFIG: Default 300s timeout config
"""

from __future__ import annotations

# ClaudeStepExecutor imported after protocol/result/config to avoid loading
# claude-agent-sdk at import time of the other lightweight modules.
from maverick.dsl.executor.claude import ClaudeStepExecutor
from maverick.dsl.executor.config import (
    DEFAULT_EXECUTOR_CONFIG,
    IMPLEMENTER_AGENT_NAME,
    RetryPolicy,
    StepExecutorConfig,
)
from maverick.dsl.executor.errors import ExecutorError, OutputSchemaValidationError
from maverick.dsl.executor.protocol import EventCallback, StepExecutor
from maverick.dsl.executor.result import ExecutorResult, UsageMetadata

__all__ = [
    "StepExecutor",
    "ExecutorResult",
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
