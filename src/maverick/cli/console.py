"""Shared Rich Console instances for Maverick CLI output.

Provides auto-TTY-detecting consoles for stdout and stderr.
Rich Console handles this automatically: styled output in terminals,
plain text when piped.
"""

from __future__ import annotations

from rich.console import Console

__all__ = ["console", "err_console"]

console = Console()
err_console = Console(stderr=True)
