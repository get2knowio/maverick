"""CLI contract tests for ``maverick reconcile --json`` (T008) per
specs/053-assumption-review-console/contracts/cli-reconcile-json.md.

Mirrors ``tests/unit/cli/test_reconcile_command.py``'s stubbing style, but
JSON mode bypasses ``execute_python_workflow``/``load_run_state`` entirely
(both the real run and dry-run paths drive ``ReconcileWorkflow.execute()``
directly — see ``src/maverick/cli/commands/reconcile.py``'s
``_run_reconcile_json`` docstring for why), so these tests stub
``ReconcileWorkflow._run`` — the one seam ``execute()`` calls into — same
pattern as the existing file's ``_stub_dry_run_result`` helper.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.testing import CliRunner, Result

from maverick.cli.context import ExitCode
from maverick.exceptions import WorkflowError
from maverick.main import cli
from maverick.workflows.reconcile.workflow import ReconcileWorkflow


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
    monkeypatch.setattr("maverick.cli.commands.reconcile._require_bd_ready_json", lambda cwd: None)
    monkeypatch.setattr("maverick.cli.commands.reconcile.JjClient", _make_jj_client(files_changed))


def _report(
    outcomes: list[dict[str, object]],
    *,
    run_id: str = "ab12cd34",
    dry_run: bool = False,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "outcomes": outcomes,
        "dry_run": dry_run,
        "started_at": "2026-07-25T00:00:00+00:00",
        "finished_at": "2026-07-25T00:00:01+00:00",
        "exit_success": all(o["status"] == "reconciled" for o in outcomes),
    }


def _outcome(
    entry_id: str,
    status: str,
    *,
    reason: str = "",
    stage_reached: str = "terminal",
    target_change_id: str | None = "qxyzabc",
    escalation_bead_id: str | None = None,
    gate_passed: bool | None = True,
    no_change_required: bool = False,
) -> dict[str, object]:
    return {
        "entry_id": entry_id,
        "status": status,
        "reason": reason,
        "stage_reached": stage_reached,
        "target_change_id": target_change_id,
        "escalation_bead_id": escalation_bead_id,
        "gate_passed": gate_passed,
        "no_change_required": no_change_required,
    }


def _stub_run_returns(
    monkeypatch: pytest.MonkeyPatch,
    report: dict[str, object],
    *,
    emit_progress: bool = False,
) -> None:
    """Stub ``ReconcileWorkflow._run`` to return *report* directly.

    Optionally emits a couple of progress events first (via the base
    class's real ``emit_step_started``/``emit_step_completed``) so tests
    can assert progress narration lands on stderr, not stdout.
    """

    outcomes = report["outcomes"]
    assert isinstance(outcomes, list)

    async def _fake_run(self: ReconcileWorkflow, inputs: dict[str, object]) -> dict[str, object]:
        if emit_progress:
            await self.emit_step_started("detect", display_label="Detecting changed answers")
            await self.emit_step_completed("detect", output={"count": len(outcomes)})
        return report

    monkeypatch.setattr(ReconcileWorkflow, "_run", _fake_run)


def _stub_run_raises(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    async def _fake_run(self: ReconcileWorkflow, inputs: dict[str, object]) -> dict[str, object]:
        raise exc

    monkeypatch.setattr(ReconcileWorkflow, "_run", _fake_run)


def _invoke(cli_runner: CliRunner, *args: str) -> Result:
    return cli_runner.invoke(cli, ["reconcile", *args])


class TestReconcileRunJsonSuccess:
    def test_empty_outcomes_exits_success(
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
        _stub_run_returns(monkeypatch, _report([]))

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["verb"] == "reconcile.run"
        assert data["result"]["outcomes"] == []
        assert data["result"]["exit_success"] is True

    def test_all_reconciled_exits_success(
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
        report = _report([_outcome("bd-1", "reconciled")])
        _stub_run_returns(monkeypatch, report)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"] == report

    def test_escalated_outcome_exits_failure_but_ok_true(
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
        report = _report(
            [
                _outcome(
                    "bd-2",
                    "needs_interactive_review",
                    reason="conflict resolution budget exhausted",
                    target_change_id=None,
                    gate_passed=False,
                )
            ]
        )
        _stub_run_returns(monkeypatch, report)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["outcomes"][0]["status"] == "needs_interactive_review"

    def test_skipped_outcome_exits_failure_but_ok_true(
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
        report = _report(
            [_outcome("bd-3", "skipped", reason="unresolvable target", target_change_id=None)]
        )
        _stub_run_returns(monkeypatch, report)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is True


class TestReconcileRunJsonPreconditions:
    def test_bd_unavailable(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)

        # Only "bd" should appear missing — a global `shutil.which` stub
        # (as the human-mode precondition test uses) also blanks out
        # git/gh, tripping the CLI group's own git/gh preflight gate
        # (main.py) before this command ever runs.
        real_which = shutil.which

        def _fake_which(
            cmd: str, mode: int = os.F_OK | os.X_OK, path: str | None = None
        ) -> str | None:
            if cmd == "bd":
                return None
            return real_which(cmd, mode, path)

        with patch("shutil.which", side_effect=_fake_which):
            result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "bd-unavailable"
        assert data["verb"] == "reconcile.run"

    def test_jj_missing_maps_to_vcs(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        monkeypatch.setattr(
            "maverick.cli.commands.reconcile._require_bd_ready_json", lambda cwd: None
        )
        # No .jj/ directory created under temp_dir.

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "vcs"

    def test_dirty_working_copy(
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

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "dirty-working-copy"

    def test_concurrent_fly_run(
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
        _stub_run_raises(
            monkeypatch, WorkflowError("cannot run reconcile while a fly run is in progress")
        )

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "concurrent-run"

    def test_lockfile_held(
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
        _stub_run_raises(
            monkeypatch,
            WorkflowError(
                "another reconcile run is already in progress (lockfile held by a live process)"
            ),
        )

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["error"]["kind"] == "locked"


class TestReconcileDryRunJson:
    def test_always_exits_success_with_dry_run_true(
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
        report = _report([_outcome("bd-1", "skipped", target_change_id=None)], dry_run=True)
        _stub_run_returns(monkeypatch, report)

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["verb"] == "reconcile.dry-run"
        assert data["result"]["dry_run"] is True

    def test_empty_outcomes_exits_success(
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
        _stub_run_returns(monkeypatch, _report([], dry_run=True))

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["result"]["outcomes"] == []

    def test_predicted_statuses_only_reconciled_or_skipped(
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
        report = _report(
            [_outcome("bd-1", "reconciled"), _outcome("bd-2", "skipped", target_change_id=None)],
            dry_run=True,
        )
        _stub_run_returns(monkeypatch, report)

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.SUCCESS
        statuses = {o["status"] for o in json.loads(result.stdout)["result"]["outcomes"]}
        assert statuses <= {"reconciled", "skipped"}

    def test_dirty_working_copy_precondition_still_enforced(
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

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.FAILURE
        data = json.loads(result.stdout)
        assert data["error"]["kind"] == "dirty-working-copy"


class TestReconcileJsonStdoutPurity:
    def test_stdout_is_exactly_one_document_progress_on_stderr(
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
        report = _report([_outcome("bd-1", "reconciled")])
        _stub_run_returns(monkeypatch, report, emit_progress=True)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        # Exactly one parseable JSON document on stdout, no interleaved
        # progress text.
        assert result.stdout.count("\n") == 1
        parsed = json.loads(result.stdout.strip())
        assert parsed["ok"] is True
        assert "Detecting changed answers" not in result.stdout

        # Progress narration landed on stderr instead.
        assert "Detecting changed answers" in result.stderr

    def test_dry_run_stdout_is_exactly_one_document(
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
        report = _report([_outcome("bd-1", "reconciled")], dry_run=True)
        _stub_run_returns(monkeypatch, report, emit_progress=True)

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.SUCCESS
        assert result.stdout.count("\n") == 1
        json.loads(result.stdout.strip())
        assert "Detecting changed answers" in result.stderr
        assert "Detecting changed answers" not in result.stdout


class TestReconcileJsonDispatchParity:
    """`--json` bypasses `execute_python_workflow`, so the things that
    helper wires up must be wired here too — otherwise the JSON path
    silently loses behavior the human path has.
    """

    def test_real_run_gets_a_checkpoint_store(
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
        _stub_run_returns(monkeypatch, _report([]))

        seen: list[object] = []
        real_init = ReconcileWorkflow.__init__

        def _spy_init(self: ReconcileWorkflow, **kwargs: object) -> None:
            seen.append(kwargs.get("checkpoint_store"))
            real_init(self, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(ReconcileWorkflow, "__init__", _spy_init)

        result = _invoke(cli_runner, "--json")

        assert result.exit_code == ExitCode.SUCCESS
        assert seen and seen[0] is not None, "real --json run must get a checkpoint store"

    def test_dry_run_gets_no_checkpoint_store(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`--dry-run` guarantees zero filesystem mutations."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        _stub_run_returns(monkeypatch, _report([], dry_run=True))

        seen: list[object] = []
        real_init = ReconcileWorkflow.__init__

        def _spy_init(self: ReconcileWorkflow, **kwargs: object) -> None:
            seen.append(kwargs.get("checkpoint_store"))
            real_init(self, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(ReconcileWorkflow, "__init__", _spy_init)

        result = _invoke(cli_runner, "--dry-run", "--json")

        assert result.exit_code == ExitCode.SUCCESS
        assert seen and seen[0] is None
        assert not (temp_dir / ".maverick" / "checkpoints").exists()

    def test_verbosity_is_threaded_into_progress_rendering(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`maverick -v reconcile --json` must render verbose progress."""
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()
        _stub_preconditions(monkeypatch)
        _stub_run_returns(monkeypatch, _report([]))

        captured: dict[str, object] = {}
        import maverick.cli.workflow_executor as wfe

        real_render = wfe.render_workflow_events

        async def _spy_render(events: object, console_obj: object, **kwargs: object) -> None:
            captured.update(kwargs)
            await real_render(events, console_obj, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(wfe, "render_workflow_events", _spy_render)

        result = cli_runner.invoke(cli, ["-v", "reconcile", "--json"])

        assert result.exit_code == ExitCode.SUCCESS
        assert captured.get("verbosity") == 1
        assert "total_steps" in captured
