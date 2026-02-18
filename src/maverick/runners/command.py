"""Command runner for safe async subprocess execution.

This module provides the CommandRunner class for executing external commands
with timeout handling, streaming output, and proper error management.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from tenacity import (
    AsyncRetrying,
    RetryError,
    stop_after_attempt,
    wait_exponential,
)

from maverick.exceptions import WorkingDirectoryError
from maverick.runners.models import CommandResult, StreamLine
from maverick.utils.secrets import _COMPILED_SENSITIVE_PATTERNS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

__all__ = ["CommandRunner", "RetryableCommandError"]

# Timeout constants
TERMINATION_GRACE_PERIOD: float = 2.0


class RetryableCommandError(Exception):
    """Exception raised when a command fails with a retryable error.

    This exception is used internally by CommandRunner to signal that a
    command execution failed but should be retried. It wraps the CommandResult
    for access after retry exhaustion.
    """

    def __init__(self, result: CommandResult, message: str = "Command failed") -> None:
        """Initialize the RetryableCommandError.

        Args:
            result: The CommandResult from the failed command execution.
            message: Human-readable error message.
        """
        super().__init__(message)
        self.result = result


class CommandRunner:
    """Execute commands safely with timeout and environment control.

    Provides async command execution with:
    - Timeout handling with graceful termination (SIGTERM + grace period + SIGKILL)
    - Working directory validation
    - Environment variable inheritance and override
    - Duration measurement

    Attributes:
        cwd: Working directory for command execution.
        timeout: Default timeout in seconds (None for no timeout).
        env: Additional environment variables to merge with parent env.

    Example:
        ```python
        runner = CommandRunner(cwd=Path("/project"), timeout=30.0)
        result = await runner.run(["pytest", "tests/"])
        if result.success:
            print(f"Tests passed in {result.duration_ms}ms")
        ```
    """

    def __init__(
        self,
        cwd: Path | None = None,
        timeout: float | None = 120.0,
        env: dict[str, str] | None = None,
    ) -> None:
        """Initialize the CommandRunner.

        Args:
            cwd: Working directory for commands. If None, uses current directory.
            timeout: Default timeout in seconds. Use None for no timeout.
            env: Additional environment variables to merge with os.environ.
        """
        self._cwd = cwd
        self._timeout = timeout
        self._extra_env = env or {}
        # Streaming state
        self._process: asyncio.subprocess.Process | None = None
        self._start_time: float | None = None
        self._stdout_lines: list[str] = []
        self._stderr_lines: list[str] = []

    @property
    def cwd(self) -> Path | None:
        """Working directory for command execution."""
        return self._cwd

    @property
    def timeout(self) -> float | None:
        """Default timeout in seconds."""
        return self._timeout

    def _validate_cwd(self, cwd: Path | None) -> None:
        """Validate working directory exists.

        Args:
            cwd: Directory to validate.

        Raises:
            WorkingDirectoryError: If directory does not exist.
        """
        if cwd is not None and not cwd.is_dir():
            raise WorkingDirectoryError(
                f"Working directory does not exist: {cwd}",
                path=cwd,
            )

    def _build_env(self, extra_env: dict[str, str] | None = None) -> dict[str, str]:
        """Build environment by merging parent env with overrides.

        Args:
            extra_env: Additional variables to add/override.

        Returns:
            Complete environment dictionary.
        """
        env = os.environ.copy()
        env.update(self._extra_env)
        if extra_env:
            env.update(extra_env)
        return env

    def _scrub_secrets(self, text: str) -> str:
        """Scrub sensitive patterns from text.

        Uses the canonical ``SENSITIVE_PATTERNS`` from
        ``maverick.utils.secrets``.

        Args:
            text: Text that may contain secrets.

        Returns:
            Text with secrets replaced by placeholders.
        """
        result = text
        for pattern, replacement in _COMPILED_SENSITIVE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    def is_retryable(self, result: CommandResult) -> bool:
        """Determine if a command failure should be retried.

        Args:
            result: The result of a command execution.

        Returns:
            True if the command should be retried, False otherwise.
        """
        # Retry on timeout
        if result.timed_out:
            return True

        # Retry on connection reset errors
        if "connection reset" in result.stderr.lower():
            return True

        # Retry on rate limit errors
        return "rate limit" in result.stderr.lower()

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        scrub_secrets: bool = False,
    ) -> CommandResult:
        """Execute a command and return the result.

        Args:
            command: Command and arguments as a sequence (no shell expansion).
            cwd: Override working directory for this command.
            timeout: Override timeout. Use 0 or negative for no timeout.
            env: Additional environment variables for this command.
            max_retries: Maximum number of retry attempts (default 0 = no retries).
            retry_delay: Initial delay between retries in seconds (default 1.0).
                Delay doubles on each retry (exponential backoff).
            scrub_secrets: If True, scrub sensitive patterns from stderr.

        Returns:
            CommandResult with returncode, stdout, stderr, duration_ms, timed_out.

        Raises:
            WorkingDirectoryError: If working directory does not exist.
        """
        # Resolve working directory
        effective_cwd = cwd if cwd is not None else self._cwd
        self._validate_cwd(effective_cwd)

        # Resolve timeout
        effective_timeout = timeout if timeout is not None else self._timeout
        if effective_timeout is not None and effective_timeout <= 0:
            effective_timeout = None

        # Build environment
        effective_env = self._build_env(env)

        # Use Tenacity for retry logic with exponential backoff
        # stop_after_attempt(1) = no retries, (2) = 1 retry, etc.
        # So we add 1 to max_retries to get the correct number of attempts
        last_result: CommandResult | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_retries + 1),
                wait=wait_exponential(multiplier=retry_delay, min=retry_delay, max=10),
                reraise=True,
            ):
                with attempt:
                    result = await self._execute_once(
                        command, effective_cwd, effective_timeout, effective_env
                    )

                    # Apply secret scrubbing if enabled
                    if scrub_secrets:
                        result = CommandResult(
                            returncode=result.returncode,
                            stdout=result.stdout,
                            stderr=self._scrub_secrets(result.stderr),
                            duration_ms=result.duration_ms,
                            timed_out=result.timed_out,
                        )

                    last_result = result

                    # If successful, return immediately
                    if result.success:
                        return result

                    # If not retryable, return the result without raising
                    if not self.is_retryable(result):
                        return result

                    # Raise to trigger retry (only for retryable failures)
                    raise RetryableCommandError(result, "Command failed, retrying...")

        except RetryError as e:
            # All retries exhausted, return the last result
            if last_result is not None:
                return last_result
            # This shouldn't happen, but handle gracefully
            raise RuntimeError("Retry exhausted with no result") from e
        except RetryableCommandError:
            # This can happen when max_retries=0 and command fails with retryable error
            # In this case, we should return the last result
            if last_result is not None:
                return last_result
            raise

        # Should not reach here, but satisfy type checker
        assert last_result is not None
        return last_result

    async def _execute_once(
        self,
        command: Sequence[str],
        cwd: Path | None,
        timeout: float | None,
        env: dict[str, str],
    ) -> CommandResult:
        """Execute a command once without retries.

        Args:
            command: Command and arguments as a sequence.
            cwd: Working directory for the command.
            timeout: Timeout in seconds or None for no timeout.
            env: Environment variables for the command.

        Returns:
            CommandResult with returncode, stdout, stderr, duration_ms, timed_out.
        """
        # Start timing
        start_time = time.monotonic()
        timed_out = False
        returncode = 0
        stdout_str = ""
        stderr_str = ""

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                # Wait for completion with timeout
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
                returncode = process.returncode or 0
                stdout_str = stdout_bytes.decode("utf-8", errors="replace")
                stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            except TimeoutError:
                # Graceful termination: SIGTERM first
                timed_out = True
                process.terminate()

                try:
                    # Give grace period for graceful shutdown
                    await asyncio.wait_for(
                        process.wait(), timeout=TERMINATION_GRACE_PERIOD
                    )
                except TimeoutError:
                    # Force kill if still running
                    process.kill()
                    await process.wait()

                returncode = -1
                # Try to get any output that was captured
                if process.stdout:
                    try:
                        partial_stdout = await asyncio.wait_for(
                            process.stdout.read(), timeout=0.1
                        )
                        stdout_str = partial_stdout.decode("utf-8", errors="replace")
                    except (TimeoutError, Exception):
                        pass
                if process.stderr:
                    try:
                        partial_stderr = await asyncio.wait_for(
                            process.stderr.read(), timeout=0.1
                        )
                        stderr_str = partial_stderr.decode("utf-8", errors="replace")
                    except (TimeoutError, Exception):
                        pass

        except FileNotFoundError:
            # Command not found
            returncode = 127
            stderr_str = f"Command not found: {command[0]}"
        except PermissionError:
            # Permission denied
            returncode = 126
            stderr_str = f"Permission denied: {command[0]}"

        # Calculate duration
        duration_ms = int((time.monotonic() - start_time) * 1000)

        return CommandResult(
            returncode=returncode,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    async def stream(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> AsyncIterator[StreamLine]:
        """Stream command output line by line.

        Yields StreamLine objects as output becomes available.
        Call wait() after iteration completes to get final CommandResult.

        Args:
            command: Command and arguments as a sequence (no shell expansion).
            cwd: Override working directory for this command.
            timeout: Override timeout for this command.
            env: Additional environment variables for this command.

        Yields:
            StreamLine objects containing content, stream type, and timestamp.

        Raises:
            WorkingDirectoryError: If working directory does not exist.
        """
        effective_cwd = cwd if cwd is not None else self._cwd
        self._validate_cwd(effective_cwd)
        effective_timeout = timeout if timeout is not None else self._timeout
        effective_env = self._build_env(env)

        self._start_time = time.monotonic()
        self._stdout_lines = []
        self._stderr_lines = []

        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=effective_cwd,
            env=effective_env,
        )

        # Create queue for merging stdout and stderr streams
        queue: asyncio.Queue[StreamLine | None] = asyncio.Queue()
        timed_out = False

        async def read_stream(
            stream: asyncio.StreamReader | None,
            stream_name: Literal["stdout", "stderr"],
        ) -> None:
            """Read lines from a stream and put them in the queue."""
            if stream is None:
                return
            try:
                while True:
                    line_bytes = await stream.readline()
                    if not line_bytes:
                        break
                    content = line_bytes.decode("utf-8", errors="replace").rstrip("\n")

                    # Store lines based on stream type
                    if stream_name == "stdout":
                        self._stdout_lines.append(content)
                    else:
                        self._stderr_lines.append(content)

                    # self._start_time is guaranteed to be set before this point
                    assert self._start_time is not None
                    timestamp_ms = int((time.monotonic() - self._start_time) * 1000)
                    await queue.put(
                        StreamLine(
                            content=content,
                            stream=stream_name,
                            timestamp_ms=timestamp_ms,
                        )
                    )
            except Exception:
                # Silently handle stream errors (process may have terminated)
                pass

        async def monitor_timeout() -> None:
            """Monitor for timeout and terminate process if needed."""
            nonlocal timed_out
            if effective_timeout is None:
                return
            try:
                await asyncio.sleep(effective_timeout)
                # If we reach here, timeout occurred
                timed_out = True
                # self._process is guaranteed to be set before this point
                assert self._process is not None
                self._process.terminate()
                try:
                    await asyncio.wait_for(
                        self._process.wait(), timeout=TERMINATION_GRACE_PERIOD
                    )
                except TimeoutError:
                    self._process.kill()
            except asyncio.CancelledError:
                # Normal completion before timeout
                pass

        # Start concurrent tasks for reading both streams and monitoring timeout
        stdout_task = asyncio.create_task(read_stream(self._process.stdout, "stdout"))
        stderr_task = asyncio.create_task(read_stream(self._process.stderr, "stderr"))
        timeout_task = asyncio.create_task(monitor_timeout())

        try:
            # Yield lines as they arrive from either stream
            while True:
                # Check if both streams are done
                if stdout_task.done() and stderr_task.done():
                    # Drain any remaining items in queue
                    while not queue.empty():
                        try:
                            line = queue.get_nowait()
                            if line is not None:
                                yield line
                        except asyncio.QueueEmpty:
                            break
                    break

                # Wait for next line with a small timeout to check task status
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=0.1)
                    if line is not None:
                        yield line
                except TimeoutError:
                    # Check if process timed out
                    if timed_out:
                        break
                    # Otherwise continue waiting
                    continue

        finally:
            # Cancel timeout monitor if still running
            if not timeout_task.done():
                timeout_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await timeout_task

            # Wait for stream tasks to complete
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

            # Ensure process has terminated
            if self._process.returncode is None:
                await self._process.wait()

    async def wait(self) -> CommandResult:
        """Get final result after streaming completes.

        Returns:
            CommandResult with returncode, stdout, stderr, duration_ms.

        Raises:
            RuntimeError: If no streaming process is active.
        """
        if self._process is None or self._start_time is None:
            raise RuntimeError("No streaming process active. Call stream() first.")

        duration_ms = int((time.monotonic() - self._start_time) * 1000)
        returncode = self._process.returncode or 0

        return CommandResult(
            returncode=returncode,
            stdout="\n".join(self._stdout_lines),
            stderr="\n".join(self._stderr_lines),
            duration_ms=duration_ms,
            timed_out=False,
        )
