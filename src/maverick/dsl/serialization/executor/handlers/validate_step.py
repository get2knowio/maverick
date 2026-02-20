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

# Tools that require source files to operate on.
# If no files match the glob pattern, the stage is skipped.
_TOOL_SOURCE_GLOBS: dict[str, str] = {
    "mypy": "**/*.py",
    "pytest": "**/*.py",
    "ruff": "**/*.py",
    "black": "**/*.py",
    "isort": "**/*.py",
    "pylint": "**/*.py",
    "pyright": "**/*.py",
    "eslint": "**/*.js",
    "tsc": "**/*.ts",
    "cargo": "**/*.rs",
    "go": "**/*.go",
}


def _has_source_files(command: tuple[str, ...], cwd: Path) -> bool:
    """Check whether source files exist for a validation tool.

    Returns True if the tool is unknown (assume files exist) or if
    at least one file matches the tool's expected source glob.

    Args:
        command: The command tuple (first element is the tool name).
        cwd: Working directory to search for source files.

    Returns:
        True if source files exist or tool is unknown, False otherwise.
    """
    tool = command[0] if command else ""
    pattern = _TOOL_SOURCE_GLOBS.get(tool)
    if pattern is None:
        return True  # Unknown tool, don't skip
    try:
        next(cwd.glob(pattern))
        return True
    except StopIteration:
        return False


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
    event_callback: EventCallback | None = None,
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

    # Determine working directory: explicit input > project_root config > cwd
    # The workflow (or parent subworkflow) may pass a cwd input to direct
    # validation into a specific directory (e.g., a hidden jj workspace).
    input_cwd = context.inputs.get("cwd")
    if input_cwd:
        cwd = Path(input_cwd)
    else:
        cwd = Path.cwd()

    # Load config if not provided — use workspace cwd so we pick up the
    # project's maverick.yaml even when running in a hidden workspace.
    if config is None:
        try:
            config = load_config(config_path=cwd / "maverick.yaml")
        except Exception as e:
            logger.warning(f"Failed to load maverick.yaml config: {e}, using defaults")
            config = MaverickConfig()

    validation_config = config.validation
    timeout = validation_config.timeout_seconds

    # Apply project_root from config only when no explicit cwd was given
    if not input_cwd and validation_config.project_root:
        cwd = validation_config.project_root

    # Build ValidationStage objects for each requested stage
    validation_stages: list[ValidationStage] = []
    skipped_stages: list[str] = []

    for stage_name in stages:
        cmd = _get_stage_command(stage_name, validation_config)
        if cmd:
            if not _has_source_files(cmd, cwd):
                logger.info(
                    "Stage '%s' skipped: no source files for '%s'",
                    stage_name,
                    cmd[0],
                )
                skipped_stages.append(stage_name)
                continue
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
        # Include skipped stage results so callers know they were intentional
        skipped_results: dict[str, Any] = {}
        for name in skipped_stages:
            skipped_results[name] = {
                "passed": True,
                "skipped": True,
                "duration_ms": 0,
                "output": f"Skipped: no source files for {name}",
                "errors": [],
            }
        return ValidationResult(
            success=True,
            stages=list(stages),
            stage_results=skipped_results,
        )

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
                if error_count > 0:
                    details = f"{duration_str} {error_count} errors"
                else:
                    # Stage failed but no structured errors parsed — show raw output
                    first_line = (stage_result.output or "").strip().split("\n")[0][:80]
                    details = (
                        f"{duration_str} {first_line}" if first_line else duration_str
                    )
                await stream.emit_stage(
                    stage_result.stage_name,
                    status="failed",
                    details=details,
                )
                logger.warning(
                    f"Validation stage '{stage_result.stage_name}' failed "
                    f"({stage_result.duration_ms}ms, {error_count} errors)"
                )

        # Emit "skipped" for stages the runner never reached
        # (due to continue_on_failure=False causing early exit)
        completed_stage_names = {sr.stage_name for sr in output.stages}
        for stage in validation_stages:
            if stage.name not in completed_stage_names:
                await stream.emit_stage(stage.name, status="skipped")
                stage_results[stage.name] = {
                    "passed": False,
                    "skipped": True,
                    "duration_ms": 0,
                    "output": "Skipped: prior stage failed",
                    "errors": [],
                }

        # Add skipped stages to results
        for name in skipped_stages:
            stage_results[name] = {
                "passed": True,
                "skipped": True,
                "duration_ms": 0,
                "output": f"Skipped: no source files for {name}",
                "errors": [],
            }

        # Include resolved validation commands so the fix loop can reuse them
        # instead of falling back to defaults (which may not match project config)
        resolved_commands: dict[str, list[str]] = {}
        for vs in validation_stages:
            resolved_commands[vs.name] = list(vs.command)
        stage_results["_validation_commands"] = resolved_commands

        return ValidationResult(
            success=output.success,
            stages=list(stages),
            stage_results=stage_results,
        )
