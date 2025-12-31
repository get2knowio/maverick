"""Init command exception hierarchy.

This module provides exception classes for the maverick init command,
including prerequisite failures, detection errors, and configuration issues.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from maverick.exceptions.base import MaverickError

if TYPE_CHECKING:
    from maverick.init.models import PrerequisiteCheck

__all__ = [
    "InitError",
    "PrerequisiteError",
    "DetectionError",
    "ConfigExistsError",
    "ConfigWriteError",
    "AnthropicAPIError",
]


class InitError(MaverickError):
    """Base exception for init command errors.

    This is the root of the init exception hierarchy. All init-specific
    exceptions inherit from this class, allowing callers to catch all
    init-related errors at CLI boundaries.

    Attributes:
        message: Human-readable error message describing what went wrong.

    Example:
        ```python
        try:
            await run_init(project_path=Path.cwd())
        except InitError as e:
            logger.error(f"Init failed: {e.message}")
            sys.exit(1)
        ```
    """


class PrerequisiteError(InitError):
    """A required prerequisite check failed.

    Raised when a prerequisite validation (git installed, in git repo,
    gh installed, gh authenticated, API key set, API accessible) fails.

    Attributes:
        check: The PrerequisiteCheck that failed.
        message: Human-readable error message.

    Example:
        ```python
        if not check.passed:
            raise PrerequisiteError(check)
        ```
    """

    def __init__(
        self,
        check: PrerequisiteCheck,
        message: str | None = None,
    ) -> None:
        """Initialize the PrerequisiteError.

        Args:
            check: The PrerequisiteCheck that failed.
            message: Optional override message. If not provided,
                uses the check's message.
        """
        self.check = check
        super().__init__(message or check.message)


class DetectionError(InitError):
    """Project type detection failed.

    Raised when project type detection fails, either due to Claude API
    errors or inability to determine project type from markers.

    Attributes:
        message: Human-readable error message.
        claude_error: Optional underlying Claude API exception.

    Example:
        ```python
        try:
            result = await detect_project_type(path)
        except anthropic.APIError as e:
            raise DetectionError(
                "Failed to detect project type",
                claude_error=e,
            )
        ```
    """

    def __init__(
        self,
        message: str,
        *,
        claude_error: Exception | None = None,
    ) -> None:
        """Initialize the DetectionError.

        Args:
            message: Human-readable error message.
            claude_error: Optional underlying Claude API exception.
        """
        self.claude_error = claude_error
        super().__init__(message)


class ConfigExistsError(InitError):
    """maverick.yaml already exists and force=False.

    Raised when attempting to write maverick.yaml but the file
    already exists and the --force flag was not provided.

    Attributes:
        config_path: Path to the existing configuration file.

    Example:
        ```python
        if config_path.exists() and not force:
            raise ConfigExistsError(config_path)
        ```
    """

    def __init__(self, config_path: Path) -> None:
        """Initialize the ConfigExistsError.

        Args:
            config_path: Path to the existing configuration file.
        """
        self.config_path = config_path
        super().__init__(f"Configuration already exists: {config_path}")


class ConfigWriteError(InitError):
    """Failed to write configuration file.

    Raised when writing maverick.yaml fails due to I/O errors,
    permission issues, or other filesystem problems.

    Attributes:
        config_path: Path where the write was attempted.
        cause: The underlying exception that caused the failure.

    Example:
        ```python
        try:
            config_path.write_text(yaml_content)
        except OSError as e:
            raise ConfigWriteError(config_path, e)
        ```
    """

    def __init__(
        self,
        config_path: Path,
        cause: Exception,
    ) -> None:
        """Initialize the ConfigWriteError.

        Args:
            config_path: Path where the write was attempted.
            cause: The underlying exception that caused the failure.
        """
        self.config_path = config_path
        self.cause = cause
        super().__init__(f"Failed to write {config_path}: {cause}")


class AnthropicAPIError(InitError):
    """Anthropic API validation failed.

    Raised when validating Anthropic API access fails during
    prerequisite checks. The status_code can help distinguish
    between authentication, permission, and rate limit errors.

    Attributes:
        message: Human-readable error message.
        status_code: Optional HTTP status code from the API response.

    Example:
        ```python
        try:
            await validate_api_access()
        except anthropic.AuthenticationError:
            raise AnthropicAPIError(
                "Invalid API key",
                status_code=401,
            )
        ```
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        """Initialize the AnthropicAPIError.

        Args:
            message: Human-readable error message.
            status_code: Optional HTTP status code from the API response.
        """
        self.status_code = status_code
        super().__init__(message)
