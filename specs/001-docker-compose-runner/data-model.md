# Data Model: Containerized Validation with Docker Compose

Date: 2025-10-30  
Feature: 001-docker-compose-runner

## Core Entities

### ComposeConfig

**Description**: Workflow parameter containing parsed Docker Compose configuration and execution settings.

**Fields**:
- `yaml_content`: str - Original YAML content as string (for serialization to file)
- `parsed_config`: dict[str, Any] - Parsed YAML structure (for validation and service lookup)
- `target_service`: str | None - Explicit service name for validation execution (None triggers default selection)
- `startup_timeout_seconds`: int = 300 - Maximum time to wait for environment startup and health checks
- `validation_timeout_seconds`: int = 60 - Maximum time per validation step execution

**Validation Rules** (in `__post_init__`):
- `len(yaml_content.encode('utf-8'))` must be ≤ 1,048,576 bytes (1 MB limit)
- `yaml_content` must not be empty
- `parsed_config` must be a dict with `services` key
- `parsed_config['services']` must be a dict with at least one service
- `startup_timeout_seconds` must be > 0
- `validation_timeout_seconds` must be > 0
- If `target_service` is provided, it must be a non-empty string

**Example**:
```python
@dataclass
class ComposeConfig:
    yaml_content: str
    parsed_config: dict[str, Any]
    target_service: str | None = None
    startup_timeout_seconds: int = 300
    validation_timeout_seconds: int = 60
    
    def __post_init__(self) -> None:
        size_bytes = len(self.yaml_content.encode('utf-8'))
        if size_bytes > 1_048_576:
            raise ValueError(f"YAML content exceeds 1MB limit: {size_bytes} bytes")
        if not self.yaml_content.strip():
            raise ValueError("YAML content cannot be empty")
        if not isinstance(self.parsed_config, dict):
            raise ValueError("Parsed config must be a dict")
        if 'services' not in self.parsed_config:
            raise ValueError("Compose config must contain 'services' key")
        if not isinstance(self.parsed_config['services'], dict):
            raise ValueError("'services' must be a dict")
        if len(self.parsed_config['services']) == 0:
            raise ValueError("At least one service must be defined")
        if self.startup_timeout_seconds <= 0:
            raise ValueError("Startup timeout must be positive")
        if self.validation_timeout_seconds <= 0:
            raise ValueError("Validation timeout must be positive")
        if self.target_service is not None and not self.target_service.strip():
            raise ValueError("Target service name cannot be empty string")
```

---

### ComposeEnvironment

**Description**: Represents a running Docker Compose environment for a workflow execution.

**Fields**:
- `project_name`: str - Unique Docker Compose project name (format: `maverick-<hash8>` where hash8 is 8-char SHA256 hash of workflow_id:run_id)
- `target_service`: str - Resolved service name where validations execute
- `health_status`: Literal["starting", "healthy", "unhealthy"] - Current health state
- `container_ids`: dict[str, str] - Map of service names to container IDs
- `started_at`: str - ISO 8601 timestamp when environment started

**Validation Rules**:
- `project_name` must start with `maverick-`
- `project_name` must contain only lowercase alphanumeric, hyphens, underscores
- `project_name` must start with letter or number
- `target_service` must not be empty
- `started_at` must be valid ISO 8601 format
- `health_status` must be one of: "starting", "healthy", "unhealthy"

**State Transitions**:
- `starting` → `healthy` (health check passes)
- `starting` → `unhealthy` (health check fails)
- `healthy` → `unhealthy` (service degrades)

**Example**:
```python
from typing import Literal

HealthStatus = Literal["starting", "healthy", "unhealthy"]

@dataclass
class ComposeEnvironment:
    project_name: str
    target_service: str
    health_status: HealthStatus
    container_ids: dict[str, str]
    started_at: str  # ISO 8601
    
    def __post_init__(self) -> None:
        import re
        pattern = r'^maverick-[a-zA-Z0-9_-]+-[a-zA-Z0-9_-]+$'
        if not re.match(pattern, self.project_name):
            raise ValueError(f"Invalid project name format: {self.project_name}")
        if not self.target_service.strip():
            raise ValueError("Target service cannot be empty")
        # Validate ISO 8601 format
        from datetime import datetime
        try:
            datetime.fromisoformat(self.started_at.replace('Z', '+00:00'))
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 timestamp: {self.started_at}") from e
```

---

### ComposeUpResult

**Description**: Result of starting a Docker Compose environment.

**Fields**:
- `success`: bool - Whether startup succeeded
- `environment`: ComposeEnvironment | None - Environment details if successful
- `error_message`: str | None - Human-readable error if failed
- `error_type`: Literal["none", "validation_error", "docker_unavailable", "startup_failed", "health_check_timeout", "health_check_failed"] - Categorized error type
- `duration_ms`: int - Time taken for startup attempt
- `stderr_excerpt`: str | None - Last 50 lines of stderr if failed

**Validation Rules**:
- If `success` is True, `environment` must not be None and `error_type` must be "none"
- If `success` is False, `error_message` must not be None and `error_type` must not be "none"
- `duration_ms` must be >= 0

