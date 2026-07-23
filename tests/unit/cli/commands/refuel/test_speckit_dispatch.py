"""Tests for ``maverick refuel`` Spec Kit mode dispatch and flags.

Covers the CLI dispatch matrix in
``contracts/cli-refuel-speckit.md``: explicit ``--speckit``,
auto-detection, and the E01-E07 error catalog.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.main import cli

_PATCH_EXECUTE = "maverick.cli.workflow_executor.execute_python_workflow"

_TASKS_MD = """\
## Phase 1: Setup

- [ ] T001 Initialize project
"""
_SPEC_MD = "# Feature Specification: Sample\n"


@pytest.fixture(autouse=True)
def _mock_bd_available():
    with (
        patch("shutil.which", return_value="/usr/bin/bd"),
        patch("maverick.beads.client.BeadClient.is_initialized", return_value=True),
    ):
        yield


def _make_speckit_dir(base: Path, name: str = "048-sample-feature") -> Path:
    feature_dir = base / "specs" / name
    feature_dir.mkdir(parents=True)
    (feature_dir / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    (feature_dir / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    return feature_dir


def _make_classic_dir(base: Path, name: str = "my-feature") -> Path:
    plan_dir = base / ".maverick" / "plans" / name
    plan_dir.mkdir(parents=True)
    (plan_dir / "flight-plan.md").write_text(
        "---\nname: my-feature\n---\n\n## Objective\n\nTest.\n", encoding="utf-8"
    )
    return plan_dir / "flight-plan.md"


class TestExplicitSpeckitFlag:
    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_speckit_flag_forces_ingestion_mode(
        self, mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        feature_dir = _make_speckit_dir(refuel_env)

        result = cli_runner.invoke(cli, ["refuel", "048", "--speckit"])

        assert result.exit_code == 0, result.output
        assert "Using Spec Kit ingestion" in result.output
        mock_execute.assert_called_once()
        run_config = mock_execute.call_args[0][1]
        from maverick.workflows.refuel_speckit import SpeckitRefuelWorkflow

        assert run_config.workflow_class is SpeckitRefuelWorkflow
        assert run_config.inputs["feature_dir"] == str(feature_dir)

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_speckit_flag_with_unresolvable_name_is_e02(
        self, _mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        result = cli_runner.invoke(cli, ["refuel", "nonexistent", "--speckit"])

        assert result.exit_code == 1
        assert "does not resolve" in result.output
        assert "Traceback" not in result.output

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_list_steps_with_speckit_lists_speckit_steps(
        self, _mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        _make_speckit_dir(refuel_env)

        result = cli_runner.invoke(cli, ["refuel", "048", "--speckit", "--list-steps"])

        assert result.exit_code == 0, result.output
        assert "Resolve Feature" in result.output
        assert "Check Template" in result.output
        assert "Parse Artifacts" in result.output
        assert "Plan Ingestion" in result.output
        assert "Create Beads" in result.output
        assert "Wire Deps" in result.output
        assert "Chain Epic" in result.output
        _mock_execute.assert_not_called()

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_skip_briefing_on_speckit_path_warns_and_is_ignored(
        self, mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        _make_speckit_dir(refuel_env)

        result = cli_runner.invoke(cli, ["refuel", "048", "--speckit", "--skip-briefing"])

        assert result.exit_code == 0, result.output
        assert "Warning" in result.output
        assert "no effect" in result.output
        mock_execute.assert_called_once()

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_success_hint_prints_fly_command(
        self, mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        _make_speckit_dir(refuel_env)
        runs_dir = refuel_env / ".maverick" / "runs" / "abc12345"
        runs_dir.mkdir(parents=True)
        (runs_dir / "metadata.json").write_text(
            '{"run_id": "abc12345", "plan_name": "048-sample-feature", '
            '"epic_id": "epic-1", "status": "refueled", "started_at": "2026-01-01T00:00:00", '
            '"completed_at": ""}',
            encoding="utf-8",
        )

        result = cli_runner.invoke(cli, ["refuel", "048", "--speckit"])

        assert result.exit_code == 0, result.output
        assert "maverick fly --epic epic-1" in result.output


class TestListStepsWithoutResolution:
    """``--list-steps`` must stay inspectable before a plan/feature exists."""

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_list_steps_without_resolution_falls_back_to_classic(
        self, _mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        # NAME resolves to neither a classic plan nor a Spec Kit feature.
        result = cli_runner.invoke(cli, ["refuel", "not-created-yet", "--list-steps"])

        assert result.exit_code == 0, result.output
        # Classic step list is shown (no error about unresolvable name).
        assert "could not resolve" not in result.output
        assert "Briefing" in result.output or "Decompose" in result.output
        _mock_execute.assert_not_called()

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_speckit_list_steps_without_resolution_lists_speckit_steps(
        self, _mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        result = cli_runner.invoke(cli, ["refuel", "not-created-yet", "--speckit", "--list-steps"])

        assert result.exit_code == 0, result.output
        assert "does not resolve" not in result.output
        assert "Resolve Feature" in result.output
        assert "Plan Ingestion" in result.output
        _mock_execute.assert_not_called()


class TestAutoDetection:
    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_speckit_only_dispatches_to_ingestion(
        self, mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        _make_speckit_dir(refuel_env)

        result = cli_runner.invoke(cli, ["refuel", "048-sample-feature"])

        assert result.exit_code == 0, result.output
        assert "Using Spec Kit ingestion" in result.output
        run_config = mock_execute.call_args[0][1]
        from maverick.workflows.refuel_speckit import SpeckitRefuelWorkflow

        assert run_config.workflow_class is SpeckitRefuelWorkflow

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_classic_only_dispatches_to_classic_unchanged(
        self, mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        _make_classic_dir(refuel_env)

        result = cli_runner.invoke(cli, ["refuel", "my-feature"])

        assert result.exit_code == 0, result.output
        assert "Using Spec Kit ingestion" not in result.output
        run_config = mock_execute.call_args[0][1]
        from maverick.workflows.refuel_maverick import RefuelMaverickWorkflow

        assert run_config.workflow_class is RefuelMaverickWorkflow

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_both_match_without_flag_is_e01(
        self, _mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        _make_speckit_dir(refuel_env, name="048-my-feature")
        _make_classic_dir(refuel_env, name="048-my-feature")

        result = cli_runner.invoke(cli, ["refuel", "048-my-feature"])

        assert result.exit_code == 1
        assert "matches both" in result.output
        assert "--speckit" in result.output
        assert "Traceback" not in result.output

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_both_match_with_flag_dispatches_to_speckit(
        self, mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        _make_speckit_dir(refuel_env, name="048-my-feature")
        _make_classic_dir(refuel_env, name="048-my-feature")

        result = cli_runner.invoke(cli, ["refuel", "048-my-feature", "--speckit"])

        assert result.exit_code == 0, result.output
        run_config = mock_execute.call_args[0][1]
        from maverick.workflows.refuel_speckit import SpeckitRefuelWorkflow

        assert run_config.workflow_class is SpeckitRefuelWorkflow

    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_neither_matches_is_e02(
        self, _mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        result = cli_runner.invoke(cli, ["refuel", "does-not-exist"])

        assert result.exit_code == 1
        assert "could not resolve" in result.output
        assert "Traceback" not in result.output


class TestErrorRendering:
    @patch(_PATCH_EXECUTE, new_callable=AsyncMock)
    def test_ambiguous_speckit_candidates_is_e03(
        self, _mock_execute: AsyncMock, cli_runner: CliRunner, refuel_env: Path
    ) -> None:
        _make_speckit_dir(refuel_env, name="048-feature-a")
        _make_speckit_dir(refuel_env, name="048-feature-b")

        result = cli_runner.invoke(cli, ["refuel", "048", "--speckit"])

        assert result.exit_code == 1
        assert "048-feature-a" in result.output
        assert "048-feature-b" in result.output
        assert "Traceback" not in result.output
