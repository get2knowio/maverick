"""Tests for Python traceback parser."""

from __future__ import annotations

from maverick.runners.parsers.python import PythonTracebackParser


class TestPythonTracebackParser:
    def test_can_parse_traceback(self):
        output = """Traceback (most recent call last):
  File "test.py", line 10, in main
    raise ValueError("test")
ValueError: test"""
        parser = PythonTracebackParser()
        assert parser.can_parse(output) is True

    def test_parse_extracts_error(self):
        output = """Traceback (most recent call last):
  File "test.py", line 10, in main
    raise ValueError("test error")
ValueError: test error"""
        parser = PythonTracebackParser()
        errors = parser.parse(output)

        assert len(errors) >= 1
        assert errors[0].file == "test.py"
        assert errors[0].line == 10
        assert "ValueError" in errors[0].message
