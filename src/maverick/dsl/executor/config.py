"""StepExecutorConfig and RetryPolicy frozen dataclasses.

No maverick imports — stdlib only. SC-004 compliance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Canonical agent name used by the implementer step in DSL workflows.
IMPLEMENTER_AGENT_NAME = "implementer"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Tenacity retry parameters for executor-level retry (FR-003).

    Maps directly to tenacity:
        stop_after_attempt(max_attempts)
        wait_exponential(multiplier=1, min=wait_min, max=wait_max)

    Attributes:
        max_attempts: Maximum number of total attempts (initial + retries).
        wait_min: Minimum wait between retries in seconds.
        wait_max: Maximum wait between retries in seconds.
    """

    max_attempts: int = 3
    wait_min: float = 1.0
    wait_max: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "max_attempts": self.max_attempts,
            "wait_min": self.wait_min,
            "wait_max": self.wait_max,
        }


@dataclass(frozen=True, slots=True)
class StepExecutorConfig:
    """Per-step execution configuration (FR-003).

    All fields default to None, meaning "use provider/agent defaults". The
    executor only enforces a setting when it is explicitly non-None.

    Attributes:
        timeout: Timeout in seconds. None = provider default (300s recommended).
        retry_policy: When set, the executor applies this retry policy at the
            outermost scope; agent-level internal retries do not apply.
        model: Model identifier override (e.g. 'claude-opus-4-6'). None = inherit.
        temperature: Sampling temperature override. None = inherit.
        max_tokens: Max output tokens override. None = inherit.
    """

    timeout: int | None = None
    retry_policy: RetryPolicy | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "timeout": self.timeout,
            "retry_policy": self.retry_policy.to_dict() if self.retry_policy else None,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


DEFAULT_EXECUTOR_CONFIG = StepExecutorConfig(timeout=300)
"""Default executor config: 300s timeout, no model/retry overrides."""
