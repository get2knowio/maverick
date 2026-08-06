"""Tests for DecisionRecord storage on RunwayStore (spec 055, US1, T004).

Covers:
- DecisionRecord to_dict/from_dict round-trip.
- RunwayStore.append_decision / get_decisions (append-only, filterable).
- RunwayStore.initialize() touching both decisions.jsonl and
  match-feedback.jsonl at the store root (NOT under episodic/).
- Malformed JSONL lines in decisions.jsonl are skipped, not raised.
- Regression: consolidate_runway() never touches decisions.jsonl or
  match-feedback.jsonl (outside episodic/ by design, never pruned).

These tests are expected to FAIL right now: DecisionRecord does not yet
exist in maverick.runway.models, and append_decision/get_decisions do not
yet exist on RunwayStore. Production code lands in a follow-up change.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.runway.models import DecisionRecord, MatchFeedbackRecord
from maverick.runway.store import RunwayStore

pytestmark = pytest.mark.asyncio


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


def _make_decision(
    *,
    source_entry_id: str = "mv-142",
    question: str = "Should retries use exponential backoff?",
    normalized_question: str = "should retries use exponential backoff",
    adopted_answer: str = "Yes, tenacity default",
    resolution_type: str = "answered",
    resolution: str = "Yes — AsyncRetrying, 3 attempts",
    severity: str = "medium",
    owner_spec: str = "052-conditional-landing",
    resolved_by: str = "Paul O'Fallon",
    resolved_at: str = "2026-08-06T14:03:22+00:00",
) -> DecisionRecord:
    return DecisionRecord(
        source_entry_id=source_entry_id,
        question=question,
        normalized_question=normalized_question,
        adopted_answer=adopted_answer,
        resolution_type=resolution_type,
        resolution=resolution,
        severity=severity,
        owner_spec=owner_spec,
        resolved_by=resolved_by,
        resolved_at=resolved_at,
    )


@pytest.fixture
def sample_decision_record() -> DecisionRecord:
    """A DecisionRecord matching the example line in
    specs/055-learned-assumption-resolution/contracts/decision-records.md.
    """
    return _make_decision()


def _make_match_feedback(
    *,
    normalized_question: str = "should retries use exponential backoff",
    source_entry_id: str = "mv-142",
    outcome: str = "rejected",
    recorded_at: str = "2026-08-07T09:15:02+00:00",
) -> MatchFeedbackRecord:
    return MatchFeedbackRecord(
        normalized_question=normalized_question,
        source_entry_id=source_entry_id,
        outcome=outcome,
        recorded_at=recorded_at,
    )


@pytest.fixture
def sample_match_feedback_record() -> MatchFeedbackRecord:
    """A MatchFeedbackRecord matching the example line in
    specs/055-learned-assumption-resolution/contracts/decision-records.md.
    """
    return _make_match_feedback()


# -----------------------------------------------------------------------------
# DecisionRecord model
# -----------------------------------------------------------------------------


class TestDecisionRecordRoundTrip:
    """DecisionRecord.to_dict()/from_dict() round-trip, per data-model.md."""

    def test_to_dict_contains_all_fields(self, sample_decision_record: DecisionRecord) -> None:
        data = sample_decision_record.to_dict()
        assert data == {
            "source_entry_id": "mv-142",
            "question": "Should retries use exponential backoff?",
            "normalized_question": "should retries use exponential backoff",
            "adopted_answer": "Yes, tenacity default",
            "resolution_type": "answered",
            "resolution": "Yes — AsyncRetrying, 3 attempts",
            "severity": "medium",
            "owner_spec": "052-conditional-landing",
            "resolved_by": "Paul O'Fallon",
            "resolved_at": "2026-08-06T14:03:22+00:00",
        }

    def test_from_dict_round_trip(self, sample_decision_record: DecisionRecord) -> None:
        data = sample_decision_record.to_dict()
        restored = DecisionRecord.from_dict(data)
        assert restored == sample_decision_record
        assert restored.to_dict() == data

    def test_resolution_type_waived(self) -> None:
        record = _make_decision(resolution_type="waived", resolution="Accepted risk, low severity")
        assert record.resolution_type == "waived"
        restored = DecisionRecord.from_dict(record.to_dict())
        assert restored.resolution_type == "waived"

    def test_is_frozen(self, sample_decision_record: DecisionRecord) -> None:
        with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError on frozen model
            sample_decision_record.source_entry_id = "changed"  # type: ignore[misc]

    def test_json_line_matches_contract_example(
        self, sample_decision_record: DecisionRecord
    ) -> None:
        """The serialized line should be parseable back through the same shape
        as the contract's example JSON line.
        """
        line = json.dumps(sample_decision_record.to_dict(), ensure_ascii=False)
        reparsed = json.loads(line)
        assert DecisionRecord.from_dict(reparsed) == sample_decision_record


# -----------------------------------------------------------------------------
# RunwayStore.append_decision / get_decisions
# -----------------------------------------------------------------------------


class TestAppendAndGetDecisions:
    async def test_append_then_get_returns_record(
        self, initialized_store: RunwayStore, sample_decision_record: DecisionRecord
    ) -> None:
        await initialized_store.append_decision(sample_decision_record)
        decisions = await initialized_store.get_decisions()
        assert len(decisions) == 1
        assert decisions[0] == sample_decision_record

    async def test_append_is_append_only_jsonl(
        self, initialized_store: RunwayStore, sample_decision_record: DecisionRecord
    ) -> None:
        await initialized_store.append_decision(sample_decision_record)
        await initialized_store.append_decision(sample_decision_record)
        decisions_path = initialized_store.path / "decisions.jsonl"
        lines = [
            line
            for line in decisions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 2

    async def test_get_decisions_no_filter_returns_all(
        self, initialized_store: RunwayStore
    ) -> None:
        d1 = _make_decision(source_entry_id="mv-001")
        d2 = _make_decision(source_entry_id="mv-002")
        d3 = _make_decision(source_entry_id="mv-003")
        for d in (d1, d2, d3):
            await initialized_store.append_decision(d)

        results = await initialized_store.get_decisions()
        assert len(results) == 3
        assert {r.source_entry_id for r in results} == {"mv-001", "mv-002", "mv-003"}

    async def test_get_decisions_filters_by_source_entry_id(
        self, initialized_store: RunwayStore
    ) -> None:
        d1 = _make_decision(source_entry_id="mv-001", resolution="first")
        d2 = _make_decision(source_entry_id="mv-002", resolution="second")
        d3 = _make_decision(source_entry_id="mv-001", resolution="first-updated")
        for d in (d1, d2, d3):
            await initialized_store.append_decision(d)

        results = await initialized_store.get_decisions(source_entry_id="mv-001")
        assert len(results) == 2
        assert all(r.source_entry_id == "mv-001" for r in results)
        assert [r.resolution for r in results] == ["first", "first-updated"]

    async def test_get_decisions_filter_no_match_returns_empty(
        self, initialized_store: RunwayStore, sample_decision_record: DecisionRecord
    ) -> None:
        await initialized_store.append_decision(sample_decision_record)
        results = await initialized_store.get_decisions(source_entry_id="does-not-exist")
        assert results == []

    async def test_get_decisions_empty_store_returns_empty_list(
        self, initialized_store: RunwayStore
    ) -> None:
        results = await initialized_store.get_decisions()
        assert results == []


# -----------------------------------------------------------------------------
# initialize() touches both new files at the store root
# -----------------------------------------------------------------------------


class TestInitializeTouchesDecisionFiles:
    async def test_initialize_creates_decisions_and_match_feedback_files(
        self, runway_path: Path
    ) -> None:
        store = RunwayStore(runway_path)
        assert not (runway_path / "decisions.jsonl").exists()
        assert not (runway_path / "match-feedback.jsonl").exists()

        await store.initialize()

        decisions_path = runway_path / "decisions.jsonl"
        feedback_path = runway_path / "match-feedback.jsonl"
        assert decisions_path.is_file()
        assert feedback_path.is_file()

        # Outside episodic/ by design (contracts/decision-records.md) —
        # never pruned by consolidation.
        assert decisions_path.parent == runway_path
        assert feedback_path.parent == runway_path
        assert not (runway_path / "episodic" / "decisions.jsonl").exists()
        assert not (runway_path / "episodic" / "match-feedback.jsonl").exists()

    async def test_initialize_idempotent_does_not_clobber_existing_content(
        self, initialized_store: RunwayStore, sample_decision_record: DecisionRecord
    ) -> None:
        await initialized_store.append_decision(sample_decision_record)
        # Re-running initialize() must not truncate/overwrite existing data.
        await initialized_store.initialize()
        decisions = await initialized_store.get_decisions()
        assert len(decisions) == 1


# -----------------------------------------------------------------------------
# Malformed JSONL tolerance
# -----------------------------------------------------------------------------


class TestMalformedDecisionLinesSkipped:
    async def test_corrupt_line_skipped_not_raised(
        self, initialized_store: RunwayStore, sample_decision_record: DecisionRecord
    ) -> None:
        decisions_path = initialized_store.path / "decisions.jsonl"
        # Write a corrupt line directly, mirroring existing _read_jsonl tolerance.
        decisions_path.write_text("{not valid json,,,\n", encoding="utf-8")

        await initialized_store.append_decision(sample_decision_record)

        results = await initialized_store.get_decisions()
        assert len(results) == 1
        assert results[0] == sample_decision_record

    async def test_corrupt_line_logs_warning(
        self, initialized_store: RunwayStore, sample_decision_record: DecisionRecord
    ) -> None:
        decisions_path = initialized_store.path / "decisions.jsonl"
        decisions_path.write_text("{totally broken\n", encoding="utf-8")
        await initialized_store.append_decision(sample_decision_record)

        with patch("maverick.runway.store.logger") as mock_logger:
            results = await initialized_store.get_decisions()

        assert len(results) == 1
        assert mock_logger.warning.called


# -----------------------------------------------------------------------------
# MatchFeedbackRecord model (spec 055, US3, T023)
# -----------------------------------------------------------------------------


class TestMatchFeedbackRecordRoundTrip:
    """MatchFeedbackRecord.to_dict()/from_dict() round-trip, per data-model.md."""

    def test_to_dict_contains_all_fields(
        self, sample_match_feedback_record: MatchFeedbackRecord
    ) -> None:
        data = sample_match_feedback_record.to_dict()
        assert data == {
            "normalized_question": "should retries use exponential backoff",
            "source_entry_id": "mv-142",
            "outcome": "rejected",
            "recorded_at": "2026-08-07T09:15:02+00:00",
        }

    def test_from_dict_round_trip(self, sample_match_feedback_record: MatchFeedbackRecord) -> None:
        data = sample_match_feedback_record.to_dict()
        restored = MatchFeedbackRecord.from_dict(data)
        assert restored == sample_match_feedback_record
        assert restored.to_dict() == data

    def test_outcome_accepted(self) -> None:
        record = _make_match_feedback(outcome="accepted")
        assert record.outcome == "accepted"
        restored = MatchFeedbackRecord.from_dict(record.to_dict())
        assert restored.outcome == "accepted"

    def test_is_frozen(self, sample_match_feedback_record: MatchFeedbackRecord) -> None:
        with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError on frozen model
            sample_match_feedback_record.source_entry_id = "changed"  # type: ignore[misc]

    def test_json_line_matches_contract_example(
        self, sample_match_feedback_record: MatchFeedbackRecord
    ) -> None:
        """The serialized line should be parseable back through the same shape
        as the contract's example JSON line.
        """
        line = json.dumps(sample_match_feedback_record.to_dict(), ensure_ascii=False)
        reparsed = json.loads(line)
        assert MatchFeedbackRecord.from_dict(reparsed) == sample_match_feedback_record


# -----------------------------------------------------------------------------
# RunwayStore.append_match_feedback / get_match_feedback (spec 055, US3, T023)
# -----------------------------------------------------------------------------


class TestAppendAndGetMatchFeedback:
    async def test_append_then_get_returns_record(
        self,
        initialized_store: RunwayStore,
        sample_match_feedback_record: MatchFeedbackRecord,
    ) -> None:
        await initialized_store.append_match_feedback(sample_match_feedback_record)
        results = await initialized_store.get_match_feedback()
        assert len(results) == 1
        assert results[0] == sample_match_feedback_record

    async def test_append_is_append_only_jsonl(
        self,
        initialized_store: RunwayStore,
        sample_match_feedback_record: MatchFeedbackRecord,
    ) -> None:
        await initialized_store.append_match_feedback(sample_match_feedback_record)
        await initialized_store.append_match_feedback(sample_match_feedback_record)
        feedback_path = initialized_store.path / "match-feedback.jsonl"
        lines = [
            line for line in feedback_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        assert len(lines) == 2

    async def test_get_match_feedback_returns_all_records_no_filter(
        self, initialized_store: RunwayStore
    ) -> None:
        f1 = _make_match_feedback(source_entry_id="mv-001", outcome="rejected")
        f2 = _make_match_feedback(source_entry_id="mv-002", outcome="accepted")
        f3 = _make_match_feedback(source_entry_id="mv-003", outcome="rejected")
        for f in (f1, f2, f3):
            await initialized_store.append_match_feedback(f)

        results = await initialized_store.get_match_feedback()
        assert len(results) == 3
        assert {r.source_entry_id for r in results} == {"mv-001", "mv-002", "mv-003"}

    async def test_get_match_feedback_returns_records_in_append_order(
        self, initialized_store: RunwayStore
    ) -> None:
        f1 = _make_match_feedback(source_entry_id="mv-001", outcome="rejected")
        f2 = _make_match_feedback(source_entry_id="mv-001", outcome="accepted")
        for f in (f1, f2):
            await initialized_store.append_match_feedback(f)

        results = await initialized_store.get_match_feedback()
        assert [r.outcome for r in results] == ["rejected", "accepted"]

    async def test_get_match_feedback_empty_store_returns_empty_list(
        self, initialized_store: RunwayStore
    ) -> None:
        results = await initialized_store.get_match_feedback()
        assert results == []


class TestMalformedMatchFeedbackLinesSkipped:
    async def test_corrupt_line_skipped_not_raised(
        self,
        initialized_store: RunwayStore,
        sample_match_feedback_record: MatchFeedbackRecord,
    ) -> None:
        feedback_path = initialized_store.path / "match-feedback.jsonl"
        feedback_path.write_text("{not valid json,,,\n", encoding="utf-8")

        await initialized_store.append_match_feedback(sample_match_feedback_record)

        results = await initialized_store.get_match_feedback()
        assert len(results) == 1
        assert results[0] == sample_match_feedback_record

    async def test_corrupt_line_logs_warning(
        self,
        initialized_store: RunwayStore,
        sample_match_feedback_record: MatchFeedbackRecord,
    ) -> None:
        feedback_path = initialized_store.path / "match-feedback.jsonl"
        feedback_path.write_text("{totally broken\n", encoding="utf-8")
        await initialized_store.append_match_feedback(sample_match_feedback_record)

        with patch("maverick.runway.store.logger") as mock_logger:
            results = await initialized_store.get_match_feedback()

        assert len(results) == 1
        assert mock_logger.warning.called


# -----------------------------------------------------------------------------
# Regression: consolidation must never touch decisions.jsonl / match-feedback.jsonl
# -----------------------------------------------------------------------------


@pytest.fixture()
def runway_dir(tmp_path: Path) -> Path:
    """Create an initialized runway directory structure (mirrors
    tests/unit/library/actions/test_consolidation.py's fixture).
    """
    runway_path = tmp_path / ".maverick" / "runway"
    episodic = runway_path / "episodic"
    semantic = runway_path / "semantic"
    episodic.mkdir(parents=True)
    semantic.mkdir(parents=True)

    (runway_path / "index.json").write_text(
        json.dumps({"version": 1, "last_consolidated": "", "episodic_counts": {}})
    )

    (episodic / "bead-outcomes.jsonl").touch()
    (episodic / "review-findings.jsonl").touch()
    (episodic / "fix-attempts.jsonl").touch()

    return tmp_path


class TestConsolidationLeavesDecisionFilesUntouched:
    """Regression test binding to the real consolidate_runway() action.

    decisions.jsonl and match-feedback.jsonl live outside episodic/ by
    design (contracts/decision-records.md: "Never" pruned by
    consolidation) — this must remain byte-identical across a
    consolidation run that actually prunes other episodic records.
    """

    async def test_consolidate_runway_does_not_modify_decision_files(
        self, runway_dir: Path
    ) -> None:
        from datetime import datetime, timedelta

        from maverick.library.actions.consolidation import consolidate_runway

        runway_path = runway_dir / ".maverick" / "runway"
        store = RunwayStore(runway_path)

        # Populate decisions + match-feedback files with real content.
        decision = _make_decision(source_entry_id="mv-999")
        await store.append_decision(decision)

        feedback_path = runway_path / "match-feedback.jsonl"
        feedback_line = (
            json.dumps(
                {
                    "normalized_question": "should retries use exponential backoff",
                    "source_entry_id": "mv-999",
                    "outcome": "rejected",
                    "recorded_at": "2026-08-07T09:15:02+00:00",
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        feedback_path.write_text(feedback_line, encoding="utf-8")

        decisions_before = (runway_path / "decisions.jsonl").read_bytes()
        feedback_before = feedback_path.read_bytes()

        # Force real pruning: an old bead outcome ages out of episodic/.
        old_ts = (datetime.now() - timedelta(days=120)).isoformat()
        (runway_path / "episodic" / "bead-outcomes.jsonl").write_text(
            json.dumps({"bead_id": "old-1", "epic_id": "e1", "timestamp": old_ts}) + "\n"
        )

        with patch(
            "maverick.library.actions.consolidation._synthesize_summary",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await consolidate_runway(cwd=runway_dir, max_age_days=90)

        assert result.success is True
        assert result.skipped is False

        decisions_after = (runway_path / "decisions.jsonl").read_bytes()
        feedback_after = feedback_path.read_bytes()

        assert decisions_after == decisions_before
        assert feedback_after == feedback_before
