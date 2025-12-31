"""Base protocol for output parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from maverick.runners.models import ParsedError

__all__ = ["OutputParser"]


class OutputParser(Protocol):
    """Protocol for parsing tool output into structured errors."""

    def can_parse(self, output: str) -> bool:
        """Check if this parser can handle the output."""
        ...

    def parse(self, output: str) -> list[ParsedError]:
        """Parse output and return list of errors."""
        ...
