"""Safety and logging hooks for Maverick agents.

NOTE: The hooks infrastructure was built for the claude-agent-sdk (HookMatcher).
With the migration to ACP-based execution, the HookMatcher concept no longer
applies. These functions are stubs that return empty lists for backwards
compatibility. The underlying safety/logging logic in the submodules is
preserved for future ACP hook integration.
"""

from __future__ import annotations

from typing import Any

from maverick.exceptions import HookConfigError, HookError, SafetyHookError
from maverick.hooks.config import HookConfig, LoggingConfig, MetricsConfig, SafetyConfig
from maverick.hooks.metrics import MetricsCollector
from maverick.hooks.types import (
    ToolExecutionLog,
    ToolMetricEntry,
    ToolMetrics,
    ValidationResult,
)


def create_safety_hooks(config: HookConfig | None = None) -> list[Any]:
    """Create safety hooks for PreToolUse validation.

    NOTE: Stubbed — HookMatcher (claude-agent-sdk) has been removed.
    Returns empty list for backwards compatibility.

    Args:
        config: Optional hook configuration (ignored).

    Returns:
        Empty list (no-op stub).
    """
    return []


def create_logging_hooks(
    config: HookConfig | None = None,
    metrics_collector: MetricsCollector | None = None,
) -> list[Any]:
    """Create logging hooks for PostToolUse events.

    NOTE: Stubbed — HookMatcher (claude-agent-sdk) has been removed.
    Returns empty list for backwards compatibility.

    Args:
        config: Optional hook configuration (ignored).
        metrics_collector: Optional metrics collector (ignored).

    Returns:
        Empty list (no-op stub).
    """
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
