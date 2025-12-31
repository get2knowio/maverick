# Internal API Contract: maverick init

**Feature**: 028-maverick-init | **Date**: 2025-12-29

## Module: `maverick.init.prereqs`

### `verify_prerequisites`

Validates all prerequisites required for maverick init.

```python
async def verify_prerequisites(
    *,
    skip_api_check: bool = False,
    timeout_per_check: float = 10.0,
) -> InitPreflightResult:
    """Verify all prerequisites for maverick init.

    Args:
        skip_api_check: Skip Anthropic API validation (for --no-detect).
        timeout_per_check: Timeout in seconds for each check.

    Returns:
        InitPreflightResult with all check results.

    Raises:
        PrerequisiteError: If a critical check fails.

    Example:
        result = await verify_prerequisites()
        if not result.success:
            for check in result.checks:
                if check.status == PreflightStatus.FAIL:
                    print(f"Failed: {check.display_name}")
                    print(f"  {check.remediation}")
    """
```

### `check_git_installed`

```python
async def check_git_installed(
    timeout: float = 5.0,
) -> PrerequisiteCheck:
    """Check if git is installed and accessible.

    Returns:
        PrerequisiteCheck with git version or error.
    """
```

### `check_in_git_repo`

```python
async def check_in_git_repo(
    cwd: Path | None = None,
    timeout: float = 5.0,
) -> PrerequisiteCheck:
    """Check if current directory is a git repository.

    Args:
        cwd: Working directory to check. Defaults to cwd.

    Returns:
        PrerequisiteCheck with success or error.
    """
```

### `check_gh_installed`

```python
async def check_gh_installed(
    timeout: float = 5.0,
) -> PrerequisiteCheck:
    """Check if GitHub CLI is installed.

    Returns:
        PrerequisiteCheck with gh version or error.
    """
```

### `check_gh_authenticated`

```python
async def check_gh_authenticated(
    timeout: float = 10.0,
) -> PrerequisiteCheck:
    """Check if GitHub CLI is authenticated.

    Returns:
        PrerequisiteCheck with username or error.
    """
```

### `check_anthropic_key_set`

```python
def check_anthropic_key_set() -> PrerequisiteCheck:
    """Check if ANTHROPIC_API_KEY environment variable is set.

    Returns:
        PrerequisiteCheck with redacted key or error.
    """
```

### `check_anthropic_api_accessible`

```python
async def check_anthropic_api_accessible(
    model: str = "claude-3-5-haiku-20241022",
    timeout: float = 10.0,
) -> PrerequisiteCheck:
    """Validate Anthropic API access with minimal request.

    Args:
        model: Model to validate access for.
        timeout: Request timeout in seconds.

    Returns:
        PrerequisiteCheck with success or error.

    Error Discrimination:
        - AuthenticationError (401): "Invalid API key" → remediation: verify ANTHROPIC_API_KEY
        - PermissionDeniedError (403): "Model not accessible" → remediation: check plan limits
        - RateLimitError (429): "Rate limit exceeded" → remediation: retry after backoff
        - TimeoutError: "API request timed out" → remediation: check network connectivity
        - Other: "Anthropic API error" → remediation: check API status page
    """
```

---

## Module: `maverick.init.detector`

### `detect_project_type`

```python
async def detect_project_type(
    project_path: Path,
    *,
    use_claude: bool = True,
    override_type: ProjectType | None = None,
    model: str = "claude-3-5-haiku-20241022",
    timeout: float = 30.0,
) -> ProjectDetectionResult:
    """Detect project type using Claude or marker-based heuristics.

    Args:
        project_path: Path to project root.
        use_claude: Use Claude for detection (False = marker-only).
        override_type: Force specific project type.
        model: Claude model for detection.
        timeout: Detection timeout in seconds.

    Returns:
        ProjectDetectionResult with detected type and findings.

    Raises:
        DetectionError: If detection fails completely.

    Example:
        result = await detect_project_type(Path.cwd())
        print(f"Detected: {result.primary_type.value}")
        for finding in result.findings:
            print(f"  • {finding}")
    """
```

### `find_marker_files`

```python
def find_marker_files(
    project_path: Path,
    max_depth: int = 2,
) -> list[ProjectMarker]:
    """Find project marker files in directory tree.

    Args:
        project_path: Path to project root.
        max_depth: Maximum directory depth to search.

    Returns:
        List of ProjectMarker instances found.
    """
```

### `build_detection_context`

```python
def build_detection_context(
    project_path: Path,
    markers: list[ProjectMarker],
    *,
    max_tree_depth: int = 3,
    max_content_length: int = 2000,
) -> str:
    """Build context string for Claude detection prompt.

    Args:
        project_path: Path to project root.
        markers: Detected marker files.
        max_tree_depth: Directory tree depth.
        max_content_length: Max chars per marker file.

    Returns:
        Formatted context string for Claude.
    """
```

### `get_validation_commands`

```python
def get_validation_commands(
    project_type: ProjectType,
) -> ValidationCommands:
    """Get default validation commands for project type.

    Args:
        project_type: Detected or overridden project type.

    Returns:
        ValidationCommands with appropriate defaults.
    """
```

---

## Module: `maverick.init.config_generator`

### `generate_config`

