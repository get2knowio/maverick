"""Unit tests for the spec-compliance grep checks.

Exercises :mod:`maverick.workflows.fly_beads._spec_check` directly,
without the action/Burr wrapper. The action's behaviour is covered by
``test_burr_graph.py``'s happy-path test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from maverick.workflows.fly_beads._spec_check import (
    RUST_CHECKS,
    SpecCheckResult,
    _filter_source_files,
    _is_test_context,
    run_spec_check,
)


def _init_git_repo(path: Path) -> None:
    """Initialise a git repo + commit a baseline so ``git diff HEAD`` works."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    # Empty commit so HEAD exists.
    (path / "baseline.txt").write_text("baseline\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=path, check=True)


class TestFilterSourceFiles:
    def test_rust_keeps_rs_drops_tests(self) -> None:
        files = [
            "src/foo.rs",
            "tests/test_foo.rs",
            "src/foo_test.rs",
            "src/foo_tests.rs",
            "src/sub/tests/helper.rs",
            "README.md",
        ]
        assert _filter_source_files(files, project_type="rust") == ["src/foo.rs"]

    def test_python_keeps_py_only(self) -> None:
        files = ["src/foo.py", "src/foo.rs", "tests/test_foo.py"]
        assert _filter_source_files(files, project_type="python") == ["src/foo.py"]

    def test_unknown_project_type_keeps_nothing(self) -> None:
        assert _filter_source_files(["src/foo.go"], project_type="go") == []


class TestIsTestContext:
    @pytest.mark.parametrize(
        "line",
        [
            "// this is a comment",
            "    // commented unwrap()",
            "#[test]",
            "    #[cfg(test)]",
            "assert!(x.unwrap() > 0);",
            "assert_eq!(a.unwrap(), b);",
        ],
    )
    def test_classifies_as_test(self, line: str) -> None:
        assert _is_test_context(line) is True

    @pytest.mark.parametrize(
        "line",
        [
            "let x = foo.unwrap();",
            '    return result.expect("oops");',
            'tokio::process::Command::new("ls")',
        ],
    )
    def test_runtime_code_is_not_test(self, line: str) -> None:
        assert _is_test_context(line) is False


class TestRunSpecCheck:
    def test_no_cwd_returns_skipped_pass(self) -> None:
        result = run_spec_check(cwd="", project_type="rust")
        assert isinstance(result, SpecCheckResult)
        assert result.passed is True
        assert "skipped" in result.details

    def test_no_git_repo_returns_no_changes_pass(self, tmp_path: Path) -> None:
        result = run_spec_check(cwd=str(tmp_path), project_type="rust")
        assert result.passed is True
        assert result.findings == ()

    def test_non_rust_project_type_returns_noop(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / "foo.go").write_text("package main\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        result = run_spec_check(cwd=str(tmp_path), project_type="go")
        assert result.passed is True
        assert "no checks for" in result.details

    def test_clean_rust_file_passes(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.rs").write_text(
            "pub fn ok() -> Result<i32, Box<dyn std::error::Error>> {\n    Ok(42)\n}\n"
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        result = run_spec_check(cwd=str(tmp_path), project_type="rust")
        assert result.passed is True
        assert result.findings == ()

    def test_unwrap_in_runtime_code_is_critical(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.rs").write_text(
            "pub fn bad() -> i32 {\n    let x: Result<i32, ()> = Ok(1);\n    x.unwrap()\n}\n"
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        result = run_spec_check(cwd=str(tmp_path), project_type="rust")
        assert result.passed is False
        assert any("unwrap" in f for f in result.findings)
        assert "critical" in result.details

    def test_test_file_findings_are_ignored(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo_test.rs").write_text("fn t() { let x: Result<i32,()> = Ok(1); x.unwrap(); }\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        result = run_spec_check(cwd=str(tmp_path), project_type="rust")
        assert result.passed is True
        assert result.findings == ()

    def test_assert_lines_are_ignored(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        # Source file (not a test file) but the unwrap is inside an
        # assert!() invocation — the heuristic skips it.
        (src / "foo.rs").write_text("fn check() { assert!(some_result().unwrap()); }\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        result = run_spec_check(cwd=str(tmp_path), project_type="rust")
        assert result.passed is True


def test_rust_checks_constant_shape() -> None:
    """RUST_CHECKS must stay shaped as ``(pattern, description, severity)``."""
    for pattern, description, severity in RUST_CHECKS:
        assert isinstance(pattern, str) and pattern
        assert isinstance(description, str) and description
        assert severity in {"critical", "major", "minor"}
