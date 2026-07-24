"""CLI contract tests for ``maverick reconcile`` (T018) per
specs/051-reconcile-changed-answers/contracts/cli-reconcile.md.

These tests only exercise the CLI's own preconditions, dispatch, and
summary rendering — they never touch a real jj/bd/airframe runtime.
``execute_python_workflow`` and ``load_run_state`` are monkeypatched so
the workflow itself never runs.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from maverick.cli.context import ExitCode
from maverick.main import cli
from maverick.workflows.reconcile.models import ReconcileStage
from maverick.workflows.reconcile.state import AnswerState, ReconcileRunState


def _make_jj_client(files_changed: int) -> type:
    """Build a fake ``JjClient`` replacement reporting *files_changed*."""

    class _FakeJjClient:
        def __init__(self, *, cwd: Path) -> None:
            self._cwd = cwd

        async def diff_stat(self, revision: str = "@") -> SimpleNamespace:
            return SimpleNamespace(files_changed=files_changed)

    return _FakeJjClient


def _stub_preconditions(monkeypatch: pytest.MonkeyPatch, *, files_changed: int = 0) -> None:
    """Bypass bd-ready + jj-clean preconditions so tests reach dispatch."""
    monkeypatch.setattr("maverick.cli.commands.reconcile.verify_bd_ready", lambda cwd=None: None)
    monkeypatch.setattr("maverick.cli.commands.reconcile.JjClient", _make_jj_client(files_changed))


def _stub_workflow_dispatch(
    monkeypatch: pytest.MonkeyPatch, *, run_state: ReconcileRunState | None
) -> dict[str, object]:
    """Fake out the workflow execution + run-state reload."""
    called: dict[str, object] = {}

    async def _fake_execute(ctx: object, run_config: object) -> None:
        called["run_config"] = run_config

    async def _fake_load_run_state(run_id: str, base: Path) -> ReconcileRunState | None:
        called["run_id"] = run_id
        return run_state

    monkeypatch.setattr("maverick.cli.workflow_executor.execute_python_workflow", _fake_execute)
    monkeypatch.setattr("maverick.workflows.reconcile.state.load_run_state", _fake_load_run_state)
    return called


class TestReconcileRegistered:
    def test_reconcile_in_cli_help(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["--help"])
        assert "reconcile" in result.output

    def test_reconcile_help_shows_dry_run(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["reconcile", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output


class TestPreconditions:
    def test_missing_bd_exits_failure(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        with patch("shutil.which", return_value=None):
            result = cli_runner.invoke(cli, ["reconcile"])

        assert result.exit_code == ExitCode.FAILURE

    def test_missing_jj_exits_failure_with_init_hint(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        monkeypatch.setattr(
            "maverick.cli.commands.reconcile.verify_bd_ready", lambda cwd=None: None
        )
        # No .jj/ directory created under temp_dir.

        result = cli_runner.invoke(cli, ["reconcile"])

        assert result.exit_code == ExitCode.FAILURE
        assert "maverick init" in result.output

    def test_dirty_working_copy_exits_failure(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch, files_changed=3)

        result = cli_runner.invoke(cli, ["reconcile"])

        assert result.exit_code == ExitCode.FAILURE
        assert "working copy" in result.output.lower()


class TestSummaryRendering:
    def test_zero_changed_answers_exits_success(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        _stub_workflow_dispatch(monkeypatch, run_state=None)

        result = cli_runner.invoke(cli, ["reconcile"])

        assert result.exit_code == ExitCode.SUCCESS
        assert "nothing to reconcile" in result.output.lower()

    def test_all_reconciled_exits_success_with_table(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        run_state = ReconcileRunState(
            run_id="abc12345",
            status="completed",
            updated_at="2026-07-24T00:00:00+00:00",
            answers=[
                AnswerState(
                    entry_id="bd-1",
                    target_change_id="qxyzabc",
                    restore_op_id="op1",
                    stage=ReconcileStage.TERMINAL,
                    terminal_status="reconciled",
                    reason="",
                ),
            ],
        )
        _stub_workflow_dispatch(monkeypatch, run_state=run_state)

        result = cli_runner.invoke(cli, ["reconcile"])

        assert result.exit_code == ExitCode.SUCCESS
        assert "bd-1" in result.output
        assert "reconciled" in result.output
        assert "maverick review" not in result.output

    def test_needs_interactive_review_exits_failure_with_hint(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        run_state = ReconcileRunState(
            run_id="abc12345",
            status="completed",
            updated_at="2026-07-24T00:00:00+00:00",
            answers=[
                AnswerState(
                    entry_id="bd-2",
                    target_change_id=None,
                    restore_op_id=None,
                    stage=ReconcileStage.TERMINAL,
                    terminal_status="needs_interactive_review",
                    reason="unresolvable correction target",
                ),
            ],
        )
        _stub_workflow_dispatch(monkeypatch, run_state=run_state)

        result = cli_runner.invoke(cli, ["reconcile"])

        assert result.exit_code == ExitCode.FAILURE
        assert "bd-2" in result.output
        # Spelled with a space, not the Python-literal underscore spelling.
        assert "needs interactive review" in result.output
        assert "needs_interactive_review" not in result.output
        assert "maverick review" in result.output

    def test_dispatch_forwards_dry_run_flag(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-``--dry-run`` invocations still dispatch through
        ``execute_python_workflow`` with ``dry_run=False`` forwarded —
        ``--dry-run`` itself is covered by ``TestDryRunSummaryRendering``
        below, which exercises the dedicated in-memory preview path (T035)
        rather than ``execute_python_workflow``/``load_run_state`` (a dry
        run never persists ``reconcile.json``, so that pair would always
        see an empty result — see ``cli/commands/reconcile.py``'s module
        docstring).
        """
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        called = _stub_workflow_dispatch(monkeypatch, run_state=None)

        cli_runner.invoke(cli, ["reconcile"])

        run_config = called["run_config"]
        assert run_config.inputs["dry_run"] is False  # type: ignore[attr-defined]


