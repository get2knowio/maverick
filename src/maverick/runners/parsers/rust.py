"""Rust compiler error parser."""

from __future__ import annotations

import re

from maverick.runners.models import ParsedError

__all__ = ["RustCompilerParser"]


class RustCompilerParser:
    """Parse rustc and cargo error output."""

    _error_pattern = re.compile(
        r"^error(?:\[E(\d+)\])?: (.+)\n\s+--> ([^:]+):(\d+):(\d+)", re.MULTILINE
    )
    _warning_pattern = re.compile(
        r"^warning(?:\[E(\d+)\])?: (.+)\n\s+--> ([^:]+):(\d+):(\d+)", re.MULTILINE
    )

    def can_parse(self, output: str) -> bool:
        """Check if output contains Rust compiler messages."""
        return "error[E" in output or "error:" in output or "warning:" in output

    def parse(self, output: str) -> list[ParsedError]:
        """Extract structured errors from rustc output."""
        errors: list[ParsedError] = []

        for match in self._error_pattern.finditer(output):
            errors.append(
                ParsedError(
                    file=match.group(3),
                    line=int(match.group(4)),
                    column=int(match.group(5)),
                    message=match.group(2),
                    severity="error",
                    code=f"E{match.group(1)}" if match.group(1) else None,
                )
            )

        for match in self._warning_pattern.finditer(output):
            errors.append(
                ParsedError(
                    file=match.group(3),
                    line=int(match.group(4)),
                    column=int(match.group(5)),
                    message=match.group(2),
                    severity="warning",
                    code=f"E{match.group(1)}" if match.group(1) else None,
                )
            )

        return errors
