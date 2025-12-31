"""CLI context and utilities for Maverick.

This module provides context management, exit codes, and utilities for
bridging Click's synchronous interface to async workflows.
"""

from __future__ import annotations

import asyncio
import functools
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, TypeVar

from maverick.cli.output import OutputFormat
from maverick.config import MaverickConfig

__all__ = [
    "ExitCode",
    "CLIContext",
    "async_command",
    "ReviewCommandInputs",
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
        no_tui: Disable TUI mode regardless of TTY.
    """

    config: MaverickConfig
    config_path: Path | None = None
    verbosity: int = 0
    quiet: bool = False
    no_tui: bool = False

    @property
    def use_tui(self) -> bool:
        """Whether TUI should be used (considers TTY detection).

        Returns:
            True if TUI should be enabled, False otherwise.
        """
        if self.no_tui:
            return False
        if self.quiet:
            return False
        return sys.stdin.isatty() and sys.stdout.isatty()


F = TypeVar("F", bound=Callable[..., Any])


def async_command(f: F) -> F:
    """Decorator to run async Click commands with asyncio.run().

    This bridges Click's synchronous interface to async workflow functions.

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
        return asyncio.run(f(*args, **kwargs))

    return wrapper  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class ReviewCommandInputs:
    """Inputs for review command execution.

    Attributes:
        pr_number: Pull request number to review.
        fix: Automatically apply suggested fixes.
        output_format: Output format (tui, json, markdown).
    """

    pr_number: int
    fix: bool = False
    output_format: OutputFormat = OutputFormat.TUI
