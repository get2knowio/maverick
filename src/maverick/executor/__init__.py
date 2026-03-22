"""StepExecutor protocol package — public API for maverick.executor.

Exports the complete public API for agent step execution:
- StepExecutor: Provider-agnostic @runtime_checkable Protocol
- AcpStepExecutor: ACP-based executor (primary)
- AgentProviderRegistry: ACP provider registry
- ExecutorResult, UsageMetadata: Result types
- StepExecutorConfig, RetryPolicy: Configuration types
- DEFAULT_EXECUTOR_CONFIG: Default 300s timeout config
"""

from __future__ import annotations

from maverick.executor.acp import AcpStepExecutor
from maverick.executor.config import (
    DEFAULT_EXECUTOR_CONFIG,
    IMPLEMENTER_AGENT_NAME,
    RetryPolicy,
    StepConfig,
    StepExecutorConfig,
)
from maverick.executor.errors import ExecutorError, OutputSchemaValidationError
from maverick.executor.protocol import EventCallback, StepExecutor
from maverick.executor.provider_registry import AgentProviderRegistry
from maverick.executor.result import ExecutorResult, UsageMetadata

__all__ = [
    "StepExecutor",
    "ExecutorResult",
    "StepConfig",
    "StepExecutorConfig",
    "RetryPolicy",
    "UsageMetadata",
    "AcpStepExecutor",
    "AgentProviderRegistry",
    "DEFAULT_EXECUTOR_CONFIG",
    "IMPLEMENTER_AGENT_NAME",
    "ExecutorError",
    "OutputSchemaValidationError",
    "EventCallback",
    "create_default_executor",
]


def create_default_executor() -> AcpStepExecutor:
    """Create an AcpStepExecutor with default config and registries.

    Loads the application config, builds an AgentProviderRegistry from
    ``config.agent_providers``, and constructs the default agent registry via
    ``create_registered_registry()``.

    Returns:
        A ready-to-use AcpStepExecutor instance.
    """
    from maverick.cli.common import create_registered_registry
    from maverick.config import load_config

    config = load_config()
    provider_registry = AgentProviderRegistry.from_config(config.agent_providers)
    registry = create_registered_registry()
    return AcpStepExecutor(
        provider_registry=provider_registry,
        agent_registry=registry,
        global_max_tokens=config.model.max_tokens,
    )
