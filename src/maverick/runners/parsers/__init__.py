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
]

_PARSERS: list[OutputParser] = [
    PythonTracebackParser(),
    RustCompilerParser(),
    ESLintJSONParser(),
]


def get_parser(output: str) -> OutputParser | None:
    """Get a parser that can handle the given output."""
    for parser in _PARSERS:
        if parser.can_parse(output):
            return parser
    return None
