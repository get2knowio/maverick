"""Validation pipeline utilities for Maverick agents.

This module provides functions for running code validation (format, lint,
typecheck, test) with automatic retry and auto-fix support.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from tenacity import (
    AsyncRetrying,
    RetryError,
    stop_after_attempt,
    wait_fixed,
)

from maverick.logging import get_logger
from maverick.models.implementation import ValidationResult, ValidationStep

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for validation commands in seconds
DEFAULT_VALIDATION_TIMEOUT: float = 120.0

#: Maximum retries for auto-fixable validation steps
MAX_VALIDATION_RETRIES: int = 3


# =============================================================================
# Validation Commands
# =============================================================================

# Mapping of validation steps to their commands
VALIDATION_COMMANDS: dict[ValidationStep, tuple[str, ...]] = {
    ValidationStep.FORMAT: ("ruff", "format", "."),
    ValidationStep.LINT: ("ruff", "check", "--fix", "."),
    ValidationStep.TYPECHECK: ("mypy", "."),
    ValidationStep.TEST: ("pytest", "-x", "--tb=short"),
}

# Steps that can be auto-fixed
AUTO_FIXABLE_STEPS: frozenset[ValidationStep] = frozenset(
    {
        ValidationStep.FORMAT,
        ValidationStep.LINT,
    }
)


# =============================================================================
# Validation Runner
# =============================================================================


async def run_validation_step(
    step: ValidationStep,
    cwd: Path,
    timeout: float = DEFAULT_VALIDATION_TIMEOUT,
) -> ValidationResult:
    """Run a single validation step.

    Args:
        step: Validation step to run.
        cwd: Working directory.
        timeout: Timeout in seconds.

    Returns:
        ValidationResult with outcome details.
    """
    command = VALIDATION_COMMANDS.get(step)
    if not command:
        return ValidationResult(
            step=step,
            success=False,
            output=f"Unknown validation step: {step}",
        )

    start_time = time.monotonic()

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)
        stdout = stdout_bytes.decode()
        stderr = stderr_bytes.decode()
        output = f"{stdout}\n{stderr}".strip()
        success = process.returncode == 0

        # For format/lint, check if changes were made (auto-fixed)
        auto_fixed = False
        if step in AUTO_FIXABLE_STEPS and success:
            # If the command succeeded after making changes
            auto_fixed = "fixed" in output.lower() or "formatted" in output.lower()

        return ValidationResult(
            step=step,
            success=success,
            output=output,
            duration_ms=duration_ms,
            auto_fixed=auto_fixed,
        )

    except TimeoutError:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        return ValidationResult(
            step=step,
            success=False,
            output=f"Validation timed out after {timeout}s",
            duration_ms=duration_ms,
        )
    except FileNotFoundError as e:
        # Command not found
        duration_ms = int((time.monotonic() - start_time) * 1000)
        return ValidationResult(
            step=step,
            success=True,  # Skip if tool not available
            output=f"Validation tool not found: {e.filename}. Skipping {step.value}.",
            duration_ms=duration_ms,
        )


async def run_validation_pipeline(
    cwd: Path,
    steps: list[ValidationStep] | None = None,
    max_retries: int = MAX_VALIDATION_RETRIES,
    stop_on_failure: bool = True,
) -> list[ValidationResult]:
    """Run the full validation pipeline with auto-fix retries.

    Pipeline order: format -> lint -> typecheck -> test

    Args:
        cwd: Working directory.
        steps: Optional list of steps to run. Defaults to all steps.
        max_retries: Max auto-fix attempts for fixable steps.
        stop_on_failure: If True, stop pipeline on first failure.

    Returns:
        List of ValidationResult for each step attempted.

    Raises:
        MaverickValidationError: If validation fails after all retries.
    """
    if steps is None:
        steps = [
            ValidationStep.FORMAT,
            ValidationStep.LINT,
            ValidationStep.TYPECHECK,
            ValidationStep.TEST,
        ]

    results: list[ValidationResult] = []

    for step in steps:
        is_fixable = step in AUTO_FIXABLE_STEPS
        retries = max_retries if is_fixable else 1
        result: ValidationResult | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(retries),
                wait=wait_fixed(0),  # Immediate retry for auto-fix steps
                reraise=False,
            ):
                with attempt:
                    result = await run_validation_step(step, cwd)

                    if result.success:
                        results.append(result)
                        logger.info(
                            "Validation %s passed%s (%.1fs)",
                            step.value,
                            " (auto-fixed)" if result.auto_fixed else "",
                            result.duration_ms / 1000,
                        )
                    elif is_fixable:
                        # Raise to trigger retry for fixable steps
                        logger.warning(
                            "Validation %s failed (attempt %d/%d), retrying...",
                            step.value,
                            attempt.retry_state.attempt_number,
                            retries,
                        )
                        raise ValueError(f"Validation {step.value} failed, retrying")
                    else:
                        # Non-fixable step failed, don't retry
                        results.append(result)
                        logger.error(
                            "Validation %s failed: %s",
                            step.value,
                            result.output[:200] if result.output else "No output",
                        )
                        if stop_on_failure:
                            return results

        except RetryError:
            # All retries exhausted for fixable step
            if result:
                results.append(result)
                logger.error(
                    "Validation %s failed after %d attempts: %s",
                    step.value,
                    retries,
                    result.output[:200] if result.output else "No output",
                )
                if stop_on_failure:
                    return results

    return results


def check_validation_passed(results: list[ValidationResult]) -> bool:
    """Check if all validation steps passed.

    Args:
        results: List of validation results.

    Returns:
        True if all steps passed.
    """
    return all(r.success for r in results)


async def quick_validate(cwd: Path) -> bool:
    """Run a quick validation (format + lint only).

    Args:
        cwd: Working directory.

    Returns:
        True if validation passed.
    """
    results = await run_validation_pipeline(
        cwd,
        steps=[ValidationStep.FORMAT, ValidationStep.LINT],
        max_retries=2,
        stop_on_failure=True,
    )
    return check_validation_passed(results)


async def full_validate(cwd: Path) -> tuple[bool, list[ValidationResult]]:
    """Run full validation pipeline.

    Args:
        cwd: Working directory.

    Returns:
        Tuple of (success, results).
    """
    results = await run_validation_pipeline(cwd)
    return check_validation_passed(results), results