**Example**:
```python
ErrorType = Literal[
    "none",
    "validation_error",
    "docker_unavailable",
    "startup_failed",
    "health_check_timeout",
    "health_check_failed"
]

@dataclass
class ComposeUpResult:
    success: bool
    environment: ComposeEnvironment | None
    error_message: str | None
    error_type: ErrorType
    duration_ms: int
    stderr_excerpt: str | None = None
    
    def __post_init__(self) -> None:
        if self.success:
            if self.environment is None:
                raise ValueError("success=True requires environment to be set")
            if self.error_type != "none":
                raise ValueError(f"success=True requires error_type='none', got '{self.error_type}'")
        else:
            if self.error_message is None or not self.error_message.strip():
                raise ValueError("success=False requires non-empty error_message")
            if self.error_type == "none":
                raise ValueError("success=False requires error_type != 'none'")
        if self.duration_ms < 0:
            raise ValueError(f"duration_ms must be >= 0, got {self.duration_ms}")
```

---

### ComposeCleanupParams

**Description**: Parameters for cleanup activity.

**Fields**:
- `project_name`: str - Docker Compose project name to clean up
- `mode`: Literal["graceful", "preserve"] - Cleanup mode

**Validation Rules**:
- `project_name` must not be empty
- `mode` must be "graceful" or "preserve"

**Example**:
```python
CleanupMode = Literal["graceful", "preserve"]

@dataclass
class ComposeCleanupParams:
    project_name: str
    mode: CleanupMode
    
    def __post_init__(self) -> None:
        if not self.project_name.strip():
            raise ValueError("project_name cannot be empty")
```

---

### ValidateInContainerParams

**Description**: Parameters for running validation inside container.

**Fields**:
- `project_name`: str - Docker Compose project name
- `service_name`: str - Service to execute command in
- `command`: list[str] - Command and arguments to execute
- `timeout_seconds`: int - Maximum execution time

**Validation Rules**:
- `project_name` must not be empty
- `service_name` must not be empty
- `command` must be non-empty list
- `timeout_seconds` must be > 0

**Example**:
```python
@dataclass
class ValidateInContainerParams:
    project_name: str
    service_name: str
    command: list[str]
    timeout_seconds: int
    
    def __post_init__(self) -> None:
        if not self.project_name.strip():
            raise ValueError("project_name cannot be empty")
        if not self.service_name.strip():
            raise ValueError("service_name cannot be empty")
        if not self.command or len(self.command) == 0:
            raise ValueError("command must be non-empty list")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
```

---

## Target Service Resolution Logic

**Function**: `resolve_target_service(config: ComposeConfig) -> str`

**Algorithm**:
```python
def resolve_target_service(config: ComposeConfig) -> str:
    """Resolve target service name using default selection policy."""
    services = config.parsed_config['services']
    
    # Explicit override
    if config.target_service is not None:
        if config.target_service not in services:
            raise ValueError(
                f"Target service '{config.target_service}' not found in services. "
                f"Available: {', '.join(services.keys())}"
            )
        return config.target_service
    
    # Single service: use it
    if len(services) == 1:
        return next(iter(services.keys()))
    
    # Multiple services: look for "app"
    if "app" in services:
        return "app"
    
    # Multiple services, no "app": fail with instructions
    raise ValueError(
        f"Multiple services defined without 'app' service. "
        f"Available services: {', '.join(services.keys())}. "
        f"Please specify target_service explicitly."
    )
```

---

## Invariants

1. **Size Constraint**: `ComposeConfig.yaml_content` serialized size ≤ 1 MB
2. **Service Existence**: Resolved `target_service` must exist in `parsed_config['services']`
3. **Health Check Requirement**: Target service in parsed config must define `healthcheck` section
4. **Project Name Uniqueness**: Each workflow run generates unique project name from workflow_id + run_id
5. **Success Correlation**: `ComposeUpResult.success=True` ⟺ `error_type="none"` ∧ `environment != None`
6. **Failure Correlation**: `ComposeUpResult.success=False` ⟺ `error_type != "none"` ∧ `error_message != None`
7. **Timeout Positivity**: All timeout fields must be > 0
8. **Cleanup Modes**: "graceful" removes all resources; "preserve" logs instructions only

---

## Type Aliases

```python
from typing import Literal

# Health status values
HealthStatus = Literal["starting", "healthy", "unhealthy"]

# Error categorization
ErrorType = Literal[
    "none",
    "validation_error",
    "docker_unavailable",
    "startup_failed",
    "health_check_timeout",
    "health_check_failed"
]

# Cleanup behavior
CleanupMode = Literal["graceful", "preserve"]
```

---

## Notes

- **Literal Types**: Use `Literal` for all enum-like values to avoid custom Temporal serializers (per constitution)
- **Result Types**: Activities return dataclasses; workflows MUST specify `result_type` parameter for proper deserialization
- **Validation Timing**: All `__post_init__` validations run at construction time (fail-fast principle)
- **Determinism**: Project names derived from `workflow.info().workflow_id` and `workflow.info().run_id` ensure deterministic, unique naming
- **Error Handling**: All subprocess stderr decoding uses `errors='replace'` to prevent UnicodeDecodeError (per constitution)
