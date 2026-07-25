"""Unit tests for the ``maverick land`` CLI command.

The single-repo land flow is small enough that the tests exercise the
public ``land`` Click command directly via ``CliRunner``. WorkspaceManager
mocking is gone — there is no workspace any more.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from maverick.assumptions.models import (
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.cli.commands.land import (
    _agent_curate,
    _display_plan,
    land,
)

# ── Help-text tests ──────────────────────────────────────────────────


class TestLandHelp:
    """Verify all CLI options appear in help output."""

    def test_land_in_cli(self) -> None:
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        assert "curate" in result.output.lower()

    def test_land_help_shows_all_options(self) -> None:
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        for option in [
            "--no-curate",
            "--dry-run",
            "--yes",
            "--base",
            "--heuristic-only",
            "--eject",
            "--finalize",
            "--no-consolidate",
            "--branch",
        ]:
            assert option in result.output, f"missing {option}"


# ── Helper: shared patcher ──────────────────────────────────────────


def _patch_curation(
    *,
    commits: list[Any] | None = None,
    curate_result: dict[str, Any] | None = None,
) -> Any:
    """Patch the action surface land relies on.

    Returns a tuple of patch context managers that callers ``stack=`` into
    ``with`` blocks. Both ``gather_curation_context`` and
    ``curate_history`` are patched at their import sites in the action
    module, plus the consolidation helper is muted.
    """
    if commits is None:
        commits = [{"id": "abc", "subject": "test"}]
    if curate_result is None:
        curate_result = {
            "success": True,
            "absorb_ran": False,
            "squashed_count": 0,
            "error": None,
        }

    return (
        patch(
            "maverick.library.actions.jj.gather_curation_context",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "commits": commits,
                    "log_summary": "...",
                    "error": None,
                },
            ),
        ),
        patch(
            "maverick.library.actions.jj.curate_history",
            new=AsyncMock(return_value=curate_result),
        ),
        patch(
            "maverick.cli.commands.land._maybe_consolidate",
            new=AsyncMock(),
        ),
    )


# ── No-op paths ──────────────────────────────────────────────────────


class TestLandNoCommits:
    def test_nothing_to_land_returns_cleanly(self) -> None:
        """When the curation context surfaces zero commits, land exits cleanly."""
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation(commits=[])
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Nothing to land" in result.output

    def test_gather_failure_exits_with_failure(self) -> None:
        """gather_curation_context failure → SystemExit(FAILURE)."""
        runner = CliRunner()
        with patch(
            "maverick.library.actions.jj.gather_curation_context",
            new=AsyncMock(
                return_value={
                    "success": False,
                    "commits": [],
                    "log_summary": "",
                    "error": "boom",
                },
            ),
        ):
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code != 0
        assert "Failed to gather commit context" in result.output


# ── Curation paths ──────────────────────────────────────────────────


class TestHeuristicCurate:
    def test_heuristic_runs_curate_history(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation(
            curate_result={
                "success": True,
                "absorb_ran": True,
                "squashed_count": 2,
                "error": None,
            },
        )
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--heuristic-only", "--yes"])
        assert result.exit_code == 0
        assert "Heuristic curation" in result.output
        assert "absorb=yes" in result.output
        assert "squashed=2" in result.output

    def test_heuristic_failure_exits_with_failure(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation(
            curate_result={
                "success": False,
                "absorb_ran": False,
                "squashed_count": 0,
                "error": "jj absorb failed",
            },
        )
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--heuristic-only", "--yes"])
        assert result.exit_code != 0
        assert "Heuristic curation failed" in result.output


class TestNoCurate:
    def test_no_curate_skips_curation_runs_consolidation(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Skipping curation" in result.output


class TestDryRun:
    def test_dry_run_skips_next_step_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--dry-run"])
        assert result.exit_code == 0
        # Dry run path prints this message and returns before hint logic.
        assert "Dry run" in result.output


# ── Mode hints ──────────────────────────────────────────────────────


class TestModeHints:
    def test_default_mode_prints_generic_next_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Next: push the curated branch" in result.output

    def test_eject_mode_prints_preview_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--eject"])
        assert result.exit_code == 0
        assert "Eject hint" in result.output
        assert "maverick/preview/" in result.output

    def test_finalize_mode_prints_finalize_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--finalize"])
        assert result.exit_code == 0
        assert "Finalize hint" in result.output
        assert "gh pr create" in result.output

    def test_eject_branch_override(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--eject", "--branch", "wip/foo"])
        assert result.exit_code == 0
        assert "wip/foo" in result.output


# ── Assumption ledger gate ──────────────────────────────────────────


def _report_entry(
    *,
    bead_id: str = "dea-1",
    severity: Severity = Severity.MEDIUM,
    status: str = STATUS_OPEN,
    owner_spec: str = "049-assumption-ledger",
    pending_reconcile: bool = False,
    reconcile_status: str | None = None,
    is_legacy: bool = False,
) -> AssumptionReportEntry:
    record = AssumptionRecord(
        bead_id=bead_id,
        question="Should retries be per bead?",
        adopted_answer="Per bead.",
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status=status,
        owner_spec=owner_spec,
        source_bead="src-1",
        change_ids=(),
        is_legacy=is_legacy,
    )
    return AssumptionReportEntry(
        record=record,
        final_answer="Per bead." if status == STATUS_ANSWERED else None,
        waived_by="alice" if status == STATUS_WAIVED else None,
        waived_at="2026-07-24T14:00:00Z" if status == STATUS_WAIVED else None,
        waive_reason="n/a" if status == STATUS_WAIVED else None,
        reconcile_status=reconcile_status,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=pending_reconcile,
    )


def _patch_gate(*, entries: list[AssumptionReportEntry] | None = None, bd_available: bool = True):
    return (
        patch(
            "maverick.beads.client.BeadClient.verify_available",
            new=AsyncMock(return_value=bd_available),
        ),
        patch(
            "maverick.assumptions.ledger.report_entries",
            new=AsyncMock(return_value=tuple(entries or ())),
        ),
    )


class TestAssumptionGate:
    def test_open_low_severity_blocks_with_nonzero_exit(self) -> None:
        """Strict gate (Clarifications 2026-07-24): even low severity blocks."""
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(severity=Severity.LOW, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate", "--yes"])
        assert result.exit_code != 0
        assert "dea-1" in result.output
        assert "049-assumption-ledger" in result.output
        assert "maverick review" in result.output

    def test_open_medium_severity_blocks_with_nonzero_exit(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(severity=Severity.MEDIUM, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate", "--yes"])
        assert result.exit_code != 0
        assert "dea-1" in result.output

    def test_pending_reconciliation_entry_blocks_with_reconcile_hint(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(status=STATUS_ANSWERED, pending_reconcile=True)
        verify, entries_patch = _patch_gate(entries=[entry])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate", "--yes"])
        assert result.exit_code != 0
        assert "maverick reconcile" in result.output

    def test_waived_only_frontier_lands_conditionally_verified(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(status=STATUS_WAIVED)
        verify, entries_patch = _patch_gate(entries=[entry])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Conditionally verified" in result.output

    def test_all_answered_lands_verified(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(status=STATUS_ANSWERED)
        verify, entries_patch = _patch_gate(entries=[entry])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Verified" in result.output

    def test_zero_entries_lands_verified(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Verified" in result.output

    def test_terminal_reconciled_entry_does_not_block(self) -> None:
        entry = _report_entry(
            status=STATUS_ANSWERED, pending_reconcile=False, reconcile_status="reconciled"
        )
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[entry])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Verified" in result.output

    def test_dry_run_still_evaluates_and_exits_nonzero_at_end(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(severity=Severity.LOW, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate", "--dry-run"])
        # The rest of the (no-op) preview still runs...
        assert "Dry run" in result.output
        assert "dea-1" in result.output
        # ...but the command exits non-zero because a real land would block.
        assert result.exit_code != 0

    def test_dry_run_heuristic_only_path_exits_nonzero_when_blocked(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(severity=Severity.LOW, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--heuristic-only", "--dry-run", "--yes"])
        assert result.exit_code != 0

    def test_no_bd_available_gate_passes_no_classification(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(bd_available=False)
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "Verified" not in result.output
        assert "Conditionally verified" not in result.output

    def test_help_exposes_no_bypass_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(land, ["--help"])
        assert result.exit_code == 0
        for flag in ("--force", "--skip-gate", "--bypass", "--no-gate"):
            assert flag not in result.output


class TestAgentCurateDryRunDoesNotPreemptGate:
    """T012 fix (analysis I1): `_agent_curate`'s dry-run branch used to raise
    ``SystemExit(SUCCESS)`` directly, pre-empting land()'s own gate-driven
    exit code. It must now return normally so the caller decides the exit.
    """

    async def test_dry_run_with_nonempty_plan_does_not_raise(self, tmp_path: Any) -> None:
        curation_ctx = {"commits": [{"id": "c1", "subject": "x"}], "log_summary": "..."}

        class _FakeStep:
            command = "describe"
            args = ("-m", "msg")
            reason = "tidy"

        class _FakePayload:
            steps = (_FakeStep(),)

        class _FakeCuratorAgent:
            def __init__(self, **_kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> _FakeCuratorAgent:
                return self

            async def __aexit__(self, *_args: Any) -> bool:
                return False

            async def curate(self, _prompt: str) -> _FakePayload:
                return _FakePayload()

        with (
            patch("maverick.agents.personas.CuratorAgent", _FakeCuratorAgent),
            patch("maverick.config.load_config"),
            patch(
                "maverick.runtime.agent_factory.runtime_for_agent",
                return_value=(object(), None),
            ),
            patch(
                "maverick.library.actions.curation.build_curator_prompt",
                return_value="prompt",
            ),
            patch(
                "maverick.library.actions.curation.ensure_refs_trailers",
                side_effect=lambda plan, commits: plan,
            ),
        ):
            # Must return normally (no SystemExit) — the caller (`land()`)
            # is what decides the final exit code based on the gate.
            await _agent_curate(
                curation_ctx=curation_ctx,
                base="main",
                dry_run=True,
                auto_approve=True,
                cwd=tmp_path,
            )


# ── Land report rendering + persistence (US2) ───────────────────────


class TestLandReportRendering:
    def test_report_persisted_on_blocked_evaluation(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(severity=Severity.LOW, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--yes"])
            assert result.exit_code != 0
            assert "Report:" in result.output
            runs_dir = Path(".maverick") / "runs"
            run_dirs = list(runs_dir.iterdir())
            assert len(run_dirs) == 1
            assert (run_dirs[0] / "land-report.json").is_file()
            assert (run_dirs[0] / "land-report.md").is_file()

    def test_report_persisted_on_successful_evaluation(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(status=STATUS_ANSWERED)
        verify, entries_patch = _patch_gate(entries=[entry])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate"])
            assert result.exit_code == 0
            runs_dir = Path(".maverick") / "runs"
            run_dirs = list(runs_dir.iterdir())
            assert len(run_dirs) == 1
            data = json.loads((run_dirs[0] / "land-report.json").read_text())
            assert data["verification"] == "verified"

    def test_report_persisted_on_dry_run_evaluation(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--dry-run"])
            assert result.exit_code == 0
            runs_dir = Path(".maverick") / "runs"
            assert len(list(runs_dir.iterdir())) == 1

    def test_persistence_failure_degrades_to_warning_same_exit_code(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with (
            gather,
            curate,
            consolidate,
            verify,
            entries_patch,
            patch(
                "maverick.assumptions.land_report.persist_report",
                side_effect=OSError("disk full"),
            ),
        ):
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "disk full" in result.output.lower() or "warning" in result.output.lower()

    def test_finalize_hint_references_body_file(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--finalize"])
            assert result.exit_code == 0
            assert "--body-file" in result.output
            assert "land-report.md" in result.output

    def test_zero_entries_prints_no_assumptions_adopted(self) -> None:
        runner = CliRunner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with gather, curate, consolidate, verify, entries_patch:
            result = runner.invoke(land, ["--no-curate"])
        assert result.exit_code == 0
        assert "No assumptions adopted" in result.output


# ── Display plan ────────────────────────────────────────────────────


class TestDisplayPlan:
    def test_display_plan_renders_table(self) -> None:
        """Smoke test for the curation-plan renderer."""
        plan = [
            {"command": "describe", "args": ["-m", "fix bug"], "reason": "tighten msg"},
            {"command": "squash", "args": ["x", "y"], "reason": "fold fixup"},
        ]
        # Function does not raise; output sinks to console. The test
        # verifies the call itself doesn't blow up on real plan input.
        _display_plan(plan)


# ── pytest-asyncio mode ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _configure_asyncio() -> None:
    """Tests in this module are sync (CliRunner). The fixture exists
    only to silence pytest-asyncio's scope warnings if a future test
    adds async helpers."""
    return None


# ── Misc: top-level mock_runner kept for downstream callers ─────────


def _make_mock_command_runner() -> patch:
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.stderr = ""
    mock_runner = AsyncMock()
    mock_runner.run.return_value = mock_result
    return patch(
        "maverick.runners.command.CommandRunner",
        return_value=mock_runner,
    )
