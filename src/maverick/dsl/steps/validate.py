"""Validate step for the Maverick workflow DSL.

This module defines ValidateStep, which runs validation stages with retry logic
and optional failure recovery steps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maverick.dsl.config import DEFAULTS
from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import StepType
from maverick.exceptions import StagesNotFoundError


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a validation step.

    Attributes:
        success: True if all validation stages passed.
        stages: List of stage names that were requested to run.
        stage_results: Per-stage results with passed status, output, and errors.
    """

    success: bool
    stages: list[str]
    stage_results: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Alias for success for compatibility with workflow expressions."""
        return self.success

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for expression evaluation compatibility.

        Returns:
            Dictionary with success, stages, passed, and stage_results fields.
        """
        return {
            "success": self.success,
            "stages": list(self.stages),
            "passed": self.passed,
            "stage_results": dict(self.stage_results),
        }


@dataclass(frozen=True, slots=True)
class ValidateStep(StepDefinition):
    """Step that runs validation stages with retry logic.

    ValidateStep executes validation stages (format, lint, test, etc.) with
    configurable retry logic. If validation fails, an optional on_failure step
    can be executed before retrying (e.g., auto-fix formatting issues).

    Attributes:
        name: Step name.
        stages: Explicit list of stages, config key, or None for default.
        retry: Number of retry attempts (0 = no retries). Defaults to
            DEFAULTS.DEFAULT_RETRY_ATTEMPTS.
        on_failure: Optional step to run before each retry.
        step_type: Always StepType.VALIDATE (auto-set, do not pass).

    Example:
        >>> # Use default stages from config with default retry
        >>> step = ValidateStep(
        ...     name="validate",
        ...     stages=None
        ... )
        >>>
        >>> # Explicit stages
        >>> step = ValidateStep(
        ...     name="validate",
        ...     stages=["format", "lint", "test"],
        ...     retry=2
        ... )
        >>>
        >>> # With auto-fix on failure
        >>> auto_fix = PythonStep(name="auto_fix", action=run_formatter)
        >>> step = ValidateStep(
        ...     name="validate",
        ...     stages=["format", "lint"],
        ...     retry=1,
        ...     on_failure=auto_fix
        ... )
    """

    name: str
    stages: list[str] | str | None = None
    retry: int = DEFAULTS.DEFAULT_RETRY_ATTEMPTS
    on_failure: StepDefinition | None = None
    step_type: StepType = field(default=StepType.VALIDATE, init=False)

    def _resolve_stages(self, context: WorkflowContext) -> list[str]:
        """Resolve stages from explicit list, config key, or default.

        Args:
            context: Workflow execution context.

        Returns:
            List of validation stage names to execute.

        Raises:
            StagesNotFoundError: If stages is a string key not found in config.
        """
        if isinstance(self.stages, list):
            return self.stages
        if self.stages is None:
            # Use default from config
            if context.config and hasattr(context.config, "validation_stages"):
                stages_attr = context.config.validation_stages
                if isinstance(stages_attr, list):
                    return stages_attr
            return []
        # stages is a string key - look up in config
        if context.config and hasattr(context.config, self.stages):
            stages_attr = getattr(context.config, self.stages)
            if isinstance(stages_attr, list):
                return stages_attr
        raise StagesNotFoundError(self.stages)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute validation with retry loop.

        Runs validation stages and retries on failure, optionally executing
        the on_failure step before each retry.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult with success=True if validation passed, or success=False
            if validation failed after all retries. The output contains the
            ValidationResult from the last validation attempt.
        """
        start_time = time.perf_counter()

        try:
            stages = self._resolve_stages(context)
        except StagesNotFoundError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=str(e),
            )

        retries_remaining = self.retry
        last_result = None

        while True:
            # Run validation
            if context.config and hasattr(context.config, "run_validation_stages"):
                result = await context.config.run_validation_stages(stages)
            else:
                # No validation runner configured - treat as pass
                result = ValidationResult(success=True, stages=stages)

            last_result = result

            if result.success:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                return StepResult(
                    name=self.name,
                    step_type=self.step_type,
                    success=True,
                    output=result,
                    duration_ms=duration_ms,
                )

            # Validation failed
            if retries_remaining <= 0:
                break

            # Run on_failure step if present
            if self.on_failure is not None:
                await self.on_failure.execute(context)

            retries_remaining -= 1

        # All retries exhausted
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return StepResult(
            name=self.name,
            step_type=self.step_type,
            success=False,
            output=last_result,
            duration_ms=duration_ms,
            error=f"Validation failed after {self.retry} retries",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence.

        Returns:
            Dictionary with step metadata including stages configuration
            and retry settings.
        """
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "stages": self.stages,
            "retry": self.retry,
            "has_on_failure": self.on_failure is not None,
        }