def _stub_dry_run_result(monkeypatch: pytest.MonkeyPatch, report: dict[str, object]) -> None:
    """Stub `ReconcileWorkflow._run` to return *report* directly.

    The dry-run CLI path (T035) drives the workflow's public `execute()`
    template method directly rather than through
    `execute_python_workflow`/`load_run_state` (a dry run never persists
    `reconcile.json`), so tests patch `_run` — the one seam `execute()`
    calls into — and let the base class's real event-queue/result
    machinery run unmodified, same pattern as
    `tests/unit/workflows/reconcile/test_workflow.py`'s own `_run_workflow`
    helper.
    """
    from maverick.workflows.reconcile.workflow import ReconcileWorkflow

    async def _fake_run(self: ReconcileWorkflow, inputs: dict[str, object]) -> dict[str, object]:
        return report

    monkeypatch.setattr(ReconcileWorkflow, "_run", _fake_run)


def _dry_run_report(
    outcomes: list[dict[str, object]],
    *,
    run_id: str = "dryrun01",
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "outcomes": outcomes,
        "dry_run": True,
        "started_at": "2026-07-24T00:00:00+00:00",
        "finished_at": "2026-07-24T00:00:01+00:00",
        "exit_success": True,
    }


class TestDryRunSummaryRendering:
    """T035: ``--dry-run``'s preview table, footer, and always-SUCCESS exit
    code (contract: "``--dry-run`` with valid preconditions -> SUCCESS(0)
    regardless of predicted statuses").
    """

    def test_would_reconcile_prediction_shows_table_footer_and_exits_success(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        _stub_dry_run_result(
            monkeypatch,
            _dry_run_report(
                [
                    {
                        "entry_id": "bd-1",
                        "status": "reconciled",
                        "reason": "",
                        "stage_reached": "pending",
                        "target_change_id": "qxyzabc",
                        "escalation_bead_id": None,
                        "gate_passed": None,
                        "no_change_required": False,
                    }
                ]
            ),
        )

        result = cli_runner.invoke(cli, ["reconcile", "--dry-run"])

        assert result.exit_code == ExitCode.SUCCESS
        assert "bd-1" in result.output
        assert "would reconcile" in result.output
        assert "Dry run — no changes made." in result.output

    def test_would_skip_prediction_shows_reason_and_still_exits_success(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A predicted "skipped" answer would exit FAILURE(1) on a real run

        (any non-"reconciled" status fails the run per
        ``_render_summary_and_exit``) but must still exit SUCCESS(0) under
        ``--dry-run`` — the contract's exit-code override applies
        regardless of predicted statuses.
        """
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        _stub_dry_run_result(
            monkeypatch,
            _dry_run_report(
                [
                    {
                        "entry_id": "bd-2",
                        "status": "skipped",
                        "reason": "unresolvable correction target",
                        "stage_reached": "pending",
                        "target_change_id": None,
                        "escalation_bead_id": None,
                        "gate_passed": None,
                        "no_change_required": False,
                    }
                ]
            ),
        )

        result = cli_runner.invoke(cli, ["reconcile", "--dry-run"])

        assert result.exit_code == ExitCode.SUCCESS
        assert "bd-2" in result.output
        # The full reason text isn't asserted here: Rich wraps long cell
        # content across lines (and inserts box-border characters mid-word)
        # at the CliRunner's default console width, making an exact
        # substring match unreliable — same reasoning as the real-run
        # `needs_interactive_review` test above, which only checks the
        # status spelling, not the reason text.
        assert "would skip" in result.output
        assert "Dry run — no changes made." in result.output

    def test_zero_changed_answers_dry_run_exits_success(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        _stub_dry_run_result(monkeypatch, _dry_run_report([]))

        result = cli_runner.invoke(cli, ["reconcile", "--dry-run"])

        assert result.exit_code == ExitCode.SUCCESS
        assert "nothing to reconcile" in result.output.lower()

    def test_dry_run_still_enforces_dirty_working_copy_precondition(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``--dry-run`` doesn't bypass the CLI's own refuse-to-start

        preconditions (contract: dry-run only skips the *mutation*
        pipeline) — a dirty working copy still exits FAILURE(1) before the
        workflow is ever dispatched.
        """
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch, files_changed=3)

        result = cli_runner.invoke(cli, ["reconcile", "--dry-run"])

        assert result.exit_code == ExitCode.FAILURE
        assert "working copy" in result.output.lower()
