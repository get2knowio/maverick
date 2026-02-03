"""Unit tests for _has_source_files helper in validate_step handler.

Tests verify that the source-file pre-check correctly identifies
when validation tools have no files to operate on, allowing stages
to be skipped rather than failing with exit codes like mypy's exit 2
or pytest's exit 5.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.serialization.executor.handlers.validate_step import (
    _has_source_files,
)


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    """Create an empty directory."""
    d = tmp_path / "empty"
    d.mkdir()
    return d


@pytest.fixture
def py_dir(tmp_path: Path) -> Path:
    """Create a directory with Python files."""
    d = tmp_path / "project"
    d.mkdir()
    (d / "main.py").write_text("print('hello')")
    sub = d / "pkg"
    sub.mkdir()
    (sub / "__init__.py").write_text("")
    return d


class TestHasSourceFiles:
    """Tests for _has_source_files helper."""

    def test_returns_true_for_unknown_tool(self, empty_dir: Path) -> None:
        """Unknown tools should not be skipped (assume files exist)."""
        assert _has_source_files(("unknown_tool", "--check"), empty_dir) is True

    def test_returns_true_for_empty_command(self, empty_dir: Path) -> None:
        """Empty command tuple should not be skipped."""
        assert _has_source_files((), empty_dir) is True

    def test_returns_false_for_mypy_with_no_py_files(self, empty_dir: Path) -> None:
        """mypy should be skipped when no .py files exist."""
        assert _has_source_files(("mypy", "."), empty_dir) is False

    def test_returns_true_for_mypy_with_py_files(self, py_dir: Path) -> None:
        """mypy should run when .py files exist."""
        assert _has_source_files(("mypy", "."), py_dir) is True

    def test_returns_false_for_pytest_with_no_py_files(self, empty_dir: Path) -> None:
        """pytest should be skipped when no .py files exist."""
        assert _has_source_files(("pytest",), empty_dir) is False

    def test_returns_true_for_ruff_with_py_files(self, py_dir: Path) -> None:
        """ruff should run when .py files exist."""
        assert _has_source_files(("ruff", "check", "."), py_dir) is True

    def test_returns_false_for_ruff_with_no_py_files(self, empty_dir: Path) -> None:
        """ruff should be skipped when no .py files exist."""
        assert _has_source_files(("ruff", "check"), empty_dir) is False

    def test_returns_false_for_eslint_with_no_js_files(self, empty_dir: Path) -> None:
        """eslint should be skipped when no .js files exist."""
        assert _has_source_files(("eslint", "."), empty_dir) is False

    def test_returns_false_for_tsc_with_no_ts_files(self, py_dir: Path) -> None:
        """tsc should be skipped in a Python-only project."""
        assert _has_source_files(("tsc",), py_dir) is False

    def test_finds_nested_py_files(self, py_dir: Path) -> None:
        """Should find .py files in subdirectories."""
        # py_dir has pkg/__init__.py — verify glob finds nested files
        assert _has_source_files(("pytest",), py_dir) is True
