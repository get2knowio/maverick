"""CLI context and utilities for Maverick.

This module provides context management, exit codes, and utilities for
bridging Click's synchronous interface to async workflows.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import gc
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, TypeVar

from maverick.config import MaverickConfig

__all__ = [
    "ExitCode",
    "CLIContext",
    "async_command",
]


class ExitCode(IntEnum):
    """Standard exit codes for Maverick CLI.

    Follows Unix conventions and FR-012 requirements:
    - 0 for success
    - 1 for failure
    - 2 for partial success
    - 130 for keyboard interrupt (128 + SIGINT=2)
    """

    SUCCESS = 0
    FAILURE = 1
    PARTIAL = 2
    INTERRUPTED = 130


@dataclass(frozen=True, slots=True)
class CLIContext:
    """Type-safe CLI context containing global options and configuration.

    Attributes:
        config: Loaded Maverick configuration.
        config_path: Path to config file (if specified via --config).
        verbosity: Verbosity level (0=default, 1=INFO, 2+=DEBUG).
        quiet: Suppress non-essential output.
    """

    config: MaverickConfig
    config_path: Path | None = None
    verbosity: int = 0
    quiet: bool = False


F = TypeVar("F", bound=Callable[..., Any])


def async_command(f: F) -> F:
    """Decorator to run async Click commands with graceful Ctrl-C handling.

    First Ctrl-C cancels the running async task and allows cleanup to run
    (with a timeout). Second Ctrl-C force-exits immediately.

    Args:
        f: Async function to wrap.

    Returns:
        Wrapped synchronous function suitable for Click commands.

    Example:
        >>> @cli.command()
        >>> @async_command
        >>> async def fly(ctx: click.Context, branch: str) -> None:
        >>>     await workflow.execute()
    """

    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return _run_with_graceful_shutdown(f(*args, **kwargs))

    return wrapper  # type: ignore[return-value]


def _run_with_graceful_shutdown(coro: Any) -> Any:
    """Run an async coroutine with graceful SIGINT handling.

    First SIGINT cancels the main task so ``finally`` blocks and cleanup
    can run (with a 5-second grace period). A second SIGINT during that
    grace period triggers an immediate hard exit.
    """
    loop = asyncio.new_event_loop()
    main_task: asyncio.Task[Any] | None = None
    _force_exit = False

    def _sigint_handler() -> None:
        nonlocal _force_exit
        if _force_exit or main_task is None or main_task.done():
            # Second Ctrl-C or task already finished — force exit now.
            print("\nForce exit.", file=sys.stderr, flush=True)  # noqa: T201
            loop.stop()
            raise SystemExit(ExitCode.INTERRUPTED)
        # First Ctrl-C — cancel the task so finally blocks can run.
        _force_exit = True
        print(  # noqa: T201
            "\nInterrupted — shutting down (press Ctrl-C again to force)...",
            file=sys.stderr,
            flush=True,
        )
        main_task.cancel()

    try:
        main_task = loop.create_task(coro)
        # Install SIGINT handler only on platforms that support it (Unix).
        if sys.platform != "win32":
            loop.add_signal_handler(signal.SIGINT, _sigint_handler)
        else:
            # On Windows, fall back to default KeyboardInterrupt behavior.
            pass
        return loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        raise SystemExit(ExitCode.INTERRUPTED) from None
    except KeyboardInterrupt:
        raise SystemExit(ExitCode.INTERRUPTED) from None
    finally:
        # Give pending cleanup tasks a short grace period.
        _shutdown_loop(loop, timeout=5.0)


def _shutdown_loop(loop: asyncio.AbstractEventLoop, timeout: float = 5.0) -> None:
    """Cancel remaining tasks and close the event loop with a timeout."""
    try:
        pending = asyncio.all_tasks(loop)
        pending = {t for t in pending if not t.done()}
        if pending:
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.wait(pending, timeout=timeout))
    except Exception:
        pass
    finally:
        # Suppress noisy ACP library errors during async generator cleanup.
        # The ACP spawn_stdio_transport generator logs ERROR-level tracebacks
        # ("aclose(): asynchronous generator is already running") when the
        # event loop tears down connections during shutdown.
        import logging as _logging

        _root = _logging.getLogger()
        _prev = _root.level
        _root.setLevel(_logging.CRITICAL)
        try:
            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            _root.setLevel(_prev)
        # Force GC before closing the loop so subprocess transports
        # are finalized while the loop is still open (prevents
        # "Event loop is closed" RuntimeError in __del__).
        gc.collect()
        loop.close()
        # Suppress the "Event loop is closed" RuntimeError that CPython
        # raises when subprocess transport __del__ fires at interpreter
        # shutdown after the loop is already closed.
        _install_loop_closed_suppressor()


_loop_closed_suppressor_installed = False


def _install_loop_closed_suppressor() -> None:
    """Suppress 'Event loop is closed' RuntimeError from subprocess __del__.

    CPython's asyncio subprocess transport calls ``loop.call_soon`` in its
    ``__del__``, which raises RuntimeError if the loop is already closed.
    This is a known CPython issue with no upstream fix in 3.12.  We install
    a custom ``sys.unraisablehook`` that silences only this specific error,
    forwarding everything else to the original hook.
    """
    global _loop_closed_suppressor_installed  # noqa: PLW0603
    if _loop_closed_suppressor_installed:
        return
    _loop_closed_suppressor_installed = True

    _orig_hook = sys.unraisablehook

    def _hook(unraisable: sys.UnraisableHookArgs) -> None:
        if isinstance(unraisable.exc_value, RuntimeError) and "Event loop is closed" in str(
            unraisable.exc_value
        ):
            return
        _orig_hook(unraisable)

    sys.unraisablehook = _hook
