"""Validation runner for executing validation stages."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.runners.preflight import ValidationResult

from maverick.logging import get_logger
from maverick.runners.command import CommandRunner
from maverick.runners.models import StageResult, ValidationOutput, ValidationStage
from maverick.runners.parsers import get_parsers

__all__ = ["ValidationRunner"]

logger = get_logger(__name__)

# Remediation hints for common validation tools
TOOL_INSTALLATION_HINTS: dict[str, str] = {
    "ruff": "Install: pip install ruff",
    "mypy": "Install: pip install mypy",
    "pytest": "Install: pip install pytest",
    "black": "Install: pip install black",
    "isort": "Install: pip install isort",
    "flake8": "Install: pip install flake8",
    "pylint": "Install: pip install pylint",
    "bandit": "Install: pip install bandit",
    "pyright": "Install: pip install pyright or npm install -g pyright",
    "prettier": "Install: npm install -g prettier",
    "eslint": "Install: npm install -g eslint",
    "tsc": "Install: npm install -g typescript",
    "npm": "Install Node.js from https://nodejs.org/",
    "node": "Install Node.js from https://nodejs.org/",
    "cargo": "Install Rust from https://rustup.rs/",
    "rustc": "Install Rust from https://rustup.rs/",
    "go": "Install Go from https://go.dev/dl/",
    "docker": "Install Docker from https://docker.com/",
}


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

    async def validate(self) -> ValidationResult:
        """Validate that all required tools are available on PATH.

        Checks that the first item of each stage's command (the tool name)
        is available via shutil.which(). Does not raise exceptions - all
        failures are reported in the returned ValidationResult.

        Returns:
            ValidationResult with success=True if all tools are present,
            or success=False with errors listing missing tools.
        """
        from maverick.runners.preflight import ValidationResult

        start_time = time.monotonic()
        errors: list[str] = []
        warnings: list[str] = []

        for stage in self._stages:
            if not stage.command:
                warnings.append(f"Stage '{stage.name}' has empty command")
                continue

            tool_name = stage.command[0]

            try:
                tool_path = shutil.which(tool_name)
                if tool_path is None:
                    hint = TOOL_INSTALLATION_HINTS.get(tool_name, "")
                    if hint:
                        errors.append(
                            f"Tool '{tool_name}' (stage '{stage.name}') "
                            f"not found on PATH. {hint}"
                        )
                    else:
                        errors.append(
                            f"Tool '{tool_name}' (stage '{stage.name}') "
                            "not found on PATH"
                        )
                else:
                    logger.debug(
                        "Tool '%s' found at '%s' for stage '%s'",
                        tool_name,
                        tool_path,
                        stage.name,
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"Error checking tool '{tool_name}' (stage '{stage.name}'): {exc}"
                )

        duration_ms = int((time.monotonic() - start_time) * 1000)

        return ValidationResult(
            success=len(errors) == 0,
            component="ValidationRunner",
            errors=tuple(errors),
            warnings=tuple(warnings),
            duration_ms=duration_ms,
        )

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
