"""Validation runner for executing validation stages."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from maverick.runners.command import CommandRunner
from maverick.runners.models import StageResult, ValidationOutput, ValidationStage
from maverick.runners.parsers import get_parsers

__all__ = ["ValidationRunner"]

logger = logging.getLogger(__name__)


class ValidationRunner:
    """Execute validation stages sequentially with fix attempts."""

    def __init__(
        self,
        stages: list[ValidationStage],
        cwd: Path | None = None,
        continue_on_failure: bool = False,
    ) -> None:
        self._stages = stages
        self._cwd = cwd
        self._continue_on_failure = continue_on_failure
        self._command_runner = CommandRunner(cwd=cwd)

    async def run(self) -> ValidationOutput:
        """Execute all stages and return aggregated results."""
        start_time = time.monotonic()
        stage_results: list[StageResult] = []
        overall_success = True

        for stage in self._stages:
            logger.debug("Running validation stage: %s", stage.name)
            result = await self._run_stage(stage)
            stage_results.append(result)

            if not result.passed:
                overall_success = False
                logger.warning(
                    "Validation stage '%s' failed (duration=%dms, fix_attempts=%d)",
                    stage.name,
                    result.duration_ms,
                    result.fix_attempts,
                )
                if result.output:
                    # Log first 500 chars of output for debugging
                    logger.debug("Stage output: %s", result.output[:500])
                if not self._continue_on_failure:
                    break
            else:
                logger.debug(
                    "Validation stage '%s' passed (duration=%dms)",
                    stage.name,
                    result.duration_ms,
                )

        total_duration_ms = int((time.monotonic() - start_time) * 1000)

        return ValidationOutput(
            success=overall_success,
            stages=tuple(stage_results),
            total_duration_ms=total_duration_ms,
        )

    async def _run_stage(self, stage: ValidationStage) -> StageResult:
        """Run a single stage with fix attempts if needed."""
        start_time = time.monotonic()
        fix_attempts = 0

        # Run the stage command
        result = await self._command_runner.run(
            list(stage.command),
            timeout=stage.timeout_seconds,
        )

        # If failed and fixable, try to fix
        if not result.success and stage.fixable and stage.fix_command:
            fix_attempts = 1
            logger.info(
                "Stage '%s' failed, attempting auto-fix with command: %s",
                stage.name,
                " ".join(stage.fix_command),
            )
            await self._command_runner.run(
                list(stage.fix_command),
                timeout=stage.timeout_seconds,
            )
            # Re-run the check
            logger.debug("Re-running validation after fix attempt: %s", stage.name)
            result = await self._command_runner.run(
                list(stage.command),
                timeout=stage.timeout_seconds,
            )

        # Parse errors from output
        errors = []
        for parser in get_parsers(result.output):
            errors.extend(parser.parse(result.output))

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return StageResult(
            stage_name=stage.name,
            passed=result.success,
            output=result.output,
            duration_ms=duration_ms,
            fix_attempts=fix_attempts,
            errors=tuple(errors),
        )
