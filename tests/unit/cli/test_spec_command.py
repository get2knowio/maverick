"""CLI contract tests for ``maverick spec`` (argument/option parsing,
preflight failures) per specs/050-headless-spec-chain/contracts/cli-spec.md.

Full happy-path chain execution is covered at the workflow level by
tests/integration/spec_chain/test_full_chain.py — these tests only
exercise the CLI's own argument parsing and preflight gate, without ever
constructing an airframe runtime.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from maverick.cli.context import ExitCode
from maverick.main import cli


class TestSpecRegistered:
    def test_spec_in_cli_help(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["--help"])
        assert "spec" in result.output

    def test_spec_help_shows_from_prd(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["spec", "--help"])
        assert result.exit_code == 0
        assert "--from-prd" in result.output


class TestArgumentParsing:
    def test_missing_feature_argument_is_usage_error(
        self, cli_runner: CliRunner, temp_dir: Path
    ) -> None:
        result = cli_runner.invoke(cli, ["spec", "--from-prd", str(temp_dir / "prd.md")])
        assert result.exit_code == ExitCode.PARTIAL

    def test_missing_from_prd_option_is_usage_error(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--from-prd is optional at the Click level (resume doesn't need
        it) but still required when starting a fresh chain — enforced in
        the command body, once past preflight and resume discovery."""
        import os

        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".specify").mkdir()
        (temp_dir / ".specify" / "init-options.json").write_text(
            '{"speckit_version": "0.14.0"}', encoding="utf-8"
        )
        monkeypatch.setattr("maverick.cli.commands.spec.verify_bd_ready", lambda cwd=None: None)

        result = cli_runner.invoke(cli, ["spec", "my-feature"])
        assert result.exit_code == ExitCode.PARTIAL

    def test_nonexistent_prd_file_is_usage_error(
        self, cli_runner: CliRunner, temp_dir: Path
    ) -> None:
        result = cli_runner.invoke(
            cli, ["spec", "my-feature", "--from-prd", str(temp_dir / "does-not-exist.md")]
        )
        assert result.exit_code == ExitCode.PARTIAL


class TestPreflight:
    """Preflight checks run before any workspace is created (FR-001/FR-018)."""

    def test_missing_bd_exits_nonzero_before_workspace_creation(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        prd = temp_dir / "prd.md"
        prd.write_text("# PRD\n\nSome content.\n", encoding="utf-8")

        with patch("shutil.which", return_value=None):
            result = cli_runner.invoke(cli, ["spec", "my-feature", "--from-prd", str(prd)])

        assert result.exit_code != ExitCode.SUCCESS
        assert not (temp_dir / ".maverick" / "runs").exists()

    def test_missing_speckit_exits_partial_with_guidance(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        prd = temp_dir / "prd.md"
        prd.write_text("# PRD\n\nSome content.\n", encoding="utf-8")
        # No .specify/ directory anywhere under temp_dir.

        monkeypatch.setattr("maverick.cli.commands.spec.verify_bd_ready", lambda cwd=None: None)

        result = cli_runner.invoke(cli, ["spec", "my-feature", "--from-prd", str(prd)])

        assert result.exit_code == ExitCode.PARTIAL
        assert not (temp_dir / ".maverick" / "runs").exists()

    def test_empty_prd_exits_partial(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".specify").mkdir()
        (temp_dir / ".specify" / "init-options.json").write_text(
            '{"speckit_version": "0.14.0"}', encoding="utf-8"
        )
        prd = temp_dir / "prd.md"
        prd.write_text("", encoding="utf-8")

        monkeypatch.setattr("maverick.cli.commands.spec.verify_bd_ready", lambda cwd=None: None)

        result = cli_runner.invoke(cli, ["spec", "my-feature", "--from-prd", str(prd)])

        assert result.exit_code == ExitCode.PARTIAL

    def test_existing_spec_dir_for_feature_is_a_collision(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".specify").mkdir()
        (temp_dir / ".specify" / "init-options.json").write_text(
            '{"speckit_version": "0.14.0"}', encoding="utf-8"
        )
        (temp_dir / "specs" / "001-my-feature").mkdir(parents=True)
        prd = temp_dir / "prd.md"
        prd.write_text("# PRD\n\ncontent\n", encoding="utf-8")

        monkeypatch.setattr("maverick.cli.commands.spec.verify_bd_ready", lambda cwd=None: None)

        result = cli_runner.invoke(cli, ["spec", "my-feature", "--from-prd", str(prd)])

        assert result.exit_code == ExitCode.PARTIAL

    def test_all_preflight_checks_pass_reaches_workflow_dispatch(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Once preflight passes, the command proceeds to dispatch the
        workflow (verified by patching execute_python_workflow itself, so
        this test never touches jj/airframe)."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".specify").mkdir()
        (temp_dir / ".specify" / "init-options.json").write_text(
            '{"speckit_version": "0.14.0"}', encoding="utf-8"
        )
        prd = temp_dir / "prd.md"
        prd.write_text("# PRD\n\ncontent\n", encoding="utf-8")

        monkeypatch.setattr("maverick.cli.commands.spec.verify_bd_ready", lambda cwd=None: None)

        called: dict[str, object] = {}

        async def _fake_execute(ctx: object, run_config: object) -> None:
            called["run_config"] = run_config

        async def _fake_load_chain_state(run_id: str, base: Path) -> None:
            called["run_id"] = run_id
            return None

        monkeypatch.setattr(
            "maverick.cli.workflow_executor.execute_python_workflow", _fake_execute
        )
        monkeypatch.setattr(
            "maverick.workflows.spec_chain.state.load_chain_state", _fake_load_chain_state
        )

        cli_runner.invoke(cli, ["spec", "my-feature", "--from-prd", str(prd)])

        assert "run_config" in called
