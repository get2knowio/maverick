"""Validation actions for workflow execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.logging import get_logger

logger = get_logger(__name__)


class _ValidationStillFailingError(Exception):
    """Internal exception to signal validation is still failing and retry is needed."""

    pass


# =============================================================================
# Stage name to command mapping for validation re-runs
# =============================================================================

# Default stage commands for common validation stages
# These are used when re-running validation after fix attempts
DEFAULT_STAGE_COMMANDS: dict[str, tuple[str, ...]] = {
    "format": ("ruff", "format", "--check", "."),
    "lint": ("ruff", "check", "."),
    "typecheck": ("mypy", "."),
    "test": ("pytest", "-x", "--tb=short"),
}


async def run_fix_retry_loop(
    stages: list[str],
    max_attempts: int,
    fixer_agent: str,
    validation_result: dict[str, Any],
    cwd: str | None = None,
    stream_callback: Any | None = None,
) -> dict[str, Any]:
    """Execute fix-and-retry loop for validation failures.

    This function implements FR-002: Must actually invoke fixer agent and
    retry validation. It iterates up to max_attempts times, invoking the fixer
    agent to address validation failures, then re-running validation to check
    if issues were resolved.

    Args:
        stages: Validation stages to run
        max_attempts: Maximum fix attempts (0 disables retry)
        fixer_agent: Name of fixer agent to use (currently unused, FixerAgent is used)
        validation_result: Initial validation result from validate step
        cwd: Working directory for validation commands (defaults to Path.cwd())
        stream_callback: Optional callback for streaming agent output

    Returns:
        Dict with:
            - passed: bool - Whether validation ultimately passed
            - attempts: int - Number of fix attempts made
            - fixes_applied: list[str] - Description of each fix applied
            - final_result: dict - Final validation result after all attempts

    Note:
        This action follows the graceful failure principle: one agent failure
        shouldn't crash the workflow. If the fixer agent fails, we record the
        error and continue, allowing the workflow to proceed with a failed status.
    """
    # If initial validation passed, return immediately with no attempts
    if validation_result.get("success", False):
        return {
            "passed": True,
            "attempts": 0,
            "fixes_applied": [],
            "final_result": validation_result,
        }

    # If max_attempts is 0, don't retry - just return the failure
    if max_attempts <= 0:
        return {
            "passed": False,
            "attempts": 0,
            "fixes_applied": [],
            "final_result": validation_result,
        }

    # Resolve working directory
    working_dir = Path(cwd) if cwd else Path.cwd()

    # Track state across retry attempts
    attempts = 0
    fixes_applied: list[str] = []
    current_result = validation_result

    # Execute fix-retry loop with tenacity
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(_ValidationStillFailingError),
            reraise=True,
        ):
            with attempt:
                attempts = attempt.retry_state.attempt_number
                logger.info(
                    "Fix attempt %d/%d using fixer agent '%s'",
                    attempts,
                    max_attempts,
                    fixer_agent,
                )

                try:
                    # Build fix context from validation errors
                    fix_prompt = _build_fix_prompt(current_result, stages, attempts)

                    # Invoke the fixer agent
                    fix_result = await _invoke_fixer_agent(
                        fix_prompt=fix_prompt,
                        cwd=working_dir,
                        stream_callback=stream_callback,
                    )

                    if fix_result.get("success", False):
                        fix_description = fix_result.get(
                            "changes_made",
                            f"Applied fix for {_summarize_errors(current_result)}",
                        )
                        fixes_applied.append(fix_description)
                        logger.info(
                            "Fix attempt %d succeeded: %s", attempts, fix_description
                        )
                    else:
                        error_msg = fix_result.get("error", "Unknown error")
                        fixes_applied.append(
                            f"Fix attempt {attempts} failed: {error_msg}"
                        )
                        logger.warning("Fix attempt %d failed: %s", attempts, error_msg)
                        # Continue to re-run validation - fix may have been partial

                    # Re-run validation to check if fixed
                    current_result = await _run_validation(
                        stages=stages,
                        cwd=working_dir,
                    )

                    if current_result.get("success", False):
                        logger.info(
                            "Validation passed after fix attempt %d",
                            attempts,
                        )
                        # Success - exit the retry loop
                        return {
                            "passed": True,
                            "attempts": attempts,
                            "fixes_applied": fixes_applied,
                            "final_result": current_result,
                        }

                    # Validation still failing - signal retry needed
                    logger.debug(
                        "Validation still failing after fix attempt %d, "
                        "%d attempt(s) remaining",
                        attempts,
                        max_attempts - attempts,
                    )
                    raise _ValidationStillFailingError()

                except _ValidationStillFailingError:
                    # Re-raise to trigger tenacity retry
                    raise
                except Exception as e:
                    # Graceful failure: log error but don't crash the workflow
                    logger.warning(
                        "Fix attempt %d failed with error: %s",
                        attempts,
                        str(e),
                        exc_info=True,
                    )
                    fixes_applied.append(f"Fix attempt {attempts} failed: {str(e)}")
                    # Signal retry needed despite the error
                    raise _ValidationStillFailingError() from e

    except _ValidationStillFailingError:
        # All retries exhausted, validation still failing
        pass

    # Return the fix loop results
    # Note: The 'passed' status reflects whether validation succeeded after fixes
    return {
        "passed": current_result.get("success", False),
        "attempts": attempts,
        "fixes_applied": fixes_applied,
        "final_result": current_result,
    }


async def _invoke_fixer_agent(
    fix_prompt: str,
    cwd: Path,
    stream_callback: Any | None = None,
) -> dict[str, Any]:
    """Invoke the FixerAgent to apply fixes based on the prompt.

    Args:
        fix_prompt: The prompt describing fixes to apply
        cwd: Working directory for the agent
        stream_callback: Optional callback for streaming agent output

    Returns:
        Dict with success status and fix details or error message
    """
    try:
        # Import here to avoid circular imports
        from maverick.agents.context import AgentContext
        from maverick.agents.fixer import FixerAgent
        from maverick.config import MaverickConfig

        # Create agent instance
        agent = FixerAgent()

        # Set stream callback if provided (for CLI/TUI output streaming)
        if stream_callback is not None:
            agent.stream_callback = stream_callback

        # Build context with the fix prompt
        context = AgentContext.from_cwd(
            cwd=cwd,
            config=MaverickConfig(),
            extra={"prompt": fix_prompt},
        )

        # Execute the agent
        result = await agent.execute(context)

        # Parse the result
        if result.success:
            # Try to extract structured info from output
            output = result.output or ""
            try:
                import json

                parsed = json.loads(output)
                return {
                    "success": True,
                    "file_modified": parsed.get("file_modified", False),
                    "file_path": parsed.get("file_path", ""),
                    "changes_made": parsed.get("changes_made", "Fix applied"),
                }
            except (json.JSONDecodeError, TypeError):
                return {
                    "success": True,
                    "changes_made": output[:200] if output else "Fix applied",
                }
        else:
            # Extract error message from result
            error_messages = []
            for error in result.errors or []:
                if hasattr(error, "message"):
                    error_messages.append(error.message)
                else:
                    error_messages.append(str(error))

            return {
                "success": False,
                "error": "; ".join(error_messages) if error_messages else "Fix failed",
            }

    except ImportError as e:
        logger.error("Failed to import agent modules: %s", e)
        return {"success": False, "error": f"Import error: {e}"}
    except ValueError as e:
        # AgentContext.from_cwd raises ValueError for invalid directories
        logger.error("Invalid context configuration: %s", e)
        return {"success": False, "error": f"Context error: {e}"}
    except Exception as e:
        logger.exception("Unexpected error invoking fixer agent: %s", e)
        return {"success": False, "error": str(e)}


async def _run_validation(
    stages: list[str],
    cwd: Path,
) -> dict[str, Any]:
    """Re-run validation stages after fix attempts.

    Args:
        stages: List of stage names to run
        cwd: Working directory for validation commands

    Returns:
        Validation result dict with success status and per-stage results
    """
    try:
        # Import here to avoid circular imports
        from maverick.runners.models import ValidationStage as RunnerValidationStage
        from maverick.runners.validation import ValidationRunner

        # Build ValidationStage objects from stage names
        validation_stages = []
        for stage_name in stages:
            command = DEFAULT_STAGE_COMMANDS.get(stage_name)
            if command:
                validation_stages.append(
                    RunnerValidationStage(
                        name=stage_name,
                        command=command,
                        fixable=False,  # Don't auto-fix during re-run
                        timeout_seconds=300.0,
                    )
                )
            else:
                logger.warning(
                    "Unknown stage '%s', skipping validation re-run for this stage",
                    stage_name,
                )

        if not validation_stages:
            logger.error("No valid stages to run for validation")
            return {"success": False, "stages": [], "error": "No valid stages"}

        # Create runner and execute
        runner = ValidationRunner(
            stages=validation_stages,
            cwd=cwd,
            continue_on_failure=True,  # Run all stages to get complete picture
        )

        output = await runner.run()

        # Convert ValidationOutput to dict format expected by the rest of the code
        stage_results = []
        for stage_result in output.stages:
            stage_results.append(
                {
                    "stage": stage_result.stage_name,
                    "success": stage_result.passed,
                    "output": stage_result.output,
                    "duration_ms": stage_result.duration_ms,
                    "error": stage_result.output if not stage_result.passed else None,
                }
            )

        return {
            "success": output.success,
            "stages": stage_results,
            "total_duration_ms": output.total_duration_ms,
        }

    except ImportError as e:
        logger.error("Failed to import validation modules: %s", e)
        return {"success": False, "stages": [], "error": f"Import error: {e}"}
    except Exception as e:
        logger.exception("Unexpected error running validation: %s", e)
        return {"success": False, "stages": [], "error": str(e)}


def _build_fix_prompt(
    validation_result: dict[str, Any],
    stages: list[str],
    attempt_number: int,
) -> str:
    """Build a prompt for the fixer agent based on validation errors.

    Args:
        validation_result: Validation result containing errors
        stages: Validation stages that were run
        attempt_number: Current fix attempt number

    Returns:
        Formatted prompt string for fixer agent
    """
    errors = []
    stage_results = validation_result.get("stage_results", {})
    for stage_name, stage_result in stage_results.items():
        if not stage_result.get("passed", True):
            # Get error details from output or errors list
            error_output = stage_result.get("output", "")
            error_list = stage_result.get("errors", [])
            if error_list:
                error_msgs = [e.get("message", str(e)) for e in error_list]
                error_msg = "; ".join(error_msgs)
            elif error_output:
                error_msg = error_output[:500]  # Truncate long output
            else:
                error_msg = "unknown error"
            errors.append(f"- {stage_name}: {error_msg}")

    errors_text = "\n".join(errors) if errors else "No specific errors provided"

    return f"""Fix validation failures (Attempt {attempt_number}):

