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

from maverick.exceptions import WorkingDirectoryError
from maverick.runners.models import CommandResult, StreamLine

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

__all__ = ["CommandRunner"]

# Timeout constants
TERMINATION_GRACE_PERIOD: float = 2.0


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

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Execute a command and return the result.

        Args:
            command: Command and arguments as a sequence (no shell expansion).
            cwd: Override working directory for this command.
            timeout: Override timeout. Use 0 or negative for no timeout.
            env: Additional environment variables for this command.

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
                cwd=effective_cwd,
                env=effective_env,
            )

            try:
                # Wait for completion with timeout
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
                returncode = process.returncode or 0
                stdout_str = stdout_bytes.decode("utf-8", errors="replace")
                stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            except asyncio.TimeoutError:
                # Graceful termination: SIGTERM first
                timed_out = True
                process.terminate()

                try:
                    # Give grace period for graceful shutdown
                    await asyncio.wait_for(
                        process.wait(), timeout=TERMINATION_GRACE_PERIOD
                    )
                except asyncio.TimeoutError:
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
                    except (asyncio.TimeoutError, Exception):
                        pass
                if process.stderr:
                    try:
                        partial_stderr = await asyncio.wait_for(
                            process.stderr.read(), timeout=0.1
                        )
                        stderr_str = partial_stderr.decode("utf-8", errors="replace")
                    except (asyncio.TimeoutError, Exception):
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
                except asyncio.TimeoutError:
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
                except asyncio.TimeoutError:
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
