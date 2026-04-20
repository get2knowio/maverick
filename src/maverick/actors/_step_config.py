"""Helpers for threading StepConfig through Thespian actor sessions."""

from __future__ import annotations

from typing import Any

from maverick.executor.config import StepConfig


def load_step_config(raw_config: StepConfig | dict[str, Any] | None) -> StepConfig | None:
    """Coerce a serialized config payload back into a StepConfig."""
    if raw_config is None:
        return None
    if isinstance(raw_config, StepConfig):
        return raw_config
    return StepConfig.model_validate(raw_config)


def step_config_with_timeout(config: StepConfig | None, timeout: int) -> StepConfig:
    """Return a StepConfig that preserves runtime overrides and sets timeout."""
    if config is None:
        return StepConfig(timeout=timeout)
    return config.model_copy(update={"timeout": timeout})


def step_allowed_tools(config: StepConfig | None) -> list[str] | None:
    """Return an actor's explicit tool allowlist, if configured."""
    if config is None:
        return None
    return config.allowed_tools