Validation Stages Run: {", ".join(stages)}

Errors:
{errors_text}

Please analyze these validation failures and apply minimal fixes to resolve them.
Focus on fixing the errors without refactoring unrelated code.
"""


def _summarize_errors(validation_result: dict[str, Any]) -> str:
    """Summarize validation errors for logging.

    Args:
        validation_result: Validation result containing errors

    Returns:
        Brief summary of errors
    """
    stage_results = validation_result.get("stage_results", {})
    failed_stages = [
        stage_name
        for stage_name, result in stage_results.items()
        if not result.get("passed", True)
    ]
    if failed_stages:
        return f"{len(failed_stages)} stage(s): {', '.join(failed_stages)}"
    return "validation failures"


async def generate_validation_report(
    initial_result: dict[str, Any],
    fix_loop_result: dict[str, Any] | None = None,
    max_attempts: int = 3,
    stages: list[str] | None = None,
    fix_enabled: bool = True,
    fix_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate final validation report.

    This function implements FR-003: Must aggregate stage results correctly.
    It combines the initial validation result with any fix loop results to
    produce a comprehensive report of the validation-and-fix process.

    Args:
        initial_result: Initial validation result from validate step
        fix_loop_result: Result from fix_retry_loop (used by validate_and_fix.yaml)
        max_attempts: Configured max attempts for context
        stages: Stages that were run
        fix_enabled: Whether fix was enabled (for validate.yaml)
        fix_result: Fix result (alternative path for validate.yaml)

    Returns:
        ValidationReportResult as dict with:
            - passed: bool - Overall validation success
            - stages: list[dict] - Per-stage results with name, passed, errors, duration
            - attempts: int - Number of fix attempts made
            - fixes_applied: list[str] - Fixes that were applied
            - remaining_errors: list[str] - Errors that couldn't be fixed
            - suggestions: list[str] - Manual fix suggestions

    Note:
        This function handles multiple input paths:
        1. validate_and_fix.yaml: Uses fix_loop_result for final status
        2. validate.yaml with fix=True: Uses fix_result for final status
        3. validate.yaml with fix=False: Uses initial_result only
    """
    # Derive stages from input if not explicitly provided
    if stages:
        pass  # Use provided stages
    elif isinstance(initial_result, dict) and initial_result.get("stages"):
        # Extract stage names from initial_result
        raw_stages = initial_result.get("stages", [])
        extracted_stages: list[str] = []
        for s in raw_stages:
            if isinstance(s, dict):
                stage_name = s.get("stage") or s.get("name") or ""
                if isinstance(stage_name, str):
                    extracted_stages.append(stage_name)
        stages = [s for s in extracted_stages if s]  # Filter empty names

    # Fall back to default stages if still empty
    if not stages:
        stages = ["format", "lint", "typecheck", "test"]

    # Validate and normalize initial_result
    if not isinstance(initial_result, dict):
        logger.warning(
            "initial_result is not a dict (got %s), treating as passed",
            type(initial_result).__name__,
        )
        initial_result = {"success": True, "stages": []}

    # Determine which result to use for final status
    # Priority: fix_result > fix_loop_result > initial_result
    fix_data = fix_result or fix_loop_result

    # Validate fix_data and filter out non-fix results
    if fix_data and not isinstance(fix_data, dict):
        logger.warning(
            "fix_data is not a dict (got %s), ignoring",
            type(fix_data).__name__,
        )
        fix_data = None
    elif (
        fix_data
        and isinstance(fix_data, dict)
        and "message" in fix_data
        and "logged" in fix_data
    ):
        # This is a log_message result, not a fix result - ignore it
        logger.debug("Ignoring log_message result in fix_data")
        fix_data = None

    # Extract final status and metrics
    if fix_data:
        # Use fix loop results
        passed = fix_data.get("passed", False)
        attempts = fix_data.get("attempts", 0)
        fixes_applied = list(fix_data.get("fixes_applied", []))
        # Get final validation result from fix loop
        final_validation = fix_data.get("final_result", initial_result)
    else:
        # Use initial results only (no fixes were attempted or applicable)
        passed = initial_result.get("success", False)
        attempts = 0
        fixes_applied = []
        final_validation = initial_result

    # Build per-stage results by aggregating from validation output
    # FR-003: Aggregate stage results correctly
    stage_results = _aggregate_stage_results(
        stages=stages,
        validation_result=final_validation,
    )

    # Extract remaining errors from failed stages
    remaining_errors = _extract_remaining_errors(stage_results)

    # Generate suggestions for manual fixes
    suggestions = _generate_fix_suggestions(
        stage_results=stage_results,
        attempts=attempts,
        max_attempts=max_attempts,
        passed=passed,
    )

    return {
        "passed": passed,
        "stages": stage_results,
        "attempts": attempts,
        "fixes_applied": fixes_applied,
        "remaining_errors": remaining_errors,
        "suggestions": suggestions,
    }


