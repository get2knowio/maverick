"""Decision-capture wiring tests for ``maverick review`` (T005,
055-learned-assumption-resolution, User Story 1).

**RED-STATE MARKER**: at the time this module was written,
``entry_actions.py``'s ``_review_ledger_entry``/``_bulk_waive_flow`` do not
write anything to the runway decisions corpus — ``RunwayStore`` has no
``append_decision``/``get_decisions`` methods and ``runway/models.py`` has
no ``DecisionRecord`` yet. These tests assert directly on
``.maverick/runway/decisions.jsonl`` content (raw JSON dicts, not a
``DecisionRecord`` model) rather than importing that model, so a missing
class doesn't break collection of this module — see
specs/055-learned-assumption-resolution/contracts/decision-records.md
("Decision capture points") and research.md R6. They are expected to FAIL
until that wiring lands; do not "fix" them by loosening the assertions —
the next task implements the production wiring these tests pin down.

Mirrors the mocking style of ``tests/unit/cli/test_review_command.py`` /
``tests/unit/cli/commands/test_review_json.py`` — patch ``BeadClient``
methods and the ``maverick.assumptions.ledger`` functions (function-local
imports in the command modules), never real ``bd``.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    KEY_SEVERITY,
    KEY_STATUS,
    KEY_SUGGESTION,
    STATUS_OPEN,
    AssumptionRecord,
    BulkWaiveResult,
    Severity,
    Suggestion,
    suggestion_to_json,
)
from maverick.beads.models import BeadDetails
from maverick.cli.commands.review import review

_LEDGER_DESCRIPTION = (
    "## Question\n\nShould retries be per bead?\n\n"
    "## Adopted Answer\n\nPer bead — matches existing scoping.\n\n"
    "## Alternatives Considered\n\n(none)\n\n"
    "## Context\n\nSource bead: src-1 — Implement the thing\n"
)


def _ledger_details(bead_id: str = "dea-1", **state: str) -> BeadDetails:
    return BeadDetails(
        id=bead_id,
        title="Assumption: Should retries be per bead?",
        description=_LEDGER_DESCRIPTION,
        bead_type="task",
        status="open",
        labels=[ASSUMPTION_LABEL],
        state=state,
    )


def _patch_client(details: BeadDetails):
    """Single-response ``BeadClient`` patch — human mode never re-reads
    the bead after a write (that re-read is a ``--json``-only concern in
    ``_project_after_write``), so one canned ``show()`` response is
    sufficient for every test in this module."""
    return (
        patch(
            "maverick.beads.client.BeadClient.verify_available",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "maverick.beads.client.BeadClient.show",
            new=AsyncMock(return_value=details),
        ),
    )


def _waived_record(bead_id: str, question: str = "Q?") -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question=question,
        adopted_answer="A.",
        alternatives=(),
        severity=Severity.LOW,
        severity_defaulted=False,
        status="waived",
        owner_spec="052-conditional-landing",
        source_bead="dea-0",
        change_ids=(),
        is_legacy=False,
    )


@pytest.fixture
def project_cwd(temp_dir: Path) -> Path:
    """Chdir into a temp dir with an initialized runway store, mirroring
    the review CLI's ``Path.cwd()`` resolution and the runway path
    convention (``<cwd>/.maverick/runway`` — see
    ``library/actions/runway.py::_get_store``).

    ``RunwayStore.initialize()`` today only touches the ``episodic/``
    files; per contracts/decision-records.md, ``decisions.jsonl`` lives
    directly under the runway root (never inside ``episodic/``, so it
    survives consolidation pruning) and — like the episodic files — is
    meant to be touched by ``initialize()`` once the feature lands. This
    fixture deliberately does NOT pre-create it: its absence after
    ``initialize()`` is part of the red state the implementing agent
    closes.

    Uses the module-level ``temp_dir`` fixture (``tests/conftest.py``),
    which also saves/restores cwd — same convention as sibling CLI tests
    (e.g. ``tests/unit/cli/test_notify_command.py``).
    """
    os.chdir(temp_dir)
    from maverick.runway.store import RunwayStore

    asyncio.run(RunwayStore(temp_dir / ".maverick" / "runway").initialize())
    return temp_dir


def _decisions_path(cwd: Path) -> Path:
    return cwd / ".maverick" / "runway" / "decisions.jsonl"


def _read_decision_lines(cwd: Path) -> list[dict[str, object]]:
    """Read ``decisions.jsonl`` as raw dicts (no ``DecisionRecord`` model
    exists yet — see module docstring)."""
    path = _decisions_path(cwd)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _feedback_path(cwd: Path) -> Path:
    return cwd / ".maverick" / "runway" / "match-feedback.jsonl"


def _read_feedback_lines(cwd: Path) -> list[dict[str, object]]:
    """Read ``match-feedback.jsonl`` as raw dicts (no ``MatchFeedbackRecord``
    round-trip needed here — same convention as ``_read_decision_lines``)."""
    path = _feedback_path(cwd)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _suggestion_state(
    *,
    resolution: str = "Per bead — matches existing scoping.",
    resolution_type: str = "answered",
    source_entry_id: str = "dea-0",
) -> dict[str, str]:
    """Build a ``{KEY_SUGGESTION: <json>}`` state fragment to seed a
    ``BeadDetails.state`` dict with a stored suggestion — mirrors
    ``report_entry_from_details``'s ``KEY_SUGGESTION`` parsing (T027
    consumes ``current_entry.suggestion``, populated this way)."""
    suggestion = Suggestion(
        resolution=resolution,
        resolution_type=resolution_type,
        source_entry_id=source_entry_id,
        source_spec="052-conditional-landing",
        resolved_at="2026-08-01T00:00:00+00:00",
        confidence=0.9,
        computed_at="2026-08-01T00:00:00+00:00",
    )
    return {KEY_SUGGESTION: suggestion_to_json(suggestion)}


class TestAnswerAppendsDecisionRecord:
    def test_single_answer_appends_one_record(self, project_cwd: Path) -> None:
        details = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead."])

        assert result.exit_code == 0, result.output
        mock_answer.assert_awaited_once()

        lines = _read_decision_lines(project_cwd)
        assert len(lines) == 1, (
            "expected exactly one DecisionRecord appended to decisions.jsonl "
            f"after a successful --answer, found {len(lines)}: {lines}"
        )
        record = lines[0]
        assert record["source_entry_id"] == "dea-1"
        assert record["resolution_type"] == "answered"
        assert record["resolution"] == "Per bead."


class TestWaiveAppendsDecisionRecord:
    def test_single_waive_appends_one_record(self, project_cwd: Path) -> None:
        details = _ledger_details(**{KEY_SEVERITY: "low", KEY_STATUS: STATUS_OPEN})
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "no longer applicable"])

        assert result.exit_code == 0, result.output
        mock_waive.assert_awaited_once()

        lines = _read_decision_lines(project_cwd)
        assert len(lines) == 1, (
            "expected exactly one DecisionRecord appended to decisions.jsonl "
            f"after a successful --waive, found {len(lines)}: {lines}"
        )
        record = lines[0]
        assert record["source_entry_id"] == "dea-1"
        assert record["resolution_type"] == "waived"
        assert record["resolution"] == "no longer applicable"
        assert record["resolved_by"] == "alice"


class TestReAnswerAppendsSecondRecord:
    def test_re_answering_appends_history_not_overwrite(self, project_cwd: Path) -> None:
        """Collapse/latest-wins is a read-side concern (data-model.md's
        "Collapse rule" for DecisionRecord) — the write side must never
        overwrite; both resolutions of the same entry must be present in
        the corpus (FR-003)."""
        details = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        runner = CliRunner()

        verify, show = _patch_client(details)
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()),
        ):
            first = runner.invoke(review, ["dea-1", "--answer", "First answer."])
        assert first.exit_code == 0, first.output

        verify, show = _patch_client(details)
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()),
        ):
            second = runner.invoke(review, ["dea-1", "--answer", "Updated answer."])
        assert second.exit_code == 0, second.output

        lines = _read_decision_lines(project_cwd)
        assert len(lines) == 2, (
            "re-answering the same entry must append a SECOND DecisionRecord "
            f"(history preserved, no overwrite), found {len(lines)}: {lines}"
        )
        assert {line["source_entry_id"] for line in lines} == {"dea-1"}
        assert [line["resolution"] for line in lines] == ["First answer.", "Updated answer."]


class TestBulkWaiveAppendsOneRecordPerEntry:
    def test_bulk_waive_appends_one_record_per_waived_entry(self, project_cwd: Path) -> None:
        result_obj = BulkWaiveResult(
            waived=(_waived_record("dea-1", "Q1?"), _waived_record("dea-2", "Q2?")),
            failed={},
        )
        runner = CliRunner()
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch(
                "maverick.assumptions.ledger.bulk_waive",
                new=AsyncMock(return_value=result_obj),
            ),
        ):
            result = runner.invoke(
                review,
                ["--spec", "052-conditional-landing", "--waive", "accepted for MVP"],
            )

        assert result.exit_code == 0, result.output

        lines = _read_decision_lines(project_cwd)
        assert len(lines) == 2, (
            "expected one DecisionRecord per successfully-waived entry from "
            f"bulk waive, found {len(lines)}: {lines}"
        )
        assert {line["source_entry_id"] for line in lines} == {"dea-1", "dea-2"}
        assert all(line["resolution_type"] == "waived" for line in lines)
        assert all(line["resolution"] == "accepted for MVP" for line in lines)


class TestAnswerAppendsMatchFeedbackWhenSuggestionPresent:
    """T023/T027 (User Story 3): resolving an entry that carried a stored
    suggestion also appends a ``MatchFeedbackRecord`` alongside the decision
    record — classified per contracts/decision-records.md's "Decision
    capture points" rule (accepted iff type + normalized text match)."""

    def test_answer_matching_suggested_answer_appends_accepted_feedback(
        self, project_cwd: Path
    ) -> None:
        details = _ledger_details(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_OPEN,
                **_suggestion_state(
                    resolution="Per bead — matches existing scoping.",
                    resolution_type="answered",
                ),
            }
        )
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(
                review, ["dea-1", "--answer", "Per bead — matches existing scoping."]
            )

        assert result.exit_code == 0, result.output
        mock_answer.assert_awaited_once()

        feedback_lines = _read_feedback_lines(project_cwd)
        assert len(feedback_lines) == 1, (
            "expected one MatchFeedbackRecord appended when the resolved "
            f"entry carried a stored suggestion, found {len(feedback_lines)}: "
            f"{feedback_lines}"
        )
        record = feedback_lines[0]
        assert record["outcome"] == "accepted"
        assert record["source_entry_id"] == "dea-0"

    def test_answer_diverging_from_suggested_answer_appends_rejected_feedback(
        self, project_cwd: Path
    ) -> None:
        details = _ledger_details(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_OPEN,
                **_suggestion_state(
                    resolution="Per bead — matches existing scoping.",
                    resolution_type="answered",
                ),
            }
        )
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()),
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Something entirely different."])

        assert result.exit_code == 0, result.output

        feedback_lines = _read_feedback_lines(project_cwd)
        assert len(feedback_lines) == 1
        assert feedback_lines[0]["outcome"] == "rejected"


