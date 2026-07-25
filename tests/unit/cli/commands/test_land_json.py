"""Unit tests for ``maverick land``'s JSON modes (053-assumption-review-console).

Covers ``land --status [--json]`` (read-only frontier query, verb
``land.status``) and ``land [--json]`` (the apply path, verb ``land.run``).
Human-mode behavior is exercised by ``test_land_command.py`` and must stay
byte-identical (FR-018) — these tests only exercise the new ``--json``
surface, reusing the mocking conventions from that file
(``_patch_curation``, ``_patch_gate``, ``_report_entry``).

Click 8.2+ always captures stdout/stderr separately, so tests parse
``result.stdout`` (never ``result.output``, which mixes both streams) —
narration in ``--json`` mode is routed to stderr and must never corrupt
the single parseable JSON document on stdout.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.assumptions.models import (
    STATUS_OPEN,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.cli.commands.land import land

# ── Shared helpers (mirrors test_land_command.py) ───────────────────


def _patch_curation(
    *,
    commits: list[Any] | None = None,
    curate_result: dict[str, Any] | None = None,
) -> Any:
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


def _report_entry(
    *,
    bead_id: str = "dea-1",
    severity: Severity = Severity.MEDIUM,
    status: str = STATUS_OPEN,
    owner_spec: str = "049-assumption-ledger",
    pending_reconcile: bool = False,
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
        is_legacy=False,
    )
    return AssumptionReportEntry(
        record=record,
        final_answer=None,
        waived_by=None,
        waived_at=None,
        waive_reason=None,
        reconcile_status=None,
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


def _json_runner() -> CliRunner:
    """A ``CliRunner`` — Click 8.2+ always captures stdout/stderr separately.

    JSON mode routes narration to stderr; tests parse ``result.stdout``
    (never ``result.output``, which mixes both streams) so stderr text can
    never corrupt the single JSON document under test.
    """
    return CliRunner()


# ── land --status [--json] ──────────────────────────────────────────


class TestLandStatusJson:
    def test_status_json_clear_frontier(self) -> None:
        runner = _json_runner()
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with verify, entries_patch:
                result = runner.invoke(land, ["--status", "--json"])
            assert result.exit_code == 0
            doc = json.loads(result.stdout)
            assert doc["ok"] is True
            assert doc["verb"] == "land.status"
            res = doc["result"]
            assert res["frontier_clear"] is True
            assert res["verification"] == "verified"
            assert res["blocking"] == {"open": [], "pending_reconcile": []}
            assert res["report"]["schema_version"] == 1
            assert "json" in res["report_paths"]
            assert "md" in res["report_paths"]

    def test_status_json_blocked_frontier_exits_zero(self) -> None:
        runner = _json_runner()
        entry = _report_entry(severity=Severity.LOW, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with runner.isolated_filesystem():
            with verify, entries_patch:
                result = runner.invoke(land, ["--status", "--json"])
            # Blocked is an ANSWER for a status query, not a failure.
            assert result.exit_code == 0
            doc = json.loads(result.stdout)
            assert doc["ok"] is True
            res = doc["result"]
            assert res["frontier_clear"] is False
            assert res["blocking"]["open"] == ["dea-1"]

    def test_status_json_degraded_verification_is_null(self) -> None:
        runner = _json_runner()
        verify, entries_patch = _patch_gate(bd_available=False)
        with runner.isolated_filesystem():
            with verify, entries_patch:
                result = runner.invoke(land, ["--status", "--json"])
            assert result.exit_code == 0
            doc = json.loads(result.stdout)
            assert doc["result"]["verification"] is None

    @pytest.mark.parametrize(
        "flag",
        ["--dry-run", "--eject", "--finalize", "--no-curate", "--heuristic-only", "--yes"],
    )
    def test_status_mutually_exclusive_with_apply_flags(self, flag: str) -> None:
        runner = _json_runner()
        result = runner.invoke(land, ["--status", flag])
        assert result.exit_code != 0

    def test_status_mutually_exclusive_json_error_envelope(self) -> None:
        runner = _json_runner()
        result = runner.invoke(land, ["--status", "--json", "--dry-run"])
        assert result.exit_code != 0
        doc = json.loads(result.stdout)
        assert doc["ok"] is False
        assert doc["error"]["kind"] == "validation"

    def test_status_does_not_invoke_curation(self) -> None:
        runner = _json_runner()
        verify, entries_patch = _patch_gate(entries=[])
        with (
            verify,
            entries_patch,
            patch("maverick.library.actions.jj.execute_curation_plan") as mock_execute,
            patch("maverick.cli.commands.land._agent_curate") as mock_agent_curate,
            patch("maverick.library.actions.jj.curate_history") as mock_curate_history,
        ):
            result = runner.invoke(land, ["--status", "--json"])
        assert result.exit_code == 0
        mock_execute.assert_not_called()
        mock_agent_curate.assert_not_called()
        mock_curate_history.assert_not_called()


# ── land [--json] (apply path) ──────────────────────────────────────


class TestLandRunJsonGateRefusal:
    def test_gate_refusal_json(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(severity=Severity.LOW, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--yes", "--json"])
            assert result.exit_code != 0
            doc = json.loads(result.stdout)
            assert doc["ok"] is False
            assert doc["verb"] == "land.run"
            assert doc["error"]["kind"] == "frontier-blocked"
            assert "totals" in doc["error"]["details"]["report"]


class TestLandRunJsonConfirmationRequired:
    def test_confirmation_required_before_execute(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])

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

        with runner.isolated_filesystem():
            with (
                gather,
                curate,
                consolidate,
                verify,
                entries_patch,
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
                patch("maverick.library.actions.jj.execute_curation_plan") as mock_execute,
            ):
                result = runner.invoke(land, ["--json"])
            assert result.exit_code != 0
            doc = json.loads(result.stdout)
            assert doc["ok"] is False
            assert doc["error"]["kind"] == "confirmation-required"
            mock_execute.assert_not_called()


class TestLandRunJsonSuccess:
    def test_success_default_mode(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--yes", "--json"])
            assert result.exit_code == 0
            doc = json.loads(result.stdout)
            assert doc["ok"] is True
            res = doc["result"]
            assert res["landed"] is True
            assert res["verification"] in {"verified", "conditionally-verified"}
            assert res["mode"] == "approve"
            assert res["curation"]["strategy"] == "none"
            assert "report" in res
            assert "report_paths" in res

    def test_success_eject_mode(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--yes", "--eject", "--json"])
            assert result.exit_code == 0
            doc = json.loads(result.stdout)
            assert doc["result"]["mode"] == "eject"
            assert doc["result"]["hint"] is not None

    def test_success_finalize_mode(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--yes", "--finalize", "--json"])
            assert result.exit_code == 0
            doc = json.loads(result.stdout)
            assert doc["result"]["mode"] == "finalize"


class TestLandRunJsonNothingToLand:
    def test_nothing_to_land_json(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation(commits=[])
        with gather, curate, consolidate:
            result = runner.invoke(land, ["--no-curate", "--json"])
        assert result.exit_code == 0
        doc = json.loads(result.stdout)
        assert doc["ok"] is True
        # Same key set as every other `land.run` success document, so a
        # consumer reading `verification`/`report`/`curation` never
        # KeyErrors just because nothing sat above base.
        assert doc["result"] == {
            "landed": False,
            "reason": "nothing-to-land",
            "mode": "approve",
            "verification": None,
            "degraded": False,
            "curation": {"strategy": "none", "executed_count": 0, "total_count": 0},
            "report": None,
            "report_paths": {},
            "hint": None,
        }

    def test_nothing_to_land_shape_matches_landed_shape(self) -> None:
        """The early return must not drop keys the apply path emits."""
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation(commits=[])
        with gather, curate, consolidate:
            empty = runner.invoke(land, ["--no-curate", "--json"])
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with _json_runner().isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                landed = runner.invoke(land, ["--no-curate", "--yes", "--json"])
        empty_keys = set(json.loads(empty.stdout)["result"])
        landed_keys = set(json.loads(landed.stdout)["result"])
        assert landed_keys - {"reason"} <= empty_keys


class TestLandRunJsonDryRunDeferred:
    def test_dry_run_blocked_frontier_defers_exit(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation()
        entry = _report_entry(severity=Severity.LOW, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--dry-run", "--json"])
            # Preview still runs and the document reports the block; exit
            # is deferred to the end rather than short-circuiting early.
            assert result.exit_code != 0
            doc = json.loads(result.stdout)
            assert doc["ok"] is False
            assert doc["error"]["kind"] == "frontier-blocked"

    def test_dry_run_clear_frontier_succeeds(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--dry-run", "--json"])
            assert result.exit_code == 0
            doc = json.loads(result.stdout)
            assert doc["ok"] is True
            assert doc["result"]["landed"] is False
            assert doc["result"]["mode"] == "dry-run"


class TestLandStatusDegradedSignal:
    """A ledger that couldn't be read is NOT a clear frontier.

    `_check_assumption_gate` degrades open (returns no entries) when bd is
    unavailable, so `frontier_clear` is trivially true. Without a top-level
    `degraded` flag, that document is indistinguishable from a genuinely
    verified one and a consumer would offer to land over unresolved
    high-severity entries.
    """

    def test_bd_unavailable_marks_degraded(self) -> None:
        runner = _json_runner()
        verify, entries_patch = _patch_gate(bd_available=False)
        with runner.isolated_filesystem():
            with verify, entries_patch:
                result = runner.invoke(land, ["--status", "--json"])
            assert result.exit_code == 0
            doc = json.loads(result.stdout)
            assert doc["ok"] is True
            assert doc["result"]["degraded"] is True
            assert doc["result"]["verification"] is None
            # `frontier_clear` alone must not be read as landable.
            assert doc["result"]["frontier_clear"] is True

    def test_healthy_ledger_is_not_degraded(self) -> None:
        runner = _json_runner()
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with verify, entries_patch:
                result = runner.invoke(land, ["--status", "--json"])
            doc = json.loads(result.stdout)
            assert doc["result"]["degraded"] is False
            assert doc["result"]["verification"] == "verified"

    def test_degraded_is_distinct_from_degraded_persistence(self) -> None:
        """The two flags mean different things and must not be conflated."""
        runner = _json_runner()
        verify, entries_patch = _patch_gate(bd_available=False)
        with runner.isolated_filesystem():
            with verify, entries_patch:
                result = runner.invoke(land, ["--status", "--json"])
            doc = json.loads(result.stdout)
            assert doc["result"]["degraded"] is True
            # Persistence succeeded — only the ledger read degraded.
            assert "degraded_persistence" not in doc["result"]


class TestLandRunDegradedSignal:
    def test_apply_path_reports_degraded(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation()
        verify, entries_patch = _patch_gate(bd_available=False)
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--no-curate", "--yes", "--json"])
            doc = json.loads(result.stdout)
            assert doc["result"]["degraded"] is True
            assert doc["result"]["verification"] is None


class TestHeuristicCurationSummary:
    """An absorb-only rewrite must not report as a no-op.

    `squashed_count` alone can't distinguish "absorb folded 6 fixups,
    nothing squashable" from "nothing to do" — both are 0.
    """

    def test_absorb_only_is_reported(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation(
            curate_result={
                "success": True,
                "absorb_ran": True,
                "squashed_count": 0,
                "error": None,
            }
        )
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--heuristic-only", "--yes", "--json"])
            doc = json.loads(result.stdout)
            curation = doc["result"]["curation"]
            assert curation["strategy"] == "heuristic"
            assert curation["absorb_ran"] is True
            assert curation["squashed_count"] == 0

    def test_squash_counts_are_reported(self) -> None:
        runner = _json_runner()
        gather, curate, consolidate = _patch_curation(
            curate_result={
                "success": True,
                "absorb_ran": False,
                "squashed_count": 3,
                "error": None,
            }
        )
        verify, entries_patch = _patch_gate(entries=[])
        with runner.isolated_filesystem():
            with gather, curate, consolidate, verify, entries_patch:
                result = runner.invoke(land, ["--heuristic-only", "--yes", "--json"])
            curation = json.loads(result.stdout)["result"]["curation"]
            assert curation["absorb_ran"] is False
            assert curation["squashed_count"] == 3
            assert curation["executed_count"] == 3
            assert curation["total_count"] == 3


class TestLandStatusHumanModeNoDuplicateRows:
    """`land --status` renders the full provenance report itself.

    Letting the gate print its own blocking panel too would list every
    blocking entry twice in one invocation.
    """

    def test_blocking_entry_appears_once(self) -> None:
        runner = CliRunner()
        entry = _report_entry(bead_id="dea-77", severity=Severity.HIGH, status=STATUS_OPEN)
        verify, entries_patch = _patch_gate(entries=[entry])
        with runner.isolated_filesystem():
            with verify, entries_patch:
                result = runner.invoke(land, ["--status"])
            assert result.exit_code == 0
            assert result.output.count("dea-77") == 1
            assert "Blocking Assumptions" not in result.output
