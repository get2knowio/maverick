"""Validation workflow implementation.

Orchestrates validation stages (format, lint, build, test) with auto-fix
capabilities and progress updates for TUI consumption.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from maverick.models.validation import (
    ProgressUpdate,
    StageResult,
    StageStatus,
    ValidationStage,
    ValidationWorkflowConfig,
    ValidationWorkflowResult,
)

if TYPE_CHECKING:
    from maverick.agents.base import MaverickAgent

__all__ = ["ValidationWorkflow", "create_python_workflow"]

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of executing a single command."""

    return_code: int
    stdout: str
    stderr: str
    error: str | None = None
    timed_out: bool = False
    command_not_found: bool = False


class ValidationWorkflow:
    """Orchestrates validation stages with fix agent integration.

    Executes configured validation stages in sequence, yielding progress
    updates for TUI consumption. When a fixable stage fails, invokes the
    fix agent to attempt repairs before retrying.

    Note:
        Cancellation is cooperative and checked between stages and fix attempts.
        Long-running commands will not be interrupted until they timeout or
        complete naturally. The workflow respects stage timeout settings.

    Attributes:
        _stages: List of validation stages to execute.
        _fix_agent: Optional agent for fix attempts.
        _config: Workflow configuration options.
        _cancel_event: Asyncio event for cooperative cancellation.
        _result: Cached result after workflow completion.
    """

    def __init__(
        self,
        stages: list[ValidationStage],
        fix_agent: MaverickAgent | None = None,
        config: ValidationWorkflowConfig | None = None,
    ) -> None:
        """Initialize the validation workflow.

        Args:
            stages: List of validation stages to execute in order.
            fix_agent: Optional agent for attempting fixes on failed stages.
            config: Optional workflow configuration.
        """
        self._stages = stages
        self._fix_agent = fix_agent
        self._config = config or ValidationWorkflowConfig()
        self._cancel_event = asyncio.Event()
        self._result: ValidationWorkflowResult | None = None
        self._start_time: float | None = None

    async def _execute_command(self, stage: ValidationStage) -> CommandResult:
        """Execute a stage command as a subprocess.

        Args:
            stage: The validation stage containing the command to execute.

        Returns:
            CommandResult with return code, output, and any error information.
        """
        command_str = " ".join(stage.command)
        logger.debug(f"Executing command: {command_str}")

        try:
            process = await asyncio.create_subprocess_exec(
                *stage.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.cwd,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=stage.timeout_seconds,
                )
                return CommandResult(
                    return_code=process.returncode or 0,
                    stdout=stdout_bytes.decode("utf-8", errors="replace"),
                    stderr=stderr_bytes.decode("utf-8", errors="replace"),
                )
            except asyncio.TimeoutError:
                # Kill the process on timeout
                process.kill()
                try:
                    # Give the process a short window to terminate after kill
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Process didn't terminate in time, log and continue
                    logger.error(
                        f"Process failed to terminate after kill: {command_str}"
                    )
                return CommandResult(
                    return_code=-1,
                    stdout="",
                    stderr="",
                    error=f"Command timed out after {stage.timeout_seconds} seconds",
                    timed_out=True,
                )
        except FileNotFoundError as e:
            return CommandResult(
                return_code=-1,
                stdout="",
                stderr="",
                error=f"Command not found: {e}",
                command_not_found=True,
            )
        except Exception as e:
            return CommandResult(
                return_code=-1,
                stdout="",
                stderr="",
                error=f"Error executing command: {e}",
            )

    async def _invoke_fix_agent(
        self, stage: ValidationStage, error_output: str
    ) -> bool:
        """Invoke the fix agent to attempt repairs.

        Args:
            stage: The stage that failed.
            error_output: The error output from the failed command.

        Returns:
            True if fix agent was invoked, False if no fix agent available.
        """
        if self._fix_agent is None:
            return False

        try:
            # Invoke the fix agent with stage and error information.
            # Fix agent execute signature is flexible and accepts varying keyword
            # arguments depending on the agent type (e.g., stage_name, command,
            # error_output). This is intentional for agent extensibility.
            await self._fix_agent.execute(  # type: ignore[call-arg]
                stage_name=stage.name,
                command=stage.command,
                error_output=error_output,
            )
            logger.info(f"Fix agent invoked for stage: {stage.name}")
            return True
        except Exception as e:
            logger.error(f"Fix agent failed for stage {stage.name}: {e}")
            return False

    async def _run_stage(
        self, stage: ValidationStage
    ) -> AsyncIterator[tuple[ProgressUpdate, StageResult | None]]:
        """Execute a single stage with retry logic.

        Args:
            stage: The validation stage to execute.

        Yields:
            Tuples of (ProgressUpdate, optional StageResult when complete).
        """
        logger.debug(f"Starting stage: {stage.name}")
        stage_start_time = time.time()
        fix_attempts = 0
        last_error = ""
        last_output = ""

        # Check for dry-run mode (T051)
        if self._config.dry_run:
            # Dry-run: report planned action without execution (T052)
            command_str = " ".join(stage.command)
            yield (
                ProgressUpdate(
                    stage=stage.name,
                    status=StageStatus.IN_PROGRESS,
                    message=f"[DRY-RUN] Would run: {command_str}",
                    fix_attempt=0,
                ),
                None,
            )

            # Simulate successful execution in dry-run mode
            duration_ms = int((time.time() - stage_start_time) * 1000)
            yield (
                ProgressUpdate(
                    stage=stage.name,
                    status=StageStatus.PASSED,
                    message=f"[DRY-RUN] Would complete: {command_str}",
                    fix_attempt=0,
                ),
                StageResult(
                    stage_name=stage.name,
                    status=StageStatus.PASSED,
                    fix_attempts=0,
                    error_message=None,
                    output=f"[DRY-RUN] Command not executed: {command_str}",
                    duration_ms=duration_ms,
                ),
            )
            return

        # Initial execution
        yield (
            ProgressUpdate(
                stage=stage.name,
                status=StageStatus.IN_PROGRESS,
                message=f"Running {' '.join(stage.command)}",
                fix_attempt=0,
            ),
            None,
        )

        result = await self._execute_command(stage)
        last_output = result.stdout + result.stderr

        # Check for immediate failures (command not found, timeout)
        if result.command_not_found or result.timed_out:
            duration_ms = int((time.time() - stage_start_time) * 1000)
            logger.error(f"Stage {stage.name} failed: {result.error}")
            yield (
                ProgressUpdate(
                    stage=stage.name,
                    status=StageStatus.FAILED,
                    message=result.error or "Command failed",
                    fix_attempt=0,
                ),
                StageResult(
                    stage_name=stage.name,
                    status=StageStatus.FAILED,
                    fix_attempts=0,
                    error_message=result.error,
                    output=last_output,
                    duration_ms=duration_ms,
                ),
            )
            return

        # If command succeeded
        if result.return_code == 0:
            duration_ms = int((time.time() - stage_start_time) * 1000)
            logger.info(f"Stage {stage.name} passed")
            yield (
                ProgressUpdate(
                    stage=stage.name,
                    status=StageStatus.PASSED,
                    message="Completed successfully",
                    fix_attempt=0,
                ),
                StageResult(
                    stage_name=stage.name,
                    status=StageStatus.PASSED,
                    fix_attempts=0,
                    error_message=None,
                    output=last_output,
                    duration_ms=duration_ms,
                ),
            )
            return

        # Command failed - attempt fixes if stage is fixable
        last_error = result.stderr or result.stdout or "Command failed"

        # Check if stage is fixable (fixable=True AND max_fix_attempts > 0)
        can_fix = stage.is_fixable and self._fix_agent is not None

        while can_fix and fix_attempts < stage.max_fix_attempts:
            # Check for cancellation before fix attempt
            if self._cancel_event.is_set():
                # Yield progress update before breaking
                yield (
                    ProgressUpdate(
                        stage=stage.name,
                        status=StageStatus.CANCELLED,
                        message="Workflow cancelled during fix attempts",
                        fix_attempt=fix_attempts,
                    ),
                    None,
                )
                break

            fix_attempts += 1

            # Yield progress update for fix attempt
            yield (
                ProgressUpdate(
                    stage=stage.name,
                    status=StageStatus.IN_PROGRESS,
                    message=f"Fix attempt #{fix_attempts}",
                    fix_attempt=fix_attempts,
                ),
                None,
            )

            # Invoke fix agent
            await self._invoke_fix_agent(stage, last_error)

            # Retry the command
            result = await self._execute_command(stage)
            last_output = result.stdout + result.stderr

            if result.return_code == 0:
                # Fixed!
                duration_ms = int((time.time() - stage_start_time) * 1000)
                logger.info(f"Stage {stage.name} fixed after {fix_attempts} attempt(s)")
                yield (
                    ProgressUpdate(
                        stage=stage.name,
                        status=StageStatus.FIXED,
                        message=f"Fixed after {fix_attempts} attempt(s)",
                        fix_attempt=fix_attempts,
                    ),
                    StageResult(
                        stage_name=stage.name,
                        status=StageStatus.FIXED,
                        fix_attempts=fix_attempts,
                        error_message=None,
                        output=last_output,
                        duration_ms=duration_ms,
                    ),
                )
                return

            # Update error for next attempt
            last_error = result.stderr or result.stdout or "Command failed"

        # Stage failed after exhausting fix attempts
        duration_ms = int((time.time() - stage_start_time) * 1000)
        error_msg = f"Stage {stage.name} failed after {fix_attempts} fix attempt(s)"
        logger.error(f"{error_msg}: {last_error}")
        yield (
            ProgressUpdate(
                stage=stage.name,
                status=StageStatus.FAILED,
                message=(
                    f"Failed after {fix_attempts} fix attempt(s)"
                    if fix_attempts > 0
                    else "Failed"
                ),
                fix_attempt=fix_attempts,
            ),
            StageResult(
                stage_name=stage.name,
                status=StageStatus.FAILED,
                fix_attempts=fix_attempts,
                error_message=last_error,
                output=last_output,
                duration_ms=duration_ms,
            ),
        )

    async def run(self) -> AsyncIterator[ProgressUpdate]:
        """Execute the validation workflow.

        Runs all configured stages in sequence, yielding progress updates.

        Yields:
            ProgressUpdate events for TUI consumption.

        Note:
            This is an async generator that yields progress updates as the workflow
            executes. Consumers should iterate over it to receive real-time updates.
            Call get_result() after iteration completes to retrieve the final result.
        """
        self._start_time = time.time()
        stage_results: list[StageResult] = []

        for stage in self._stages:
            # Check for cancellation before starting stage
            if self._cancel_event.is_set():
                # Mark remaining stages as cancelled
                stage_results.append(
                    StageResult(
                        stage_name=stage.name,
                        status=StageStatus.CANCELLED,
                        fix_attempts=0,
                        error_message="Workflow cancelled",
                        output="",
                        duration_ms=0,
                    )
                )
                yield ProgressUpdate(
                    stage=stage.name,
                    status=StageStatus.CANCELLED,
                    message="Workflow cancelled",
                )
                continue

            # Run the stage
            async for progress, result in self._run_stage(stage):
                yield progress
                if result is not None:
                    stage_results.append(result)

            # Check stop_on_failure
            if (
                self._config.stop_on_failure
                and stage_results
                and stage_results[-1].status == StageStatus.FAILED
            ):
                # Mark remaining stages as not executed (they won't be in results)
                break

        # Calculate overall success
        success = all(r.passed for r in stage_results)
        total_duration_ms = int((time.time() - self._start_time) * 1000)

        # Build metadata (T053)
        metadata = {}
        if self._config.dry_run:
            metadata["dry_run"] = True

        self._result = ValidationWorkflowResult(
            success=success,
            stage_results=stage_results,
            cancelled=self._cancel_event.is_set(),
            total_duration_ms=total_duration_ms,
            metadata=metadata,
        )

    def cancel(self) -> None:
        """Request workflow cancellation."""
        self._cancel_event.set()

    def get_result(self) -> ValidationWorkflowResult:
        """Get the final workflow result.

        Returns:
            ValidationWorkflowResult with success status and stage breakdown.

        Raises:
            RuntimeError: If called before run() completes.
        """
        if self._result is None:
            raise RuntimeError("Workflow has not completed. Call run() first.")
        return self._result


def create_python_workflow(
    fix_agent: MaverickAgent | None = None,
    config: ValidationWorkflowConfig | None = None,
) -> ValidationWorkflow:
    """Create a ValidationWorkflow with default Python stages.

    Factory function for creating a pre-configured workflow for Python projects
    using DEFAULT_PYTHON_STAGES (format, lint, typecheck, test).

    Args:
        fix_agent: Optional agent for attempting fixes on failed stages.
        config: Optional workflow configuration.

    Returns:
        ValidationWorkflow configured with Python validation stages.

    Example:
        >>> from maverick.workflows.validation import create_python_workflow
        >>> workflow = create_python_workflow()
        >>> async for progress in workflow.run():
        ...     print(f"{progress.stage}: {progress.status}")
    """
    from maverick.models.validation import DEFAULT_PYTHON_STAGES

    return ValidationWorkflow(
        stages=list(DEFAULT_PYTHON_STAGES),
        fix_agent=fix_agent,
        config=config,
    )