class TestWaiveAppendsMatchFeedbackWhenSuggestionPresent:
    def test_waive_matching_suggested_waive_appends_accepted_feedback(
        self, project_cwd: Path
    ) -> None:
        details = _ledger_details(
            **{
                KEY_SEVERITY: "low",
                KEY_STATUS: STATUS_OPEN,
                **_suggestion_state(resolution="no longer applicable", resolution_type="waived"),
            }
        )
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "no longer applicable"])

        assert result.exit_code == 0, result.output
        mock_waive.assert_awaited_once()

        feedback_lines = _read_feedback_lines(project_cwd)
        assert len(feedback_lines) == 1
        assert feedback_lines[0]["outcome"] == "accepted"
        assert feedback_lines[0]["source_entry_id"] == "dea-0"

    def test_waive_when_suggestion_was_an_answer_appends_rejected_feedback(
        self, project_cwd: Path
    ) -> None:
        """A waive-type resolution never matches an answer-type suggestion,
        regardless of text — type mismatch always classifies as rejected."""
        details = _ledger_details(
            **{
                KEY_SEVERITY: "low",
                KEY_STATUS: STATUS_OPEN,
                **_suggestion_state(
                    resolution="Per bead — matches existing scoping.",
                    resolution_type="answered",
                ),
            }
        )
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()),
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "no longer applicable"])

        assert result.exit_code == 0, result.output

        feedback_lines = _read_feedback_lines(project_cwd)
        assert len(feedback_lines) == 1
        assert feedback_lines[0]["outcome"] == "rejected"


