"""Validate step handler for executing validation steps.

This module handles execution of ValidateStepRecord steps by running
actual validation commands from maverick.yaml configuration.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.config import MaverickConfig, ValidationConfig, load_config
from maverick.dsl.context import WorkflowContext
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import ValidateStepRecord
from maverick.dsl.steps.validate import ValidationResult
from maverick.dsl.streaming import StreamingContext
from maverick.logging import get_logger
from maverick.runners.models import ValidationStage
from maverick.runners.validation import ValidationRunner

if TYPE_CHECKING:
    from maverick.dsl.events import ProgressEvent

    EventCallback = Callable[[ProgressEvent], Awaitable[None]]

logger = get_logger(__name__)


def _get_stage_command(
    stage_name: str, validation_config: ValidationConfig
) -> tuple[str, ...] | None:
    """Get the command for a validation stage from config.

    Args:
        stage_name: Name of the stage (format, lint, typecheck, test).
        validation_config: Validation configuration from maverick.yaml.

    Returns:
        Command tuple if stage exists in config, None otherwise.
    """
    stage_to_cmd = {
        "format": validation_config.format_cmd,
        "lint": validation_config.lint_cmd,
        "typecheck": validation_config.typecheck_cmd,
        "test": validation_config.test_cmd,
    }
    cmd_list = stage_to_cmd.get(stage_name)
    if cmd_list:
        return tuple(cmd_list)
    return None


async def execute_validate_step(
    step: ValidateStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    event_callback: "EventCallback | None" = None,
) -> Any:
    """Execute a validation step using ValidationRunner.

    Loads validation commands from maverick.yaml and executes them
    using the ValidationRunner. Falls back to defaults if no config found.

    Args:
        step: ValidateStepRecord containing stages and retry configuration.
        resolved_inputs: Resolved values.
        context: WorkflowContext with inputs and step results.
        registry: Component registry (unused).
        config: Optional MaverickConfig. If None, loads from maverick.yaml.
        event_callback: Optional callback for streaming progress events.

    Returns:
        ValidationResult with success status and stage information.
    """
    # Get stages to run (resolved from expressions or literal list)
    stages = resolved_inputs.get("stages", step.stages)
    if isinstance(stages, str):
        stages = [stages]

    # Load config if not provided
    if config is None:
        try:
            config = load_config()
        except Exception as e:
            logger.warning(f"Failed to load maverick.yaml config: {e}, using defaults")
            config = MaverickConfig()

    validation_config = config.validation
    timeout = validation_config.timeout_seconds

    # Build ValidationStage objects for each requested stage
    validation_stages: list[ValidationStage] = []
    skipped_stages: list[str] = []

    for stage_name in stages:
        cmd = _get_stage_command(stage_name, validation_config)
        if cmd:
            validation_stages.append(
                ValidationStage(
                    name=stage_name,
                    command=cmd,
                    fixable=False,  # Fix logic is handled by fixer agent
                    fix_command=None,
                    timeout_seconds=timeout,
                )
            )
        else:
            logger.debug(f"Stage '{stage_name}' not configured, skipping")
            skipped_stages.append(stage_name)

    # If no stages to run, return success
    if not validation_stages:
        logger.info("No validation stages configured to run")
        return ValidationResult(
            success=True,
            stages=list(stages),
            stage_results={},
        )

    # Determine working directory (use project_root from config or cwd)
    cwd = validation_config.project_root or Path.cwd()

    # Create streaming context for progress events
    async with StreamingContext(event_callback, step.name, "validation") as stream:
        # Create and run ValidationRunner
        runner = ValidationRunner(
            stages=validation_stages,
            cwd=cwd,
            continue_on_failure=False,  # Fail fast on first error
        )

        try:
            # Emit stage indicators as validation runs
            for stage in validation_stages:
                await stream.emit_stage(stage.name, status="running")

            output = await runner.run()
        except Exception as e:
            logger.error(f"Validation runner failed: {e}")
            await stream.emit_progress(f"Validation failed: {e}", level="error")
            return ValidationResult(
                success=False,
                stages=list(stages),
                stage_results={"error": str(e)},
            )

        # Build stage results dict and emit completion status
        stage_results: dict[str, Any] = {}
        for stage_result in output.stages:
            stage_results[stage_result.stage_name] = {
                "passed": stage_result.passed,
                "duration_ms": stage_result.duration_ms,
                "output": stage_result.output[:1000] if stage_result.output else None,
                "errors": [
                    {"file": e.file, "line": e.line, "message": e.message}
                    for e in stage_result.errors
                ],
            }

            # Emit stage completion status
            duration_str = f"({stage_result.duration_ms}ms)"
            if stage_result.passed:
                await stream.emit_stage(
                    stage_result.stage_name,
                    status="passed",
                    details=duration_str,
                )
                logger.info(
                    f"Validation stage '{stage_result.stage_name}' passed "
                    f"({stage_result.duration_ms}ms)"
                )
            else:
                error_count = len(stage_result.errors)
                await stream.emit_stage(
                    stage_result.stage_name,
                    status="failed",
                    details=f"{duration_str} {error_count} errors",
                )
                logger.warning(
                    f"Validation stage '{stage_result.stage_name}' failed "
                    f"({stage_result.duration_ms}ms, {error_count} errors)"
                )

        return ValidationResult(
            success=output.success,
            stages=list(stages),
            stage_results=stage_results,
        )
