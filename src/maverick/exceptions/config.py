from __future__ import annotations

from typing import Any

from maverick.exceptions.base import MaverickError


class ConfigError(MaverickError):
    """Exception for configuration loading, parsing, and validation errors.

    Raised when configuration cannot be loaded, parsed, or validated. This includes
    YAML parsing failures, Pydantic validation errors, and invalid environment
    variable values.

    Attributes:
        message: Human-readable error message describing the configuration issue.
        field: Optional field name that caused the error (e.g., "api_key").
        value: Optional value that failed validation (for debugging).

    Examples:
        ```python
        # YAML parsing failure
        raise ConfigError(
            "Failed to parse maverick.yaml: invalid YAML syntax at line 10"
        )

        # Pydantic validation failure
        raise ConfigError(
            "Invalid configuration value",
            field="max_parallel_reviews",
            value=-1
        )

        # Invalid environment variable
        raise ConfigError(
            "Environment variable must be a valid URL",
            field="MAVERICK_API_URL",
            value="not-a-url"
        )
        ```
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        """Initialize the ConfigError.

        Args:
            message: Human-readable error message.
            field: Optional field name that caused the error.
            value: Optional value that failed validation.
        """
        self.field = field
        self.value = value
        super().__init__(message)
