"""Output parsers for extracting structured errors from tool output."""

from __future__ import annotations

from maverick.runners.parsers.base import OutputParser
from maverick.runners.parsers.eslint import ESLintJSONParser
from maverick.runners.parsers.python import PythonTracebackParser
from maverick.runners.parsers.rust import RustCompilerParser

__all__ = [
    "OutputParser",
    "PythonTracebackParser",
    "RustCompilerParser",
    "ESLintJSONParser",
    "get_parser",
    "get_parsers",
]

_PARSERS: list[OutputParser] = [
    PythonTracebackParser(),
    RustCompilerParser(),
    ESLintJSONParser(),
]


def get_parsers(output: str) -> list[OutputParser]:
    """Get all parsers that can handle the given output."""
    matching_parsers = []
    for parser in _PARSERS:
        if parser.can_parse(output):
            matching_parsers.append(parser)
    return matching_parsers


def get_parser(output: str) -> OutputParser | None:
    """Get the first parser that can handle the given output."""
    parsers = get_parsers(output)
    return parsers[0] if parsers else None
