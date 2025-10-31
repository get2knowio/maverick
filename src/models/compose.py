"""Data models for Docker Compose integration.

This module defines the data structures used for containerized validation
with Docker Compose, including configuration, environment state, and results.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


# Type aliases for better type safety and Temporal serialization
HealthStatus = Literal["starting", "healthy", "unhealthy"]
ErrorType = Literal[
    "none",
    "validation_error",
    "docker_unavailable",
    "startup_failed",
    "health_check_timeout",
    "health_check_failed",
]
CleanupMode = Literal["graceful", "preserve"]


@dataclass
class ComposeConfig:
    """Workflow parameter containing parsed Docker Compose configuration.

    Attributes:
        yaml_content: Original YAML content as string (for serialization to file)
        parsed_config: Parsed YAML structure (for validation and service lookup)
        target_service: Explicit service name for validation execution (None triggers default)
        startup_timeout_seconds: Maximum time to wait for environment startup and health checks
        validation_timeout_seconds: Maximum time per validation step execution

    Invariants:
        - yaml_content size must be <= 1 MB
        - yaml_content must not be empty
        - parsed_config must be dict with 'services' key
        - parsed_config['services'] must have at least one service
        - startup_timeout_seconds must be > 0
        - validation_timeout_seconds must be > 0
        - target_service must be non-empty string if provided
    """

    yaml_content: str
    parsed_config: dict[str, Any]
    target_service: str | None = None
    startup_timeout_seconds: int = 300
    validation_timeout_seconds: int = 60

    def __post_init__(self) -> None:
        """Validate configuration at construction time."""
        # Check size limit
        size_bytes = len(self.yaml_content.encode("utf-8"))
        if size_bytes > 1_048_576:
            raise ValueError(f"YAML content exceeds 1MB limit: {size_bytes} bytes")

        # Check non-empty content
        if not self.yaml_content.strip():
            raise ValueError("YAML content cannot be empty")

        # Validate parsed structure
        if not isinstance(self.parsed_config, dict):
            raise ValueError("Parsed config must be a dict")

        if "services" not in self.parsed_config:
            raise ValueError("Compose config must contain 'services' key")

        if not isinstance(self.parsed_config["services"], dict):
            raise ValueError("'services' must be a dict")

        if len(self.parsed_config["services"]) == 0:
            raise ValueError("At least one service must be defined")

        # Validate timeouts
        if self.startup_timeout_seconds <= 0:
            raise ValueError("Startup timeout must be positive")

        if self.validation_timeout_seconds <= 0:
            raise ValueError("Validation timeout must be positive")

        # Validate target service if provided
        if self.target_service is not None and not self.target_service.strip():
            raise ValueError("Target service name cannot be empty string")


@dataclass
class ComposeEnvironment:
    """Represents a running Docker Compose environment.

    Attributes:
        project_name: Unique Docker Compose project name (format: maverick-<hash8>)
        target_service: Resolved service name where validations execute
        health_status: Current health state
        container_ids: Map of service names to container IDs
        started_at: ISO 8601 timestamp when environment started

    State Transitions:
        - starting → healthy (health check passes)
        - starting → unhealthy (health check fails)
        - healthy → unhealthy (service degrades)
    """

    project_name: str
    target_service: str
    health_status: HealthStatus
    container_ids: dict[str, str]
    started_at: str  # ISO 8601 format

    def __post_init__(self) -> None:
        """Validate environment state at construction time."""
        import re

        # Validate project name format (Docker Compose requirements)
        # Format: maverick-<8char-hash> (e.g., maverick-a1b2c3d4)
        # Must be lowercase alphanumeric, hyphens, underscores only
        # Must start with letter or number
        pattern = r"^[a-z0-9][a-z0-9_-]*$"
        if not re.match(pattern, self.project_name):
            raise ValueError(
                f"Invalid project name format: {self.project_name}. "
                "Must contain only lowercase alphanumeric, hyphens, underscores "
                "and start with letter or number."
            )

        # Additional check for expected format (maverick-<hash>)
        if not self.project_name.startswith("maverick-"):
            raise ValueError(
                f"Project name must start with 'maverick-': {self.project_name}"
            )

        # Validate target service
        if not self.target_service.strip():
            raise ValueError("Target service cannot be empty")

        # Validate ISO 8601 timestamp
        try:
            datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 timestamp: {self.started_at}") from e


@dataclass
class ComposeUpResult:
    """Result of starting a Docker Compose environment.

    Attributes:
        success: Whether startup succeeded
        environment: Environment details if successful
        error_message: Human-readable error if failed
        error_type: Categorized error type
        duration_ms: Time taken for startup attempt
        stderr_excerpt: Last 50 lines of stderr if failed

    Invariants:
        - success=True requires environment != None and error_type='none'
        - success=False requires error_message != None and error_type != 'none'
        - duration_ms must be >= 0
    """

    success: bool
    environment: ComposeEnvironment | None
    error_message: str | None
    error_type: ErrorType
    duration_ms: int
    stderr_excerpt: str | None = None

    def __post_init__(self) -> None:
        """Validate result consistency at construction time."""
        if self.success:
            if self.environment is None:
                raise ValueError("success=True requires environment to be set")
            if self.error_type != "none":
                raise ValueError(
                    f"success=True requires error_type='none', got '{self.error_type}'"
                )
        else:
            if self.error_message is None or not self.error_message.strip():
                raise ValueError("success=False requires non-empty error_message")
            if self.error_type == "none":
                raise ValueError("success=False requires error_type != 'none'")

        if self.duration_ms < 0:
            raise ValueError(f"duration_ms must be >= 0, got {self.duration_ms}")


@dataclass
class ComposeCleanupParams:
    """Parameters for cleanup activity.

    Attributes:
        project_name: Docker Compose project name to clean up
        mode: Cleanup mode (graceful or preserve)

    Cleanup Modes:
        - graceful: Remove all resources (success path)
        - preserve: Log instructions only (failure path)
    """

    project_name: str
    mode: CleanupMode

    def __post_init__(self) -> None:
        """Validate cleanup parameters at construction time."""
        if not self.project_name.strip():
            raise ValueError("project_name cannot be empty")


@dataclass
class ValidateInContainerParams:
    """Parameters for running validation inside container.

    Attributes:
        project_name: Docker Compose project name
        service_name: Service to execute command in
        command: Command and arguments to execute
        timeout_seconds: Maximum execution time
    """

    project_name: str
    service_name: str
    command: list[str]
    timeout_seconds: int

    def __post_init__(self) -> None:
        """Validate parameters at construction time."""
        if not self.project_name.strip():
            raise ValueError("project_name cannot be empty")

        if not self.service_name.strip():
            raise ValueError("service_name cannot be empty")

        if not self.command or len(self.command) == 0:
            raise ValueError("command must be non-empty list")

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass
class ValidationResult:
    """Result of running a validation command.

    Attributes:
        success: Whether validation command succeeded (return_code == 0)
        stdout: Standard output from command
        stderr: Standard error from command
        return_code: Exit code from command
        duration_ms: Execution time in milliseconds
    """

    success: bool
    stdout: str
    stderr: str
    return_code: int
    duration_ms: int

    def __post_init__(self) -> None:
        """Validate result consistency at construction time."""
        if self.duration_ms < 0:
            raise ValueError(f"duration_ms must be >= 0, got {self.duration_ms}")


def resolve_target_service(config: ComposeConfig) -> str:
    """Resolve target service name using default selection policy.

    Algorithm:
        1. If explicit target_service provided: Use it (validate existence)
        2. If single service: Use it
        3. If multiple services and 'app' exists: Use 'app'
        4. If multiple services without 'app': Fail with instructions

    Args:
        config: Docker Compose configuration

    Returns:
        Resolved service name

    Raises:
        ValueError: If target service cannot be determined or doesn't exist
    """
    services = config.parsed_config["services"]

    # Explicit override
    if config.target_service is not None:
        if config.target_service not in services:
            available = ", ".join(sorted(services.keys()))
            raise ValueError(
                f"Target service '{config.target_service}' not found in services. "
                f"Available: {available}"
            )
        return config.target_service

    # Single service: use it
    if len(services) == 1:
        return next(iter(services.keys()))

    # Multiple services: look for "app"
    if "app" in services:
        return "app"

    # Multiple services, no "app": fail with instructions
    available = ", ".join(sorted(services.keys()))
    raise ValueError(
        f"Multiple services defined without 'app' service. "
        f"Available services: {available}. "
        f"Please specify target_service explicitly."
    )
