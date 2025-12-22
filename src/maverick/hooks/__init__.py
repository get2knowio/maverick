from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

from claude_agent_sdk import HookMatcher

from maverick.exceptions import HookConfigError, HookError, SafetyHookError
from maverick.hooks.config import HookConfig, LoggingConfig, MetricsConfig, SafetyConfig
from maverick.hooks.logging import log_tool_execution
from maverick.hooks.metrics import MetricsCollector, collect_metrics
from maverick.hooks.safety import validate_bash_command, validate_file_write
from maverick.hooks.types import (
    ToolExecutionLog,
    ToolMetricEntry,
    ToolMetrics,
    ValidationResult,
)


def create_safety_hooks(config: HookConfig | None = None) -> list[HookMatcher]:
    """Create safety hooks for PreToolUse validation (FR-001).

    Args:
        config: Optional hook configuration. Uses secure defaults if None.

    Returns:
        List of HookMatcher objects for PreToolUse event.

    Example:
        >>> from maverick.hooks import create_safety_hooks, HookConfig
        >>> hooks = create_safety_hooks(HookConfig())
        >>> # Use in ClaudeAgentOptions
        >>> options = ClaudeAgentOptions(
        ...     hooks={"PreToolUse": hooks}
        ... )
    """
    config = config or HookConfig()
    safety_config = config.safety
    hooks: list[HookMatcher] = []

    # Create bash validation hook if enabled
    if safety_config.bash_validation_enabled:
        bash_hook = partial(validate_bash_command, config=safety_config)
        hooks.append(
            HookMatcher(
                matcher="Bash",
                hooks=[bash_hook],  # type: ignore[list-item]
                timeout=float(safety_config.hook_timeout_seconds),
            )
        )

    # Create file write validation hook if enabled
    if safety_config.file_write_validation_enabled:
        file_write_hook = partial(validate_file_write, config=safety_config)
        # Match both Write and Edit tools
        hooks.append(
            HookMatcher(
                matcher="Write|Edit",
                hooks=[file_write_hook],  # type: ignore[list-item]
                timeout=float(safety_config.hook_timeout_seconds),
            )
        )

    return hooks


def create_logging_hooks(
    config: HookConfig | None = None,
    metrics_collector: MetricsCollector | None = None,
) -> list[HookMatcher]:
    """Create logging hooks for PostToolUse events (FR-002).

    Args:
        config: Optional hook configuration. Uses defaults if None.
        metrics_collector: Optional shared metrics collector. Created if None.

    Returns:
        List of HookMatcher objects for PostToolUse event.

    Example:
        >>> from maverick.hooks import create_logging_hooks, MetricsCollector
        >>> collector = MetricsCollector()
        >>> hooks = create_logging_hooks(metrics_collector=collector)
        >>> # Later: query metrics
        >>> metrics = await collector.get_metrics("Bash")
    """
    config = config or HookConfig()
    logging_config = config.logging
    metrics_config = config.metrics

    # Create internal collector if needed and metrics enabled
    if metrics_config.enabled and metrics_collector is None:
        metrics_collector = MetricsCollector(metrics_config)

    # Build list of hooks to apply
    hook_functions: list[Callable[..., Any]] = []

    if logging_config.enabled:
        logging_hook = partial(log_tool_execution, config=logging_config)
        hook_functions.append(logging_hook)

    if metrics_config.enabled and metrics_collector is not None:
        metrics_hook = partial(collect_metrics, collector=metrics_collector)
        hook_functions.append(metrics_hook)

    # Return single HookMatcher that matches all tools (matcher=None)
    if hook_functions:
        return [
            HookMatcher(
                matcher=None,  # Match all tools
                hooks=hook_functions,
                timeout=None,  # No timeout for logging/metrics
            )
        ]

    return []


# Public exports
__all__ = [
    # Factory functions
    "create_safety_hooks",
    "create_logging_hooks",
    # Configuration
    "HookConfig",
    "SafetyConfig",
    "LoggingConfig",
    "MetricsConfig",
    # Types
    "ValidationResult",
    "ToolExecutionLog",
    "ToolMetrics",
    "ToolMetricEntry",
    # Metrics collector
    "MetricsCollector",
    # Exceptions
    "HookError",
    "SafetyHookError",
    "HookConfigError",
]