```python
def generate_config(
    *,
    git_info: GitRemoteInfo,
    detection: ProjectDetectionResult | None,
    project_type: ProjectType | None = None,
) -> InitConfig:
    """Generate maverick.yaml configuration.

    Args:
        git_info: Parsed git remote information.
        detection: Detection result (None if --no-detect).
        project_type: Override project type.

    Returns:
        InitConfig ready for serialization.

    Example:
        config = generate_config(
            git_info=git_info,
            detection=detection_result,
        )
        with open("maverick.yaml", "w") as f:
            f.write(config.to_yaml())
    """
```

### `write_config`

```python
def write_config(
    config: InitConfig,
    output_path: Path,
    *,
    force: bool = False,
) -> None:
    """Write configuration to maverick.yaml.

    Args:
        config: Configuration to write.
        output_path: Path to write to.
        force: Overwrite existing file.

    Raises:
        ConfigExistsError: If file exists and force=False.
        ConfigWriteError: If write fails.
    """
```

---

## Module: `maverick.init.git_parser`

### `parse_git_remote`

```python
async def parse_git_remote(
    project_path: Path,
    remote_name: str = "origin",
) -> GitRemoteInfo:
    """Parse git remote URL to extract owner and repo.

    Args:
        project_path: Path to git repository.
        remote_name: Name of remote to parse.

    Returns:
        GitRemoteInfo with parsed owner/repo or nulls.

    Example:
        info = await parse_git_remote(Path.cwd())
        if info.owner and info.repo:
            print(f"Repository: {info.full_name}")
        else:
            print("Warning: No remote configured")
    """
```

---

## Module: `maverick.init`

### `run_init`

Main entry point for init logic (called by CLI command).

```python
async def run_init(
    *,
    project_path: Path | None = None,
    type_override: ProjectType | None = None,
    use_claude: bool = True,
    force: bool = False,
    verbose: bool = False,
) -> InitResult:
    """Execute maverick init workflow.

    Args:
        project_path: Path to project root. Defaults to cwd.
        type_override: Force specific project type.
        use_claude: Use Claude for detection.
        force: Overwrite existing config.
        verbose: Enable verbose output.

    Returns:
        InitResult with complete execution state.

    Raises:
        PrerequisiteError: If prerequisites fail.
        DetectionError: If detection fails.
        ConfigExistsError: If config exists and force=False.

    Example:
        result = await run_init(force=True)
        if result.success:
            print(f"Config written to {result.config_path}")
    """
```

---

## Module: `maverick.runners.preflight`

### `AnthropicAPIValidator` (New Class)

```python
@dataclass
class AnthropicAPIValidator:
    """Validates Anthropic API access for workflow preflight.

    Implements ValidatableRunner protocol for integration with
    existing preflight validation system.
    """

    model: str = "claude-3-5-haiku-20241022"
    timeout: float = 10.0

    async def validate(self) -> ValidationResult:
        """Validate API access.

        Returns:
            ValidationResult with success status and any errors.
        """
```

### Integration with PreflightValidator

```python
# In FlyWorkflow/RefuelWorkflow __init__:
self.anthropic_validator = AnthropicAPIValidator(
    model=config.model.model_id,
    timeout=config.preflight.timeout_per_check,
)

# Discovered automatically by WorkflowDSLMixin.run_preflight()
# via the existing runner discovery pattern (attribute ends with _validator)
```

---

## Module: `maverick.exceptions.init`

### Exception Hierarchy

```python
class InitError(MaverickError):
    """Base exception for init command errors."""
    pass


class PrerequisiteError(InitError):
    """A required prerequisite check failed."""

    def __init__(
        self,
        check: PrerequisiteCheck,
        message: str | None = None,
    ) -> None:
        self.check = check
        super().__init__(message or check.message)


class DetectionError(InitError):
    """Project type detection failed."""

    def __init__(
        self,
        message: str,
        *,
        claude_error: Exception | None = None,
    ) -> None:
        self.claude_error = claude_error
        super().__init__(message)


class ConfigExistsError(InitError):
    """maverick.yaml already exists and force=False."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        super().__init__(f"Configuration already exists: {config_path}")


class ConfigWriteError(InitError):
    """Failed to write configuration file."""

    def __init__(
        self,
        config_path: Path,
        cause: Exception,
    ) -> None:
        self.config_path = config_path
        self.cause = cause
        super().__init__(f"Failed to write {config_path}: {cause}")


class AnthropicAPIError(InitError):
    """Anthropic API validation failed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(message)
```

---

## Integration Points

### CLI Command Registration

```python
# In src/maverick/main.py or src/maverick/cli/main.py:

from maverick.cli.commands.init import init as init_command

cli.add_command(init_command)
```

### Workflow Preflight Integration

```python
# In src/maverick/workflows/fly/workflow.py and refuel/workflow.py:

from maverick.runners.preflight import AnthropicAPIValidator

class FlyWorkflow:
    def __init__(self, config: MaverickConfig, ...):
        # ... existing setup ...

        # NEW: Add Anthropic API validator
        self.anthropic_validator = AnthropicAPIValidator(
            model=config.model.model_id,
        )

    # run_preflight() in base class automatically discovers
    # self.anthropic_validator via attribute naming convention
```

### Deprecation in config.py

```python
# In src/maverick/cli/commands/config.py:

from maverick.cli.commands.init import init as new_init

@config.command("init")
@click.option("--force", is_flag=True)
@click.pass_context
def config_init(ctx: click.Context, force: bool) -> None:
    """[DEPRECATED] Initialize maverick configuration."""
    click.echo(
        click.style(
            "Warning: 'maverick config init' is deprecated. "
            "Use 'maverick init' instead.",
            fg="yellow",
        ),
        err=True,
    )
    ctx.invoke(new_init, force=force)
```
