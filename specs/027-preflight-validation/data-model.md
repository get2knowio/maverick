# Data Model: Preflight Validation System

**Feature**: 027-preflight-validation  
**Date**: 2024-12-24

## Entities

### 1. ValidationResult

Represents the outcome of a single validation check for one component.

```python
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a single validation check.

    Attributes:
        success: Whether the validation passed.
        component: Name of the validated component (e.g., "GitRunner").
        errors: Tuple of error messages (empty if success=True).
        warnings: Tuple of warning messages (non-blocking).
        duration_ms: Time taken for this validation in milliseconds.
    """

    success: bool
    component: str
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DSL serialization."""
        return asdict(self)
```

**Validation Rules**:

- `component` must be non-empty string
- If `success=False`, `errors` should be non-empty
- `duration_ms` must be non-negative

**State Transitions**: N/A (immutable value object)

---

### 2. PreflightResult

Aggregates multiple `ValidationResult` objects and provides overall status.

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Aggregated preflight validation result.

    Attributes:
        success: True only if ALL validations passed.
        results: Tuple of individual ValidationResult objects.
        total_duration_ms: Total time for all validations.
        failed_components: Tuple of component names that failed.
        all_errors: Aggregated errors from all failed validations.
        all_warnings: Aggregated warnings from all validations.
    """

    success: bool
    results: tuple[ValidationResult, ...]
    total_duration_ms: int
    failed_components: tuple[str, ...] = field(default_factory=tuple)
    all_errors: tuple[str, ...] = field(default_factory=tuple)
    all_warnings: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_results(
        cls,
        results: list[ValidationResult],
        total_duration_ms: int,
    ) -> "PreflightResult":
        """Create PreflightResult from list of ValidationResults."""
        failed = [r for r in results if not r.success]
        return cls(
            success=len(failed) == 0,
            results=tuple(results),
            total_duration_ms=total_duration_ms,
            failed_components=tuple(r.component for r in failed),
            all_errors=tuple(
                f"[{r.component}] {err}"
                for r in failed
                for err in r.errors
            ),
            all_warnings=tuple(
                f"[{r.component}] {warn}"
                for r in results
                for warn in r.warnings
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DSL serialization."""
        return {
            "success": self.success,
            "results": [r.to_dict() for r in self.results],
            "total_duration_ms": self.total_duration_ms,
            "failed_components": list(self.failed_components),
            "all_errors": list(self.all_errors),
            "all_warnings": list(self.all_warnings),
        }
```

**Validation Rules**:

- `success` must be True iff all results have `success=True`
- `failed_components` must match components with `success=False`
- `total_duration_ms` must be non-negative

**State Transitions**: N/A (immutable value object)

---

### 3. ValidatableRunner (Protocol)

Interface for runners that support environment validation.

```python
from typing import Protocol

class ValidatableRunner(Protocol):
    """Protocol for runners that support environment validation.

    Any runner class that implements an async validate() method
    returning ValidationResult satisfies this protocol.
    """

    async def validate(self) -> ValidationResult:
        """Validate that required tools and configuration are available.

        Returns:
            ValidationResult with success status and any errors/warnings.

        Note:
            This method should NOT raise exceptions for validation failures.
            Failures should be captured in the ValidationResult.errors tuple.
        """
        ...
```

**Implementers**:

- `GitRunner` - validates git CLI and repository state
- `GitHubCLIRunner` - validates gh CLI and authentication
- `ValidationRunner` - validates configured tool availability
- `CodeRabbitRunner` - validates coderabbit CLI (if enabled)

---

### 4. PreflightConfig

Configuration for preflight validation behavior.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class PreflightConfig:
    """Configuration for preflight validation.

    Attributes:
        timeout_per_check: Maximum seconds per individual validation (default: 5.0).
        fail_on_warning: Whether to fail workflow on warnings (default: False).
    """

    timeout_per_check: float = 5.0
    fail_on_warning: bool = False
```

---

## Relationships

```
┌─────────────────────┐
│  ValidatableRunner  │ (Protocol)
│    + validate()     │
└─────────┬───────────┘
          │ implements
          ▼
┌─────────────────────────────────────────────────────┐
│  GitRunner │ GitHubCLIRunner │ ValidationRunner │   │
│            │                  │ CodeRabbitRunner    │
└──────────────────────┬──────────────────────────────┘
                       │ produces
                       ▼
              ┌─────────────────┐
              │ ValidationResult│
              │ (per component) │
              └────────┬────────┘
                       │ aggregated by
                       ▼
              ┌─────────────────┐
              │ PreflightResult │
              │   (overall)     │
              └────────┬────────┘
                       │ used by
                       ▼
              ┌─────────────────┐
              │PreflightValidator│
              │   (orchestrator)│
              └─────────────────┘
```

## Error Types

### PreflightValidationError

Exception raised when preflight validation fails.

```python
from maverick.exceptions.base import MaverickError

class PreflightValidationError(MaverickError):
    """Raised when preflight validation fails.

    Attributes:
        result: The PreflightResult containing failure details.
    """

    def __init__(self, result: PreflightResult) -> None:
        self.result = result
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        lines = [
            f"Preflight validation failed ({len(self.result.failed_components)} components):",
            "",
        ]
        for error in self.result.all_errors:
            lines.append(f"  ✗ {error}")
        if self.result.all_warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in self.result.all_warnings:
                lines.append(f"  ⚠ {warning}")
        return "\n".join(lines)
```

## Serialization

All data models support serialization via `to_dict()` for:

- DSL workflow context passing
- Logging and debugging
- Event emission to TUI

The serialization format uses standard Python types (dict, list, str, int, bool) to ensure compatibility with JSON serialization if needed.
