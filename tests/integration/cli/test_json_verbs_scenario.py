"""End-to-end scenario test for the ``--json`` verbs added by
053-assumption-review-console (T016).

Automates quickstart.md Scenarios 1-3: a seeded assumption ledger flows
through ``review --list --json`` -> answer one entry -> waive another ->
bulk-waive a spec's low-severity entries -> ``reconcile --dry-run --json``
-> ``land --status --json``. Each step is an independent ``CliRunner``
invocation (no persistent process), so the ledger fixtures for step N+1
are hand-updated to reflect what step N "wrote" — the mutation is asserted
against the mocked ledger call, not against real bd/jj state, but the
mock data threads through so the scenario reads as one coherent narrative.

Mocking style mirrors the existing unit-level JSON tests this feature
added (never real bd/jj processes):

* ``tests/unit/cli/commands/test_review_json.py`` — ``BeadClient.show``/
  ``verify_available`` + ``maverick.assumptions.ledger.{answer,waive,
  bulk_waive}`` patches.
* ``tests/unit/cli/commands/test_reconcile_json.py`` — precondition
  bypass (``_require_bd_ready_json``, a fake ``JjClient``) plus a
  ``ReconcileWorkflow._run`` stub returning a canned report.
* ``tests/unit/cli/commands/test_land_json.py`` / ``test_land_report.py``
  — ``AssumptionRecord``/``AssumptionReportEntry`` construction and
  ``maverick.assumptions.ledger.report_entries`` patching for the land
  frontier gate.

Every invocation asserts stdout parses as exactly one JSON document (the
FR-005/error-envelope.md stream-discipline guarantee) — explicitly via a
single-line stdout check at least once, and implicitly every time
``json.loads(result.stdout)`` succeeds without a trailing-content error.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    KEY_ANSWER,
    KEY_OWNER_SPEC,
    KEY_RECONCILE_STATUS,
    KEY_SEVERITY,
    KEY_SOURCE_BEAD,
    KEY_STATUS,
    KEY_WAIVE_REASON,
    KEY_WAIVED_AT,
    KEY_WAIVED_BY,
    RECONCILE_STATUS_PENDING,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    BulkWaiveResult,
    Severity,
)
from maverick.beads.models import BeadDetails
from maverick.cli.commands.land import land
from maverick.cli.commands.review import review
from maverick.main import cli
from maverick.workflows.reconcile.workflow import ReconcileWorkflow

# ── Shared fixture identifiers ──────────────────────────────────────────

_SPEC_A = "052-conditional-landing"
_SPEC_B = "049-assumption-ledger"

_DEA_1 = "dea-1"  # spec A, medium — answered in step 3
_DEA_2 = "dea-2"  # spec A, high — waived in step 4
_DEA_3 = "dea-3"  # spec B, low — bulk-waived in step 5
_DEA_4 = "dea-4"  # spec B, low — bulk-waived in step 5

_ANSWER_TEXT = "Use ISO-8601 timestamps everywhere."
_WAIVE_REASON_SINGLE = "Accepted risk for MVP."
_WAIVE_REASON_BULK = "Low-severity noise accepted for this spec."


def _description(question: str, adopted_answer: str, source_bead: str = "src-1") -> str:
    """Build a ledger-entry description in the fixed markdown shape
    ``ledger.parse_description`` expects (mirrors ``_LEDGER_DESCRIPTION`` in
    ``tests/unit/cli/commands/test_review_json.py``)."""
    return (
        "## Question\n\n"
        f"{question}\n\n"
        "## Adopted Answer\n\n"
        f"{adopted_answer}\n\n"
        "## Alternatives Considered\n\n(none)\n\n"
        "## Context\n\n"
        f"Source bead: {source_bead} — Implement the thing\n"
    )


def _report_entry(
    *,
    bead_id: str,
    owner_spec: str,
    severity: Severity,
    status: str = STATUS_OPEN,
    question: str = "Should retries be per bead?",
    adopted_answer: str = "Per bead — matches existing scoping.",
    final_answer: str | None = None,
    waived_by: str | None = None,
    waived_at: str | None = None,
    waive_reason: str | None = None,
    reconcile_status: str | None = None,
    pending_reconcile: bool = False,
) -> AssumptionReportEntry:
    """Build one seeded ``AssumptionReportEntry`` fixture (mirrors
    ``_report_entry`` in ``tests/unit/cli/commands/test_land_json.py`` and
    ``_entry`` in ``tests/unit/assumptions/test_land_report.py``)."""
    record = AssumptionRecord(
        bead_id=bead_id,
        question=question,
        adopted_answer=adopted_answer,
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
        final_answer=final_answer,
        waived_by=waived_by,
        waived_at=waived_at,
        waive_reason=waive_reason,
        reconcile_status=reconcile_status,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=pending_reconcile,
    )


def _ledger_details(bead_id: str, owner_spec: str, question: str, **state: str) -> BeadDetails:
    """Build the ``BeadDetails`` ``BeadClient.show`` would return for one
    ledger-entry bead (mirrors ``_ledger_details``/``_waived_details`` in
    ``tests/unit/cli/commands/test_review_json.py``)."""
    return BeadDetails(
        id=bead_id,
        title=f"Assumption: {question}",
        description=_description(question, "Per bead — matches existing scoping."),
        bead_type="task",
        status="open" if state.get(KEY_STATUS) != STATUS_WAIVED else "closed",
        labels=[ASSUMPTION_LABEL],
        state={KEY_OWNER_SPEC: owner_spec, KEY_SOURCE_BEAD: "src-1", **state},
    )


def _seed_open_entries() -> list[AssumptionReportEntry]:
    """The initial open population — 4 entries across 2 specs, mixed
    severity (Scenario 1 step 1: "sweep population")."""
    return [
        _report_entry(bead_id=_DEA_1, owner_spec=_SPEC_A, severity=Severity.MEDIUM),
        _report_entry(bead_id=_DEA_2, owner_spec=_SPEC_A, severity=Severity.HIGH),
        _report_entry(bead_id=_DEA_3, owner_spec=_SPEC_B, severity=Severity.LOW),
        _report_entry(bead_id=_DEA_4, owner_spec=_SPEC_B, severity=Severity.LOW),
    ]


def _assert_single_json_document(stdout: str) -> dict[str, Any]:
    """Assert *stdout* is exactly one parseable JSON document (FR-005 /
    error-envelope.md stream discipline) and return the parsed envelope."""
    stripped = stdout.strip()
    assert stripped, "expected non-empty stdout"
    # A single JSON document has no sibling top-level values after it —
    # json.loads raises on trailing garbage, giving us the check for free,
    # but assert the line-count invariant too (matches the reconcile JSON
    # tests' explicit stdout-purity assertion).
    assert stdout.count("\n") == 1, f"expected exactly one line of stdout, got: {stdout!r}"
    doc = json.loads(stripped)
    assert doc["schema_version"] == 1
    assert isinstance(doc["ok"], bool)
    return doc


class TestJsonVerbsScenario:
    """One coherent walkthrough: list -> answer -> waive -> bulk-waive ->
    reconcile --dry-run -> land --status, all under ``--json``."""

    def test_full_scenario(
        self,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runner = CliRunner()

        # ── Step 1/2: seed + review --list --json ───────────────────────
        seeded = _seed_open_entries()
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.assumptions.ledger.report_entries",
                new=AsyncMock(return_value=tuple(seeded)),
            ),
        ):
            result = runner.invoke(review, ["--list", "--json"])

        assert result.exit_code == 0
        doc = _assert_single_json_document(result.output)
        assert doc["ok"] is True
        assert doc["verb"] == "review.list"

        listed_ids = {row["bead_id"] for row in doc["result"]["entries"]}
        assert listed_ids == {_DEA_1, _DEA_2, _DEA_3, _DEA_4}
        counts = doc["result"]["counts"]
        assert counts["total"] == 4
        assert counts["by_status"]["open"] == 4
        assert counts["by_status"]["answered"] == 0
        assert counts["by_status"]["waived"] == 0
        assert counts["by_severity"] == {"low": 2, "medium": 1, "high": 1}
        assert counts["pending_reconcile"] == 0

        # ── Step 3: answer dea-1 (medium, spec A) ────────────────────────
        before_dea1 = _ledger_details(
            _DEA_1,
            _SPEC_A,
            "Should retries be per bead?",
            **{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN},
        )
        after_dea1 = _ledger_details(
            _DEA_1,
            _SPEC_A,
            "Should retries be per bead?",
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_ANSWERED,
                KEY_ANSWER: _ANSWER_TEXT,
                KEY_RECONCILE_STATUS: RECONCILE_STATUS_PENDING,
            },
        )
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.beads.client.BeadClient.show",
                new=AsyncMock(side_effect=[before_dea1, after_dea1]),
            ),
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, [_DEA_1, "--answer", _ANSWER_TEXT, "--json"])

        assert result.exit_code == 0
        doc = _assert_single_json_document(result.output)
        assert doc["ok"] is True
        assert doc["verb"] == "review.answer"
        assert doc["result"]["action"] == "answered"
        assert doc["result"]["entry"]["bead_id"] == _DEA_1
        assert doc["result"]["entry"]["status"] == "answered"
        assert doc["result"]["entry"]["reconcile"]["status"] == "pending"
        mock_answer.assert_awaited_once()
        assert mock_answer.await_args.kwargs["answer_text"] == _ANSWER_TEXT

        # ── Step 4: waive dea-2 (high, spec A) ───────────────────────────
        before_dea2 = _ledger_details(
            _DEA_2,
            _SPEC_A,
            "Should retries be per bead?",
            **{KEY_SEVERITY: "high", KEY_STATUS: STATUS_OPEN},
        )
        after_dea2 = _ledger_details(
            _DEA_2,
            _SPEC_A,
            "Should retries be per bead?",
            **{
                KEY_SEVERITY: "high",
                KEY_STATUS: STATUS_WAIVED,
                KEY_WAIVED_BY: "alice",
                KEY_WAIVED_AT: "2026-07-25T00:00:00+00:00",
                KEY_WAIVE_REASON: _WAIVE_REASON_SINGLE,
            },
        )
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.beads.client.BeadClient.show",
                new=AsyncMock(side_effect=[before_dea2, after_dea2]),
            ),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            result = runner.invoke(review, [_DEA_2, "--waive", _WAIVE_REASON_SINGLE, "--json"])

        assert result.exit_code == 0
        doc = _assert_single_json_document(result.output)
        assert doc["ok"] is True
        assert doc["verb"] == "review.waive"
        assert doc["result"]["action"] == "waived"
        assert doc["result"]["entry"]["bead_id"] == _DEA_2
        assert doc["result"]["entry"]["status"] == "waived"
        mock_waive.assert_awaited_once()

        # ── Step 5: bulk-waive spec B's low-severity entries ─────────────
        bulk_result = BulkWaiveResult(
            waived=(
                AssumptionRecord(
                    bead_id=_DEA_3,
                    question="Should retries be per bead?",
                    adopted_answer="Per bead — matches existing scoping.",
                    alternatives=(),
                    severity=Severity.LOW,
                    severity_defaulted=False,
                    status=STATUS_WAIVED,
                    owner_spec=_SPEC_B,
                    source_bead="src-1",
                    change_ids=(),
                    is_legacy=False,
                ),
                AssumptionRecord(
                    bead_id=_DEA_4,
                    question="Should retries be per bead?",
                    adopted_answer="Per bead — matches existing scoping.",
                    alternatives=(),
                    severity=Severity.LOW,
                    severity_defaulted=False,
                    status=STATUS_WAIVED,
                    owner_spec=_SPEC_B,
                    source_bead="src-1",
                    change_ids=(),
                    is_legacy=False,
                ),
            ),
            failed={},
        )
        after_dea3 = _ledger_details(
            _DEA_3,
            _SPEC_B,
            "Should retries be per bead?",
            **{
                KEY_SEVERITY: "low",
                KEY_STATUS: STATUS_WAIVED,
                KEY_WAIVED_BY: "alice",
                KEY_WAIVED_AT: "2026-07-25T00:00:00+00:00",
                KEY_WAIVE_REASON: _WAIVE_REASON_BULK,
            },
        )
        after_dea4 = _ledger_details(
            _DEA_4,
            _SPEC_B,
            "Should retries be per bead?",
            **{
                KEY_SEVERITY: "low",
                KEY_STATUS: STATUS_WAIVED,
                KEY_WAIVED_BY: "alice",
                KEY_WAIVED_AT: "2026-07-25T00:00:00+00:00",
                KEY_WAIVE_REASON: _WAIVE_REASON_BULK,
            },
        )
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.beads.client.BeadClient.show",
                new=AsyncMock(side_effect=[after_dea3, after_dea4]),
            ),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch(
                "maverick.assumptions.ledger.bulk_waive",
                new=AsyncMock(return_value=bulk_result),
            ),
        ):
            result = runner.invoke(
                review, ["--spec", _SPEC_B, "--waive", _WAIVE_REASON_BULK, "--json"]
            )

        assert result.exit_code == 0
        doc = _assert_single_json_document(result.output)
        assert doc["ok"] is True
        assert doc["verb"] == "review.bulk-waive"
        assert doc["result"]["owner_spec"] == _SPEC_B
        assert doc["result"]["severities"] == ["low"]
        assert {row["bead_id"] for row in doc["result"]["waived"]} == {_DEA_3, _DEA_4}
        assert doc["result"]["failed"] == {}

        # ── Step 6: reconcile --dry-run --json ───────────────────────────
        # dea-1 is now answered with a reconcile status of "pending" — the
        # detection predicate reconcile relies on. Predict it as
        # "reconciled" (dry-run vocabulary only ever produces
        # reconciled/skipped per the workflow's predictor).
        os.chdir(temp_dir)
        monkeypatch.setattr(Path, "home", lambda: temp_dir)
        (temp_dir / ".jj").mkdir()

        class _FakeJjClient:
            def __init__(self, *, cwd: Path) -> None:
                self._cwd = cwd

            async def diff_stat(self, revision: str = "@") -> SimpleNamespace:
                return SimpleNamespace(files_changed=0)

        monkeypatch.setattr(
            "maverick.cli.commands.reconcile._require_bd_ready_json", lambda cwd: None
        )
        monkeypatch.setattr("maverick.cli.commands.reconcile.JjClient", _FakeJjClient)

        dry_run_report: dict[str, object] = {
            "run_id": "scenario1",
            "outcomes": [
                {
                    "entry_id": _DEA_1,
                    "status": "reconciled",
                    "reason": "",
                    "stage_reached": "terminal",
                    "target_change_id": "qxyzabc",
                    "escalation_bead_id": None,
                    "gate_passed": True,
                    "no_change_required": False,
                }
            ],
            "dry_run": True,
            "started_at": "2026-07-25T00:00:00+00:00",
            "finished_at": "2026-07-25T00:00:01+00:00",
            "exit_success": True,
        }

        async def _fake_run(
            self: ReconcileWorkflow, inputs: dict[str, object]
        ) -> dict[str, object]:
            return dry_run_report

        monkeypatch.setattr(ReconcileWorkflow, "_run", _fake_run)

        cli_runner = CliRunner()
        result = cli_runner.invoke(cli, ["reconcile", "--dry-run", "--json"])

        assert result.exit_code == 0
        doc = _assert_single_json_document(result.stdout)
        assert doc["ok"] is True
        assert doc["verb"] == "reconcile.dry-run"
        assert doc["result"]["dry_run"] is True
        predicted_statuses = {o["status"] for o in doc["result"]["outcomes"]}
        assert predicted_statuses <= {"reconciled", "skipped"}
        assert doc["result"]["outcomes"][0]["entry_id"] == _DEA_1

        # ── Step 7: land --status --json ─────────────────────────────────
        # Reconcile above was only a dry-run preview — nothing was actually
        # reconciled — so dea-1 still carries a "pending" reconcile status
        # and (per 051's detection predicate) blocks the land frontier as
        # pending-reconcile even though every entry has been answered or
        # waived by a human. dea-2/3/4 are waived and no longer block.
        current_entries = [
            _report_entry(
                bead_id=_DEA_1,
                owner_spec=_SPEC_A,
                severity=Severity.MEDIUM,
                status=STATUS_ANSWERED,
                final_answer=_ANSWER_TEXT,
                reconcile_status=RECONCILE_STATUS_PENDING,
                pending_reconcile=True,
            ),
            _report_entry(
                bead_id=_DEA_2,
                owner_spec=_SPEC_A,
                severity=Severity.HIGH,
                status=STATUS_WAIVED,
                waived_by="alice",
                waived_at="2026-07-25T00:00:00+00:00",
                waive_reason=_WAIVE_REASON_SINGLE,
            ),
            _report_entry(
                bead_id=_DEA_3,
                owner_spec=_SPEC_B,
                severity=Severity.LOW,
                status=STATUS_WAIVED,
                waived_by="alice",
                waived_at="2026-07-25T00:00:00+00:00",
                waive_reason=_WAIVE_REASON_BULK,
            ),
            _report_entry(
                bead_id=_DEA_4,
                owner_spec=_SPEC_B,
                severity=Severity.LOW,
                status=STATUS_WAIVED,
                waived_by="alice",
                waived_at="2026-07-25T00:00:00+00:00",
                waive_reason=_WAIVE_REASON_BULK,
            ),
        ]

        runner2 = CliRunner()
        with runner2.isolated_filesystem():
            with (
                patch(
                    "maverick.beads.client.BeadClient.verify_available",
                    new=AsyncMock(return_value=True),
                ),
                patch(
                    "maverick.assumptions.ledger.report_entries",
                    new=AsyncMock(return_value=tuple(current_entries)),
                ),
            ):
                result = runner2.invoke(land, ["--status", "--json"])

            assert result.exit_code == 0
            doc = _assert_single_json_document(result.stdout)
            assert doc["ok"] is True
            assert doc["verb"] == "land.status"
            res = doc["result"]
            assert "frontier_clear" in res
            assert "verification" in res
            assert "blocking" in res
            assert "report" in res
            assert "report_paths" in res
            assert res["frontier_clear"] is False
            assert res["blocking"]["open"] == []
            assert res["blocking"]["pending_reconcile"] == [_DEA_1]