def _aggregate_stage_results(
    stages: list[str],
    validation_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Aggregate per-stage results from validation output.

    This implements FR-003 requirement to aggregate stage results correctly.

    Args:
        stages: List of stage names that were run
        validation_result: Validation result containing stage details

    Returns:
        List of stage result dicts with name, passed, errors, duration_ms
    """
    stage_results = []
    raw_stages = validation_result.get("stages", [])

    # Build a lookup map for raw stage results
    stage_map = {}
    for raw_stage in raw_stages:
        if isinstance(raw_stage, dict):
            stage_name = raw_stage.get("stage", raw_stage.get("name", ""))
            if stage_name:
                stage_map[stage_name] = raw_stage

    # Build result for each expected stage
    for stage_name in stages:
        raw_result = stage_map.get(stage_name)

        if raw_result:
            # Extract actual stage result
            passed = raw_result.get("success", raw_result.get("passed", False))
            error_msg = raw_result.get("error", raw_result.get("output", ""))
            errors = [error_msg] if error_msg and not passed else []
            duration_ms = raw_result.get("duration_ms", 0)
        else:
            # Stage wasn't run or not found in results
            logger.debug("Stage '%s' not found in validation results", stage_name)
            passed = False
            errors = [f"Stage '{stage_name}' was not executed"]
            duration_ms = 0

        stage_results.append(
            {
                "name": stage_name,
                "passed": passed,
                "errors": errors,
                "duration_ms": duration_ms,
            }
        )

    return stage_results


def _extract_remaining_errors(stage_results: list[dict[str, Any]]) -> list[str]:
    """Extract remaining error messages from failed stages.

    Args:
        stage_results: List of stage result dicts

    Returns:
        List of error messages from failed stages
    """
    errors = []
    for stage in stage_results:
        if not stage.get("passed", True):
            stage_name = stage.get("name", "unknown")
            stage_errors = stage.get("errors", [])
            for error in stage_errors:
                if error:
                    errors.append(f"[{stage_name}] {error}")

    return errors


def _generate_fix_suggestions(
    stage_results: list[dict[str, Any]],
    attempts: int,
    max_attempts: int,
    passed: bool,
) -> list[str]:
    """Generate suggestions for manual fixes based on validation results.

    Args:
        stage_results: List of stage result dicts
        attempts: Number of fix attempts made
        max_attempts: Maximum attempts configured
        passed: Whether validation ultimately passed

    Returns:
        List of suggestion strings for manual intervention
    """
    if passed:
        return []

    suggestions = []

    # If we exhausted fix attempts
    if attempts >= max_attempts and max_attempts > 0:
        suggestions.append(
            f"Automatic fixes exhausted ({attempts} attempts). "
            "Manual intervention required."
        )

    # Per-stage suggestions
    failed_stages = [s for s in stage_results if not s.get("passed", True)]

    if any(s.get("name") == "format" for s in failed_stages):
        suggestions.append(
            "Format errors detected. Try running the formatter manually: "
            "`ruff format .` or your project's format command."
        )

    if any(s.get("name") == "lint" for s in failed_stages):
        suggestions.append(
            "Linting errors detected. Review the errors above and fix manually, "
            "or try `ruff check --fix .` for auto-fixable issues."
        )

    if any(s.get("name") == "typecheck" for s in failed_stages):
        suggestions.append(
            "Type checking errors detected. Review mypy output and add type hints "
            "or type: ignore comments as needed."
        )

    if any(s.get("name") == "test" for s in failed_stages):
        suggestions.append(
            "Test failures detected. Review test output, fix failing tests, "
            "and re-run: `pytest` or your project's test command."
        )

    # If no specific suggestions, provide generic guidance
    if not suggestions:
        suggestions.append(
            "Review validation output above for details on what needs to be fixed."
        )

    return suggestions


def log_message(message: str) -> dict[str, Any]:
    """Log a message (for skip scenarios in validate.yaml).

    Args:
        message: Message to log

    Returns:
        Dict with logged message
    """
    logger.info(message)
    return {"message": message, "logged": True}
