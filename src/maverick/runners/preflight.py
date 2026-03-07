"""Preflight validation data models and orchestrator.

This module provides the core data structures for preflight validation:
- ValidationResult: Result of a single validation check
- PreflightResult: Aggregated results from all validations
- PreflightConfig: Configuration for validation behavior
- PreflightValidator: Orchestrator that runs validations in parallel
- CustomToolValidator: Validates custom tools from configuration
"""

from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from maverick.config import CustomToolConfig
    from maverick.runners.protocols import ValidatableRunner

__all__ = [
    "ValidationResult",
    "PreflightResult",
    "PreflightConfig",
    "PreflightValidator",
    "CustomToolValidator",
]


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
        """Convert to dictionary for DSL serialization.

        Returns:
            Dictionary representation of this result.
        """
        return asdict(self)


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
    ) -> PreflightResult:
        """Create PreflightResult from list of ValidationResults.

        Args:
            results: List of individual validation results.
            total_duration_ms: Total time taken for all validations.

        Returns:
            Aggregated PreflightResult.
        """
        failed = [r for r in results if not r.success]
        return cls(
            success=len(failed) == 0,
            results=tuple(results),
            total_duration_ms=total_duration_ms,
            failed_components=tuple(r.component for r in failed),
            all_errors=tuple(
                f"[{r.component}] {err}" for r in failed for err in r.errors
            ),
            all_warnings=tuple(
                f"[{r.component}] {warn}" for r in results for warn in r.warnings
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DSL serialization.

        Returns:
            Dictionary representation of this result.
        """
        return {
            "success": self.success,
            "results": [r.to_dict() for r in self.results],
            "total_duration_ms": self.total_duration_ms,
            "failed_components": list(self.failed_components),
            "all_errors": list(self.all_errors),
            "all_warnings": list(self.all_warnings),
        }


@dataclass(frozen=True, slots=True)
class PreflightConfig:
    """Configuration for preflight validation.

    Attributes:
        timeout_per_check: Maximum seconds per individual validation (default: 5.0).
        fail_on_warning: Whether to fail workflow on warnings (default: False).
    """

    timeout_per_check: float = 5.0
    fail_on_warning: bool = False


class PreflightValidator:
    """Orchestrates preflight validation across multiple runners.

    This class runs validation checks on multiple runners in parallel,
    aggregating the results into a single PreflightResult.

    Example:
        validator = PreflightValidator(
            runners=[git_runner, github_runner],
            config=PreflightConfig(timeout_per_check=5.0),
        )
        result = await validator.run()
        if not result.success:
            raise PreflightValidationError(result)
    """

    def __init__(
        self,
        runners: Sequence[ValidatableRunner],
        config: PreflightConfig | None = None,
    ) -> None:
        """Initialize the preflight validator.

        Args:
            runners: Sequence of runners to validate.
            config: Optional configuration for validation behavior.
        """
        self._runners = list(runners)
        self._config = config or PreflightConfig()

    async def _validate_with_timeout(
        self,
        runner: ValidatableRunner,
    ) -> ValidationResult:
        """Run a single validation with timeout.

        Args:
            runner: The runner to validate.

        Returns:
            ValidationResult from the runner, or a timeout error result.
        """
        component_name = runner.__class__.__name__
        start_time = time.monotonic()

        try:
            result = await asyncio.wait_for(
                runner.validate(),
                timeout=self._config.timeout_per_check,
            )
            return result
        except TimeoutError:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return ValidationResult(
                success=False,
                component=component_name,
                errors=(
                    f"Validation timed out after {self._config.timeout_per_check}s",
                ),
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return ValidationResult(
                success=False,
                component=component_name,
                errors=(f"Validation failed with error: {e}",),
                duration_ms=duration_ms,
            )

    async def run(self) -> PreflightResult:
        """Execute all validations in parallel.

        Returns:
            PreflightResult with aggregated results from all runners.
        """
        if not self._runners:
            return PreflightResult(
                success=True,
                results=(),
                total_duration_ms=0,
            )

        start_time = time.monotonic()

        # Run all validations in parallel, capturing exceptions
        tasks = [self._validate_with_timeout(runner) for runner in self._runners]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert any uncaught exceptions to ValidationResult
        processed_results: list[ValidationResult] = []
        for i, result in enumerate(results):
            if isinstance(result, ValidationResult):
                processed_results.append(result)
            elif isinstance(result, Exception):
                # This shouldn't happen since _validate_with_timeout catches exceptions
                component_name = self._runners[i].__class__.__name__
                processed_results.append(
                    ValidationResult(
                        success=False,
                        component=component_name,
                        errors=(f"Unexpected error: {result}",),
                    )
                )

        total_duration_ms = int((time.monotonic() - start_time) * 1000)
        return PreflightResult.from_results(processed_results, total_duration_ms)


class CustomToolValidator:
    """Validates custom tools defined in maverick.yaml configuration.

    This class allows users to define additional tools that should be
    validated during preflight checks.

    Example:
        validator = CustomToolValidator(custom_tools=[
            CustomToolConfig(name="Docker", command="docker", required=True),
        ])
        result = await validator.validate()
    """

    def __init__(self, custom_tools: Sequence[CustomToolConfig]) -> None:
        """Initialize the custom tool validator.

        Args:
            custom_tools: List of custom tool configurations to validate.
        """
        self._custom_tools = list(custom_tools)

    async def validate(self) -> ValidationResult:
        """Validate all custom tools are available.

        Returns:
            ValidationResult with success status and any errors/warnings.
        """
        start_time = time.monotonic()
        errors: list[str] = []
        warnings: list[str] = []

        for tool in self._custom_tools:
            # Check if tool is on PATH
            tool_path = shutil.which(tool.command)

            if tool_path is None:
                hint_suffix = f" {tool.hint}" if tool.hint else ""
                message = (
                    f"Tool '{tool.name}' ({tool.command}) not found on PATH."
                    f"{hint_suffix}"
                )

                if tool.required:
                    errors.append(message)
                else:
                    warnings.append(message)

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return ValidationResult(
            success=len(errors) == 0,
            component="CustomTools",
            errors=tuple(errors),
            warnings=tuple(warnings),
            duration_ms=duration_ms,
        )