class TestBulkWaiveAppendsMatchFeedbackPerEntryWithSuggestion:
    """Bulk waive: each waived entry that carried a stored suggestion gets a
    feedback record; entries without one don't.

    ``bulk_waive``'s ``BulkWaiveResult.waived`` carries bare
    ``AssumptionRecord``s (no ``suggestion`` field) — the implementing agent
    is expected to re-fetch each waived record's pre-waive suggestion state
    via ``BeadClient.show`` (the same seam ``_project_after_write`` already
    uses in this module for JSON-mode row projection), so this test mocks
    ``BeadClient.show`` with a per-bead-id ``side_effect`` rather than the
    single canned response ``_patch_client`` provides.
    """

    def test_bulk_waive_appends_feedback_only_for_entries_carrying_a_suggestion(
        self, project_cwd: Path
    ) -> None:
        result_obj = BulkWaiveResult(
            waived=(
                _waived_record("dea-1", "Q1?"),
                _waived_record("dea-2", "Q2?"),
            ),
            failed={},
        )

        details_with_suggestion = _ledger_details(
            "dea-1",
            **{
                KEY_SEVERITY: "low",
                KEY_STATUS: STATUS_OPEN,
                **_suggestion_state(resolution="accepted for MVP", resolution_type="waived"),
            },
        )
        details_without_suggestion = _ledger_details(
            "dea-2", **{KEY_SEVERITY: "low", KEY_STATUS: STATUS_OPEN}
        )

        async def _show(bead_id: str) -> BeadDetails:
            if bead_id == "dea-1":
                return details_with_suggestion
            return details_without_suggestion

        runner = CliRunner()
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.beads.client.BeadClient.show",
                new=AsyncMock(side_effect=_show),
            ),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch(
                "maverick.assumptions.ledger.bulk_waive",
                new=AsyncMock(return_value=result_obj),
            ),
        ):
            result = runner.invoke(
                review,
                ["--spec", "052-conditional-landing", "--waive", "accepted for MVP"],
            )

        assert result.exit_code == 0, result.output

        feedback_lines = _read_feedback_lines(project_cwd)
        assert len(feedback_lines) == 1, (
            "expected exactly one MatchFeedbackRecord — only dea-1 carried a "
            f"stored suggestion — found {len(feedback_lines)}: {feedback_lines}"
        )
        assert feedback_lines[0]["source_entry_id"] == "dea-0"
        assert feedback_lines[0]["outcome"] == "accepted"

        # Both entries still get a DecisionRecord regardless of suggestion
        # presence — feedback capture is additive, never a substitute.
        decision_lines = _read_decision_lines(project_cwd)
        assert {line["source_entry_id"] for line in decision_lines} == {"dea-1", "dea-2"}


