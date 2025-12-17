from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _default_sensitive_paths() -> list[str]:
    """Return default sensitive path patterns."""
    return [
        ".env",
        ".env.*",
        "secrets/",
        ".secrets/",
        "~/.ssh/",
        "~/.aws/",
        "~/.config/gcloud/",
        "/etc/",
        "/usr/",
        "/bin/",
        "/sbin/",
        "/root/",
    ]


class SafetyConfig(BaseModel):
    """Configuration for safety hooks.

    Attributes:
        bash_validation_enabled: Enable bash command validation.
        file_write_validation_enabled: Enable file write validation.
        bash_blocklist: Additional bash patterns to block.
        bash_allow_override: Patterns to allow (override defaults).
        sensitive_paths: Paths blocked for writes.
        path_allowlist: Paths to allow despite patterns.
        path_blocklist: Additional paths to block.
        fail_closed: Block on hook exception.
        hook_timeout_seconds: Per-hook timeout.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    bash_validation_enabled: bool = True
    file_write_validation_enabled: bool = True
    bash_blocklist: list[str] = Field(default_factory=list)
    bash_allow_override: list[str] = Field(default_factory=list)
    sensitive_paths: list[str] = Field(default_factory=_default_sensitive_paths)
    path_allowlist: list[str] = Field(default_factory=list)
    path_blocklist: list[str] = Field(default_factory=list)
    fail_closed: bool = True
    hook_timeout_seconds: int = Field(default=10, ge=1, le=120)

    @field_validator("bash_blocklist", "bash_allow_override", mode="after")
    @classmethod
    def validate_regex_patterns(cls, v: list[str]) -> list[str]:
        """Validate that all patterns are valid regex."""
        for pattern in v:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e
        return v


class LoggingConfig(BaseModel):
    """Configuration for logging hooks.

    Attributes:
        enabled: Enable execution logging.
        log_level: Python log level.
        output_destination: Logger name.
        sanitize_inputs: Sanitize sensitive data.
        max_output_length: Max output characters.
        sensitive_patterns: Additional patterns to sanitize.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    enabled: bool = True
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    output_destination: str = "maverick.hooks"
    sanitize_inputs: bool = True
    max_output_length: int = Field(default=1000, ge=100, le=10000)
    sensitive_patterns: list[str] = Field(default_factory=list)


class MetricsConfig(BaseModel):
    """Configuration for metrics collection.

    Attributes:
        enabled: Enable metrics collection.
        max_entries: Max entries in rolling window.
        time_window_seconds: Optional time-based window.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    enabled: bool = True
    max_entries: int = Field(default=10000, ge=100, le=1000000)
    time_window_seconds: int | None = Field(default=None, ge=60)


class HookConfig(BaseModel):
    """Root configuration for all hooks.

    Attributes:
        safety: Safety hook configuration.
        logging: Logging hook configuration.
        metrics: Metrics collection configuration.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
