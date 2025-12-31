# API Contracts: Preflight Validation System

**Feature**: 027-preflight-validation  
**Date**: 2024-12-24

This document defines the public interfaces for the preflight validation system.

## Protocol: ValidatableRunner

Location: `src/maverick/runners/protocols.py`

```python
from typing import Protocol
from maverick.runners.preflight import ValidationResult

class ValidatableRunner(Protocol):
    """Protocol for runners that support environment validation."""

    async def validate(self) -> ValidationResult:
        """Validate that required tools and configuration are available.

        Returns:
            ValidationResult with success status and any errors/warnings.

        Contract:
            - MUST NOT raise exceptions for validation failures
            - MUST capture failures in ValidationResult.errors
            - MUST complete within reasonable time (caller uses timeout)
            - MUST be safe to call multiple times (idempotent)
        """
        ...
```

## Class: PreflightValidator

Location: `src/maverick/runners/preflight.py`

```python
class PreflightValidator:
    """Orchestrates preflight validation across multiple runners."""

    def __init__(
        self,
        runners: list[ValidatableRunner],
        timeout_per_check: float = 5.0,
    ) -> None:
        """Initialize the preflight validator.

        Args:
            runners: List of runners to validate.
            timeout_per_check: Maximum seconds per validation (default: 5.0).

        Contract:
            - runners MUST implement ValidatableRunner protocol
            - timeout_per_check MUST be > 0
        """
        ...

    async def run(self) -> PreflightResult:
        """Execute all validations in parallel.

        Returns:
            PreflightResult with aggregated results from all runners.

        Contract:
            - MUST run all validations, even if some fail
            - MUST apply timeout to each validation individually
            - MUST NOT raise exceptions (failures captured in result)
            - MUST complete in approximately max(timeout_per_check) time
        """
        ...
```

## Mixin Method: WorkflowDSLMixin.run_preflight()

Location: `src/maverick/workflows/base.py`

```python
class WorkflowDSLMixin:
    async def run_preflight(
        self,
        runners: list[ValidatableRunner] | None = None,
        timeout_per_check: float = 5.0,
    ) -> PreflightResult:
        """Run preflight validation before workflow execution.

        Args:
            runners: Runners to validate. If None, discovers from instance.
            timeout_per_check: Maximum seconds per validation.

        Returns:
            PreflightResult if all validations pass.

        Raises:
            PreflightValidationError: If any critical validation fails.

        Contract:
            - MUST be called before any state-changing operations
            - MUST run even in dry_run mode
            - MUST aggregate all failures (not fail on first)
            - SHOULD discover runners from workflow instance if not provided
        """
        ...
```

## Runner validate() Methods

Each runner implements `validate()` returning `ValidationResult`.

### GitRunner.validate()

```python
async def validate(self) -> ValidationResult:
    """Validate git environment.

    Checks:
        1. git executable on PATH
        2. Current directory is inside a git repository
        3. Repository is not in merge/rebase conflict state
        4. Git user.name and user.email are configured

    Returns:
        ValidationResult with component="GitRunner"
    """
    ...
```

### GitHubCLIRunner.validate()

```python
async def validate(self) -> ValidationResult:
    """Validate GitHub CLI environment.

    Checks:
        1. gh executable on PATH
        2. User is authenticated (gh auth status)
        3. Token has required scopes (repo, read:org)

    Returns:
        ValidationResult with component="GitHubCLIRunner"
    """
    ...
```

### ValidationRunner.validate()

```python
async def validate(self) -> ValidationResult:
    """Validate configured validation tools.

    Checks:
        - Each configured tool (ruff, mypy, pytest, etc.) is on PATH

    Returns:
        ValidationResult with component="ValidationRunner"
    """
    ...
```

### CodeRabbitRunner.validate()

```python
async def validate(self) -> ValidationResult:
    """Validate CodeRabbit CLI (if enabled).

    Checks:
        - coderabbit executable on PATH (warning, not error, if missing)

    Returns:
        ValidationResult with component="CodeRabbitRunner"
        Note: Missing CodeRabbit is a warning, not an error.
    """
    ...
```

## Exception: PreflightValidationError

Location: `src/maverick/exceptions/preflight.py`

```python
class PreflightValidationError(MaverickError):
    """Raised when preflight validation fails.

    Attributes:
        result: PreflightResult containing all failure details.

    Contract:
        - Error message MUST list all failed components
        - Error message MUST include remediation hints
        - result attribute MUST contain full PreflightResult
    """

    result: PreflightResult
```

## Usage Example

```python
from maverick.runners import GitRunner, GitHubCLIRunner, ValidationRunner
from maverick.runners.preflight import PreflightValidator
from maverick.exceptions import PreflightValidationError

async def run_workflow():
    # Create runners
    git = GitRunner(cwd=Path.cwd())
    github = GitHubCLIRunner()
    validation = ValidationRunner(stages=config.validation.stages)

    # Run preflight
    validator = PreflightValidator(
        runners=[git, github, validation],
        timeout_per_check=5.0,
    )
    result = await validator.run()

    if not result.success:
        raise PreflightValidationError(result)

    # Proceed with workflow...
```
