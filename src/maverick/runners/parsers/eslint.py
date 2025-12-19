"""ESLint JSON output parser."""

from __future__ import annotations

import json

from maverick.runners.models import ParsedError

__all__ = ["ESLintJSONParser"]


class ESLintJSONParser:
    """Parse ESLint JSON format output."""

    def can_parse(self, output: str) -> bool:
        """Check if output is ESLint JSON format."""
        try:
            data = json.loads(output.strip())
            return isinstance(data, list) and all(
                "filePath" in item for item in data if isinstance(item, dict)
            )
        except (json.JSONDecodeError, TypeError):
            return False

    def parse(self, output: str) -> list[ParsedError]:
        """Extract errors from ESLint JSON output."""
        errors: list[ParsedError] = []

        try:
            data = json.loads(output.strip())
            for file_result in data:
                file_path = file_result.get("filePath", "")
                for msg in file_result.get("messages", []):
                    errors.append(
                        ParsedError(
                            file=file_path,
                            line=msg.get("line", 1),
                            column=msg.get("column"),
                            message=msg.get("message", "Unknown error"),
                            severity="error"
                            if msg.get("severity", 2) == 2
                            else "warning",
                            code=msg.get("ruleId"),
                        )
                    )
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        return errors
