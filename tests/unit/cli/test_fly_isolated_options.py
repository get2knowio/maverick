"""Unit tests for `maverick fly`'s `--isolated`/`--no-isolated` resolution
and preconditions (057-isolated-bead-workspaces, US3, T062).

Contract: specs/057-isolated-bead-workspaces/contracts/fly-isolated-mode.md
("Resolution order" and "Preconditions" sections, contract F9, FR-030,
FR-037).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli

_PATCH_EXECUTE = "maverick.cli.commands.fly._group.execute_python_workflow"


def _init_colocated(cwd: Path) -> None:
    (cwd / ".jj").mkdir(exist_ok=True)


@pytest.fixture(autouse=True)
def _mock_bd_ready():
    """Skip the bd-on-PATH + .beads-initialized preflight (git/gh/bd/jj
    all resolve) — these tests are about --isolated's own
    resolution/preconditions, not the general preflight."""
    with (
        patch("shutil.which", return_value="/usr/bin/tool"),
        patch("maverick.beads.client.BeadClient.is_initialized", return_value=True),
    ):
        yield


class TestResolutionOrder:
    """--isolated/--no-isolated > workspace.enabled > false (FR-030)."""

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_defaults_to_false_with_no_flag_and_no_config(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / "maverick.yaml").write_text("github:\n  owner: test-org\n")

        result = cli_runner.invoke(cli, ["fly"])

        assert result.exit_code == 0, result.output
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["isolated"] is False

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_workspace_enabled_config_turns_it_on(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        _init_colocated(temp_dir)
        (temp_dir / "maverick.yaml").write_text("workspace:\n  enabled: true\n")

        result = cli_runner.invoke(cli, ["fly"])

        assert result.exit_code == 0, result.output
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["isolated"] is True

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_isolated_flag_turns_it_on_with_no_config(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        _init_colocated(temp_dir)
        (temp_dir / "maverick.yaml").write_text("github:\n  owner: test-org\n")

        result = cli_runner.invoke(cli, ["fly", "--isolated"])

        assert result.exit_code == 0, result.output
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["isolated"] is True

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_no_isolated_flag_overrides_enabled_config(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The explicit flag always wins over config, in both directions."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / "maverick.yaml").write_text("workspace:\n  enabled: true\n")

        result = cli_runner.invoke(cli, ["fly", "--no-isolated"])

        assert result.exit_code == 0, result.output
        run_config = mock_execute.call_args[0][1]
        assert run_config.inputs["isolated"] is False


class TestPreconditions:
    """Preconditions refuse with an actionable message and no silent
    fallback (contract F9, FR-037) — checked before any bead is selected."""

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_missing_jj_directory_refuses(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        # deliberately no .jj/ directory

        result = cli_runner.invoke(cli, ["fly", "--isolated"])

        assert result.exit_code != 0
        assert "maverick init" in result.output
        mock_execute.assert_not_called()  # no silent fallback to non-isolated

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_missing_jj_binary_refuses(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        _init_colocated(temp_dir)
        (temp_dir / "maverick.yaml").write_text("github:\n  owner: test-org\n")

        def _which_no_jj(name: str) -> str | None:
            return None if name == "jj" else "/usr/bin/tool"

        with patch("shutil.which", side_effect=_which_no_jj):
            result = cli_runner.invoke(cli, ["fly", "--isolated"])

        assert result.exit_code != 0
        assert "jj" in result.output.lower()
        mock_execute.assert_not_called()

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_preconditions_are_skipped_when_not_isolated(
        self,
        mock_execute: AsyncMock,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without --isolated (and no workspace.enabled), the .jj/ and jj
        binary checks never run — every observable behavior matches today
        (FR-035)."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / "maverick.yaml").write_text("github:\n  owner: test-org\n")
        # no .jj/, and shutil.which("jj") would fail if checked

        result = cli_runner.invoke(cli, ["fly"])

        assert result.exit_code == 0, result.output
        mock_execute.assert_called_once()