class TestNoFeedbackWhenNoSuggestionStored:
    """Regression guard: an entry without a stored suggestion must never
    produce a feedback record — only the decision record. This already
    holds given the pre-T027 wiring (no feedback capture exists at all
    yet); asserted explicitly so it can't silently regress once T027 lands.
    """

    def test_answer_without_stored_suggestion_appends_no_feedback_record(
        self, project_cwd: Path
    ) -> None:
        details = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()),
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead."])

        assert result.exit_code == 0, result.output
        assert _read_decision_lines(project_cwd), "the decision record must still be appended"
        feedback_lines = _read_feedback_lines(project_cwd)
        assert feedback_lines == [], (
            "no stored suggestion on the entry -> no MatchFeedbackRecord should "
            f"be appended, found: {feedback_lines}"
        )

    def test_waive_without_stored_suggestion_appends_no_feedback_record(
        self, project_cwd: Path
    ) -> None:
        details = _ledger_details(**{KEY_SEVERITY: "low", KEY_STATUS: STATUS_OPEN})
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()),
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "no longer applicable"])

        assert result.exit_code == 0, result.output
        assert _read_decision_lines(project_cwd), "the decision record must still be appended"
        feedback_lines = _read_feedback_lines(project_cwd)
        assert feedback_lines == [], (
            "no stored suggestion on the entry -> no MatchFeedbackRecord should "
            f"be appended, found: {feedback_lines}"
        )


