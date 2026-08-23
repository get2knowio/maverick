"""CLI tests for ``maverick delta validate`` — invoked through the root
``cli`` group per house convention (contracts/cli-delta.md)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from maverick.main import cli

_SPEC_MD = """\
# Feature Specification: Sample

### Functional Requirements

- **FR-001**: The first requirement.
- **FR-002**: The gate MUST evaluate the frontier before curating.

### Key Entities
"""

_TASKS_MD = "## Phase 1: Setup\n\n- [ ] T001 Initialize project\n"


@pytest.fixture
def feature_env(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(temp_dir)
    feature_dir = temp_dir / "specs" / "052-conditional-landing"
    (feature_dir / "deltas").mkdir(parents=True)
    (feature_dir / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    (feature_dir / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    return feature_dir


def _write_delta(feature_dir: Path, name: str, text: str) -> None:
    (feature_dir / "deltas" / name).write_text(text, encoding="utf-8")


_VALID_DELTA = (
    "# Delta: reword\n\n**Target**: 052-conditional-landing\n\n"
    "## MODIFIED FR-002\n\n### Before\n\n"
    "- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
    "### After\n\n- **FR-002**: The gate MUST evaluate the assumption frontier "
    "before any curation step runs, on all three curation paths.\n"
)

_MULTI_PROBLEM_DELTA = (
    "# Delta: bad\n\n**Target**: 052-conditional-landing\n\n"
    "## MODIFIED FR-999\n\n### Before\n\n- **FR-999**: Nope.\n\n"
    "### After\n\n- **FR-999**: Still nope.\n\n"
    "## TASKS\n\n- WITHDRAWN: T404\n"
)


class TestValidDelta:
    def test_valid_delta_exits_zero(self, cli_runner: CliRunner, feature_env: Path) -> None:
        _write_delta(feature_env, "001-reword.md", _VALID_DELTA)
        result = cli_runner.invoke(cli, ["delta", "validate", "052/001-reword"])
        assert result.exit_code == 0, result.output
        assert "052-conditional-landing/001-reword" in result.output
        assert "1 modified" in result.output


class TestMultiProblemDelta:
    def test_reports_every_problem_and_exits_nonzero(
        self, cli_runner: CliRunner, feature_env: Path
    ) -> None:
        _write_delta(feature_env, "002-bad.md", _MULTI_PROBLEM_DELTA)
        result = cli_runner.invoke(cli, ["delta", "validate", "052/002-bad"])
        assert result.exit_code == 1
        assert "dangling-requirement" not in result.output  # codes aren't in human output...
        assert "FR-999" in result.output
        assert "T404" in result.output


class TestFeatureResolution:
    def test_exact_directory_name(self, cli_runner: CliRunner, feature_env: Path) -> None:
        _write_delta(feature_env, "001-reword.md", _VALID_DELTA)
        result = cli_runner.invoke(
            cli, ["delta", "validate", "052-conditional-landing/001-reword"]
        )
        assert result.exit_code == 0, result.output

    def test_nnn_prefix(self, cli_runner: CliRunner, feature_env: Path) -> None:
        _write_delta(feature_env, "001-reword.md", _VALID_DELTA)
        result = cli_runner.invoke(cli, ["delta", "validate", "052/001-reword"])
        assert result.exit_code == 0, result.output

    def test_exact_name_suffix(self, cli_runner: CliRunner, feature_env: Path) -> None:
        _write_delta(feature_env, "001-reword.md", _VALID_DELTA)
        result = cli_runner.invoke(cli, ["delta", "validate", "conditional-landing/001-reword"])
        assert result.exit_code == 0, result.output

    def test_unresolvable_feature_fails(self, cli_runner: CliRunner, feature_env: Path) -> None:
        result = cli_runner.invoke(cli, ["delta", "validate", "999/001-nope"])
        assert result.exit_code == 1

    def test_unresolvable_delta_slug_fails(self, cli_runner: CliRunner, feature_env: Path) -> None:
        result = cli_runner.invoke(cli, ["delta", "validate", "052/999-nope"])
        assert result.exit_code == 1


class TestDirectPath:
    def test_direct_file_path(self, cli_runner: CliRunner, feature_env: Path) -> None:
        _write_delta(feature_env, "001-reword.md", _VALID_DELTA)
        path = feature_env / "deltas" / "001-reword.md"
        result = cli_runner.invoke(cli, ["delta", "validate", str(path)])
        assert result.exit_code == 0, result.output
