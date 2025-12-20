"""Python traceback parser."""

from __future__ import annotations

import re

from maverick.runners.models import ParsedError

__all__ = ["PythonTracebackParser"]


class PythonTracebackParser:
    """Parse Python traceback and pytest output for errors."""

    _traceback_pattern = re.compile(r'File "([^"]+)", line (\d+)(?:, in (\w+))?')
    _error_pattern = re.compile(r"^(\w+Error|\w+Exception): (.+)$", re.MULTILINE)

    def can_parse(self, output: str) -> bool:
        """Check if output contains Python traceback."""
        return "Traceback (most recent call last)" in output or "Error:" in output

    def parse(self, output: str) -> list[ParsedError]:
        """Extract file, line, message from Python tracebacks."""
        errors: list[ParsedError] = []

        # Find traceback locations
        for match in self._traceback_pattern.finditer(output):
            file_path = match.group(1)
            line_num = int(match.group(2))

            # Look for the error message
            error_match = self._error_pattern.search(output[match.end() :])
            if error_match:
                message = f"{error_match.group(1)}: {error_match.group(2)}"
            else:
                message = "Python error"

            errors.append(
                ParsedError(
                    file=file_path,
                    line=line_num,
                    message=message,
                    severity="error",
                )
            )

        return errors