class TestDecisionCaptureFailureIsNonBlocking:
    """FR-004: decision capture is best-effort. A failed write must warn,
    never block or fail the review action — the ledger write already
    succeeded and is the source of truth."""

    def test_unwritable_decisions_store_warns_but_answer_still_succeeds(
        self, project_cwd: Path
    ) -> None:
        # Force any future write to decisions.jsonl to fail: make the path
        # a directory instead of a file, so an `open(path, "a")` raises
        # IsADirectoryError regardless of how the store implements the append.
        # `project_cwd`'s initialize() call already touched decisions.jsonl
        # as an empty file (T007) — remove it first so `mkdir()` can claim
        # the path.
        decisions_path = _decisions_path(project_cwd)
        decisions_path.unlink(missing_ok=True)
        decisions_path.mkdir(parents=True)

        details = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead."])

        # The ledger write is the source of truth; a decision-capture
        # failure must never block or fail the review action itself.
        assert result.exit_code == 0, result.output
        mock_answer.assert_awaited_once()
        assert "Bead dea-1 answered and closed" in result.output

        # ...but it must be visibly reported, not silently swallowed.
        assert "Warning" in result.output, (
            "expected a `[yellow]Warning:[/]`-style message when decision "
            f"capture fails; got output:\n{result.output!r}"
        )


class TestNotifyAutoWaiveExcludedFromCorpus:
    """FR-005 / research.md R6: the scheduler's auto-waive path is
    structurally excluded from the decision corpus — ``notify``'s
    ``_execute_auto_waives`` never touches ``entry_actions.py``'s capture
    helpers, unlike ``maverick review`` (human surface).

    Unlike the tests above, this one is a *guard*, not a red-state probe:
    it holds both before and after the capture wiring lands (that's the
    point — it pins down that the machine path must stay excluded even
    once decision capture exists elsewhere in the codebase).
    """

    def test_execute_auto_waives_writes_no_decision_record(self, project_cwd: Path) -> None:
        from maverick.assumptions.schedule.models import AutoWaiveDecision
        from maverick.beads.client import BeadClient
        from maverick.cli.commands.notify import _execute_auto_waives

        decision = AutoWaiveDecision(
            entry_id="dea-lo",
            reason_text="auto-waived by schedule policy after 168h: stale, accepted risk",
        )
        client = BeadClient(cwd=project_cwd)

        async def _fake_ledger_waive(
            client: object, *, bead_id: str, reason: str, waived_by: str
        ) -> None:
            return None

        with patch("maverick.cli.commands.notify.ledger_waive", new=_fake_ledger_waive):
            succeeded = asyncio.run(_execute_auto_waives(client=client, decisions=(decision,)))

        assert succeeded == [decision]

        lines = _read_decision_lines(project_cwd)
        assert lines == [], (
            "scheduler auto-waive (`waived_by='maverick-scheduler'`) must never "
            f"write to the human decision corpus (FR-005); found: {lines}"
        )


class TestAlreadyResolvedBypassForAutoResolvedEntries:
    """T029 (User Story 4, FR-020): ``maverick review <id> --answer`` on an
    entry the auto-resolution policy already waived
    (``assumption_auto_resolved=true``) bypasses the ``ALREADY_RESOLVED``
    pre-check (``entry_actions.py``'s ``_review_ledger_entry``, ~line 226)
    and proceeds to answer normally. A plain human-waived entry
    (``auto_resolved`` false/absent) must still be refused — asserted here
    as a companion regression guard.

    Not yet implemented as of this task: the pre-check currently refuses
    *any* ``STATUS_WAIVED`` entry regardless of ``KEY_AUTO_RESOLVED`` — the
    bypass test below fails today because the refusal still fires (exit
    code != 0, ``ledger.answer`` never called) rather than proceeding.
    """

    def test_answer_bypasses_refusal_when_entry_was_auto_resolved(self, project_cwd: Path) -> None:
        from maverick.assumptions.models import KEY_AUTO_RESOLVED

        details = _ledger_details(
            **{
                KEY_SEVERITY: "low",
                KEY_STATUS: "waived",
                KEY_AUTO_RESOLVED: "true",
                **_suggestion_state(
                    resolution="Per bead — matches existing scoping.",
                    resolution_type="answered",
                ),
            }
        )
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(
                review, ["dea-1", "--answer", "Per bead — matches existing scoping."]
            )

        assert result.exit_code == 0, result.output
        mock_answer.assert_awaited_once()
        assert "already waived" not in result.output.lower()
        assert "Bead dea-1 answered and closed" in result.output

    def test_answer_still_refused_when_entry_was_human_waived(self, project_cwd: Path) -> None:
        """Regression guard: a plain human-waived entry (no
        ``assumption_auto_resolved``) keeps the existing already-resolved
        refusal — the bypass above must be scoped to auto-resolved entries
        only, never to waived entries generally."""
        details = _ledger_details(**{KEY_SEVERITY: "low", KEY_STATUS: "waived"})
        verify, show = _patch_client(details)
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead."])

        assert result.exit_code != 0
        mock_answer.assert_not_awaited()
        assert "already waived" in result.output.lower()


class TestHumanOverrideClearsAutoResolvedStamp:
    """A human resolving an auto-resolved entry takes ownership of it, so
    ``assumption_auto_resolved`` must come back off the bead.

    Two things break if the stamp survives: reports keep annotating a
    human-resolved row ``auto-resolved`` (misattributing the decision), and
    the already-resolved refusal — which the stamp deliberately bypasses —
    stays disabled forever, so the entry can be silently re-resolved any
    number of times.
    """

    def _auto_resolved_details(self):  # noqa: ANN202
        from maverick.assumptions.models import KEY_AUTO_RESOLVED

        return _ledger_details(
            **{
                KEY_SEVERITY: "low",
                KEY_STATUS: "waived",
                KEY_AUTO_RESOLVED: "true",
                **_suggestion_state(
                    resolution="Per bead — matches existing scoping.",
                    resolution_type="answered",
                ),
            }
        )

    def test_answer_unstamps_auto_resolved(self, project_cwd: Path) -> None:
        from maverick.assumptions.models import KEY_AUTO_RESOLVED

        verify, show = _patch_client(self._auto_resolved_details())
        mock_set_state = AsyncMock()
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()),
            patch("maverick.beads.client.BeadClient.set_state", new=mock_set_state),
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "A different answer entirely."])

        assert result.exit_code == 0, result.output
        written: dict[str, str] = {}
        for call in mock_set_state.await_args_list:
            state = call.args[1] if len(call.args) > 1 else call.kwargs.get("state", {})
            written.update(state)
        # "false", not cleared: bd rejects empty state values, and readers
        # compare against "true".
        assert written.get(KEY_AUTO_RESOLVED) == "false"

    def test_human_waive_of_non_auto_resolved_entry_never_writes_the_key(
        self, project_cwd: Path
    ) -> None:
        """Scoped to overrides — an ordinary open entry's resolution must
        not start stamping ``assumption_auto_resolved`` at all."""
        from maverick.assumptions.models import KEY_AUTO_RESOLVED

        verify, show = _patch_client(_ledger_details(**{KEY_SEVERITY: "low"}))
        mock_set_state = AsyncMock()
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()),
            patch("maverick.beads.client.BeadClient.set_state", new=mock_set_state),
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "Accepted risk."])

        assert result.exit_code == 0, result.output
        for call in mock_set_state.await_args_list:
            state = call.args[1] if len(call.args) > 1 else call.kwargs.get("state", {})
            assert KEY_AUTO_RESOLVED not in state
