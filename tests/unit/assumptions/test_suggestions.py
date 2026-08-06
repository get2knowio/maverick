"""Tests for learned-resolution suggestion evaluation and persistence.

Covers spec 055-learned-assumption-resolution, User Story 2 (T011): matching
a newly recorded/listed assumption entry against the decision corpus, and
persisting/back-filling the result on the bead as ``assumption_suggestion``.

Target functions under test (not yet implemented as of this task — see
research.md R5 for the normative signatures):

    def evaluate_suggestion(
        record: AssumptionReportEntry,
        corpus: list[DecisionRecord],
        feedback: list[MatchFeedbackRecord],
    ) -> Suggestion | None

    async def attach_suggestions(
        client: BeadClient,
        store: RunwayStore,
        records: list[AssumptionReportEntry],
    ) -> None

    async def backfill_suggestions(
        client: BeadClient,
        store: RunwayStore,
        entries: list[AssumptionReportEntry],
    ) -> list[AssumptionReportEntry]

``feedback`` is exercised only with an empty list here (US3/T023 owns
feedback-penalty behavior; the parameter exists from T018 with an empty
default so US2 behavior is unchanged until feedback records exist).

See:
- specs/055-learned-assumption-resolution/research.md R5, R11, R12, R13
- specs/055-learned-assumption-resolution/data-model.md (Suggestion, invariants 1-4)
- specs/055-learned-assumption-resolution/contracts/decision-records.md

``AssumptionReportEntry.suggestion``/``.auto_resolved`` (T015) and
``Suggestion``/``KEY_SUGGESTION``/``KEY_AUTO_RESOLVED`` (T015/T017) have not
landed yet as of this task — constructing test fixtures against them, and
importing ``evaluate_suggestion``/``attach_suggestions``/
``backfill_suggestions`` (T016/T018), are expected to fail at collection or
construction time. That failure IS the red state this test file asserts;
T015-T018 land together and make this file pass.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.matching import PRESENTATION_THRESHOLD, normalize_question
from maverick.assumptions.models import (
    STATUS_OPEN,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
    Suggestion,
    suggestion_to_json,
)
from maverick.assumptions.suggestions import (
    _MAX_SUGGESTION_JSON_LENGTH,
    attach_suggestions,
    backfill_suggestions,
    evaluate_suggestion,
)
from maverick.beads.client import BeadClient
from maverick.runway.models import DecisionRecord, MatchFeedbackRecord
from maverick.runway.store import RunwayStore

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _record(
    bead_id: str,
    question: str,
    *,
    severity: Severity = Severity.LOW,
    owner_spec: str = "052-conditional-landing",
) -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question=question,
        adopted_answer="Some adopted answer to keep working.",
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status=STATUS_OPEN,
        owner_spec=owner_spec,
        source_bead="src-bead-1",
        change_ids=(),
        is_legacy=False,
    )


def _entry(
    bead_id: str,
    question: str,
    *,
    severity: Severity = Severity.LOW,
    owner_spec: str = "052-conditional-landing",
    suggestion: Suggestion | None = None,
    auto_resolved: bool = False,
) -> AssumptionReportEntry:
    return AssumptionReportEntry(
        record=_record(bead_id, question, severity=severity, owner_spec=owner_spec),
        final_answer=None,
        waived_by=None,
        waived_at=None,
        waive_reason=None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=False,
        suggestion=suggestion,
        auto_resolved=auto_resolved,
    )


def _decision(
    source_entry_id: str,
    question: str,
    *,
    resolution: str = "Yes, that's correct.",
    resolution_type: str = "answered",
    resolved_at: str = "2026-08-01T00:00:00+00:00",
    owner_spec: str = "052-conditional-landing",
) -> DecisionRecord:
    return DecisionRecord(
        source_entry_id=source_entry_id,
        question=question,
        normalized_question=normalize_question(question),
        adopted_answer="What the agent had adopted.",
        resolution_type=resolution_type,  # type: ignore[arg-type]
        resolution=resolution,
        severity="medium",
        owner_spec=owner_spec,
        resolved_by="Test User",
        resolved_at=resolved_at,
    )


# ---------------------------------------------------------------------------
# evaluate_suggestion
# ---------------------------------------------------------------------------


class TestEvaluateSuggestionBelowThreshold:
    def test_empty_corpus_returns_none(self) -> None:
        entry = _entry("mv-1", "Should retries use exponential backoff?")
        assert evaluate_suggestion(entry, [], feedback=[]) is None

    def test_low_similarity_candidate_returns_none(self) -> None:
        entry = _entry("mv-1", "Should retries use exponential backoff for network calls?")
        corpus = [_decision("mv-2", "Where should database backups be archived indefinitely?")]
        assert evaluate_suggestion(entry, corpus, feedback=[]) is None


class TestEvaluateSuggestionSelfMatchExcluded:
    def test_self_match_never_suggested_even_when_identical(self) -> None:
        # R12: an entry re-opened/re-answered must never match the decision
        # record produced by its own earlier resolution.
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        corpus = [_decision("mv-1", question)]  # source_entry_id == entry.bead_id
        assert evaluate_suggestion(entry, corpus, feedback=[]) is None

    def test_self_match_excluded_leaving_lower_candidates_below_threshold(self) -> None:
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        corpus = [
            _decision("mv-1", question),  # self-match: excluded regardless of score
            _decision("mv-2", "Where should database backups be archived indefinitely?"),
        ]
        assert evaluate_suggestion(entry, corpus, feedback=[]) is None


class TestEvaluateSuggestionMatch:
    def test_match_returns_suggestion_with_expected_shape(self) -> None:
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        decision = _decision(
            "mv-2",
            question,
            resolution="Yes, use exponential backoff via tenacity.",
            resolution_type="answered",
            resolved_at="2026-08-01T00:00:00+00:00",
            owner_spec="052-conditional-landing",
        )

        result = evaluate_suggestion(entry, [decision], feedback=[])

        # Exactly one suggestion is ever returned — never a list.
        assert isinstance(result, Suggestion)
        assert result.source_entry_id == "mv-2"
        assert result.resolution == "Yes, use exponential backoff via tenacity."
        assert result.resolution_type == "answered"
        assert result.source_spec == "052-conditional-landing"
        assert result.resolved_at == "2026-08-01T00:00:00+00:00"
        assert result.confidence >= PRESENTATION_THRESHOLD


class TestEvaluateSuggestionCollapse:
    def test_only_latest_version_participates_in_matching(self) -> None:
        # Two DecisionRecords for the same source_entry_id (a re-answered
        # decision). The EARLIER version is a near-perfect textual match
        # (score 1.0) with an "old" resolution; the LATER version has
        # slightly different phrasing (still >= threshold) with a "new"
        # resolution. Without collapse, select_best would pick the earlier,
        # higher-scoring record — this test fails unless only the latest
        # version participates.
        question = "Should retries use exponential backoff for network calls?"
        entry = _entry("mv-1", question)
        earlier = _decision(
            "mv-2",
            question,  # exact match -> base score 1.0
            resolution="Old answer: fixed delay retries.",
            resolved_at="2026-01-01T00:00:00+00:00",
        )
        later = _decision(
            "mv-2",
            "Should retries use exponential backoff for network requests?",
            resolution="New answer: exponential backoff via tenacity.",
            resolved_at="2026-06-01T00:00:00+00:00",
        )

        result = evaluate_suggestion(entry, [earlier, later], feedback=[])

        assert result is not None
        assert result.source_entry_id == "mv-2"
        assert result.resolution == "New answer: exponential backoff via tenacity."
        assert result.resolved_at == "2026-06-01T00:00:00+00:00"


class TestEvaluateSuggestionTieBreak:
    def test_tie_breaks_on_resolved_at_descending(self) -> None:
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        older = _decision("mv-2", question, resolved_at="2026-01-01T00:00:00+00:00")
        newer = _decision("mv-3", question, resolved_at="2026-06-01T00:00:00+00:00")

        result = evaluate_suggestion(entry, [older, newer], feedback=[])

        assert result is not None
        assert result.source_entry_id == "mv-3"
        assert result.resolved_at == "2026-06-01T00:00:00+00:00"

    def test_tie_breaks_on_source_entry_id_ascending(self) -> None:
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        same_time = "2026-06-01T00:00:00+00:00"
        candidates = [
            _decision("mv-99", question, resolved_at=same_time),
            _decision("mv-2", question, resolved_at=same_time),
            _decision("mv-42", question, resolved_at=same_time),
        ]

        result = evaluate_suggestion(entry, candidates, feedback=[])

        assert result is not None
        assert result.source_entry_id == "mv-2"


class TestEvaluateSuggestionPerformance:
    def test_scales_to_500_records_under_one_second(self) -> None:
        # SC-006: a single evaluation against a ~500-record corpus must
        # complete well under one second.
        entry = _entry("mv-1", "Should retries use exponential backoff for network calls?")
        corpus = [
            _decision(
                f"mv-corpus-{i}",
                f"Should component {i} use retry strategy variant {i} "
                "for outbound network calls to a downstream service?",
                resolved_at=f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00",
            )
            for i in range(500)
        ]

        start = time.perf_counter()
        evaluate_suggestion(entry, corpus, feedback=[])
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0


# ---------------------------------------------------------------------------
# classify_feedback / record_feedback (spec 055, US3, T023)
#
# ``classify_feedback``/``record_feedback`` do not exist yet in
# ``maverick.assumptions.suggestions`` as of this task (T026 adds them) — the
# module-level imports above deliberately do NOT name them, so a missing
# symbol doesn't break collection of the rest of this file (evaluate_suggestion
# / attach_suggestions / backfill_suggestions tests, already green, must keep
# passing). Each test below imports the two functions locally instead; until
# T026 lands, every test in these classes fails with an ImportError, which IS
# the red state this task asserts.
# ---------------------------------------------------------------------------


def _suggestion(
    *,
    resolution: str = "Yes, use exponential backoff via tenacity.",
    resolution_type: str = "answered",
    source_entry_id: str = "mv-2",
    source_spec: str = "052-conditional-landing",
    resolved_at: str = "2026-08-01T00:00:00+00:00",
    confidence: float = 0.9,
) -> Suggestion:
    return Suggestion(
        resolution=resolution,
        resolution_type=resolution_type,
        source_entry_id=source_entry_id,
        source_spec=source_spec,
        resolved_at=resolved_at,
        confidence=confidence,
        computed_at="2026-08-01T00:00:00+00:00",
    )


class TestClassifyFeedback:
    """classify_feedback(entry, suggestion, *, resolution_type, resolution).

    Per contracts/decision-records.md "Decision capture points": accepted
    iff resolution_type matches the suggestion's AND normalized resolution
    text matches the suggestion's normalized resolution text; anything else
    (different text, or a type mismatch regardless of text) is rejected.
    """

    def test_same_type_same_text_is_accepted(self) -> None:
        from maverick.assumptions.suggestions import classify_feedback

        suggestion = _suggestion(
            resolution="Yes, use exponential backoff via tenacity.",
            resolution_type="answered",
        )
        entry = _entry("mv-1", "Should retries use exponential backoff?", suggestion=suggestion)

        result = classify_feedback(
            entry,
            suggestion,
            resolution_type="answered",
            resolution="Yes, use exponential backoff via tenacity.",
        )
        assert result == "accepted"

    def test_same_type_same_text_is_accepted_case_and_punctuation_insensitive(self) -> None:
        from maverick.assumptions.suggestions import classify_feedback

        suggestion = _suggestion(
            resolution="Yes, use exponential backoff via tenacity.",
            resolution_type="answered",
        )
        entry = _entry("mv-1", "Should retries use exponential backoff?", suggestion=suggestion)

        result = classify_feedback(
            entry,
            suggestion,
            resolution_type="answered",
            resolution="YES USE EXPONENTIAL BACKOFF VIA TENACITY",
        )
        assert result == "accepted"

    def test_same_type_different_text_is_rejected(self) -> None:
        from maverick.assumptions.suggestions import classify_feedback

        suggestion = _suggestion(
            resolution="Yes, use exponential backoff via tenacity.",
            resolution_type="answered",
        )
        entry = _entry("mv-1", "Should retries use exponential backoff?", suggestion=suggestion)

        result = classify_feedback(
            entry,
            suggestion,
            resolution_type="answered",
            resolution="No, use a fixed delay instead.",
        )
        assert result == "rejected"

    def test_answer_suggested_but_waived_is_rejected(self) -> None:
        """Type mismatch is rejected even when the text is identical."""
        from maverick.assumptions.suggestions import classify_feedback

        suggestion = _suggestion(
            resolution="Yes, use exponential backoff via tenacity.",
            resolution_type="answered",
        )
        entry = _entry("mv-1", "Should retries use exponential backoff?", suggestion=suggestion)

        result = classify_feedback(
            entry,
            suggestion,
            resolution_type="waived",
            resolution="Yes, use exponential backoff via tenacity.",
        )
        assert result == "rejected"

    def test_waive_suggested_but_answered_is_rejected(self) -> None:
        """Type mismatch is rejected even when the text is identical."""
        from maverick.assumptions.suggestions import classify_feedback

        suggestion = _suggestion(
            resolution="No longer applicable.",
            resolution_type="waived",
        )
        entry = _entry("mv-1", "Should retries use exponential backoff?", suggestion=suggestion)

        result = classify_feedback(
            entry,
            suggestion,
            resolution_type="answered",
            resolution="No longer applicable.",
        )
        assert result == "rejected"


class TestRecordFeedback:
    """record_feedback(store, entry, *, accepted) -> bool.

    Mirrors ``record_decision``'s never-raises/bool-return fail-soft
    contract (FR-004): a store-write failure returns ``False`` instead of
    raising; a successful append returns ``True``.
    """

    @pytest.mark.asyncio
    async def test_appends_accepted_feedback_record(self, tmp_path: Path) -> None:
        from maverick.assumptions.suggestions import record_feedback

        store = RunwayStore(tmp_path / "runway")
        await store.initialize()
        suggestion = _suggestion()
        entry = _entry("mv-1", "Should retries use exponential backoff?", suggestion=suggestion)

        ok = await record_feedback(store, entry, accepted=True)

        assert ok is True
        records = await store.get_match_feedback()
        assert len(records) == 1
        assert records[0].outcome == "accepted"
        assert records[0].source_entry_id == "mv-2"
        assert records[0].normalized_question == normalize_question(
            "Should retries use exponential backoff?"
        )

    @pytest.mark.asyncio
    async def test_appends_rejected_feedback_record(self, tmp_path: Path) -> None:
        from maverick.assumptions.suggestions import record_feedback

        store = RunwayStore(tmp_path / "runway")
        await store.initialize()
        suggestion = _suggestion()
        entry = _entry("mv-1", "Should retries use exponential backoff?", suggestion=suggestion)

        ok = await record_feedback(store, entry, accepted=False)

        assert ok is True
        records = await store.get_match_feedback()
        assert len(records) == 1
        assert records[0].outcome == "rejected"
        assert records[0].source_entry_id == "mv-2"

    @pytest.mark.asyncio
    async def test_store_failure_returns_false_never_raises(self, tmp_path: Path) -> None:
        from maverick.assumptions.suggestions import record_feedback

        store = RunwayStore(tmp_path / "runway")
        await store.initialize()
        suggestion = _suggestion()
        entry = _entry("mv-1", "Should retries use exponential backoff?", suggestion=suggestion)

        with patch.object(
            RunwayStore,
            "append_match_feedback",
            new=AsyncMock(side_effect=RuntimeError("disk full")),
        ):
            ok = await record_feedback(store, entry, accepted=True)

        assert ok is False


# ---------------------------------------------------------------------------
# End-to-end: rejection feedback suppresses even a perfect base-score match
# (FR-015), a subsequent acceptance restores it (spec 055, US3, T023).
#
# Unlike the classes above, ``evaluate_suggestion`` and ``MatchFeedbackRecord``
# already exist and the fold logic in ``evaluate_suggestion`` already applies
# ``matching.effective_confidence`` correctly — these tests exercise that
# existing behavior end-to-end with real MatchFeedbackRecord data, not a
# not-yet-implemented function. They are the regression guard T026 must keep
# green (the parameter has been feedback-driven since T018; only the
# *capture* of real feedback records is new in this story).
# ---------------------------------------------------------------------------


class TestFeedbackFoldSuppressesAndRestoresSuggestion:
    def test_perfect_match_without_feedback_is_suggested(self) -> None:
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        decision = _decision("mv-2", question)

        result = evaluate_suggestion(entry, [decision], feedback=[])

        assert result is not None
        assert result.confidence >= PRESENTATION_THRESHOLD
        # Identical normalized text -> base score at/near 1.0.
        assert result.confidence >= 0.99

    def test_one_net_rejection_suppresses_even_a_perfect_match(self) -> None:
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        decision = _decision("mv-2", question)

        rejection = MatchFeedbackRecord(
            normalized_question=normalize_question(question),
            source_entry_id="mv-2",
            outcome="rejected",
            recorded_at="2026-08-07T09:15:02+00:00",
        )

        # Sanity: without feedback this pairing IS suggested.
        assert evaluate_suggestion(entry, [decision], feedback=[]) is not None

        result = evaluate_suggestion(entry, [decision], feedback=[rejection])

        assert result is None, (
            "one net rejection (1.0 - REJECTION_PENALTY(0.30) = 0.70 < "
            "PRESENTATION_THRESHOLD(0.75)) must drop even a perfect base "
            "score below the presentation threshold (FR-015)"
        )

    def test_subsequent_acceptance_restores_the_suggestion(self) -> None:
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        decision = _decision("mv-2", question)

        rejection = MatchFeedbackRecord(
            normalized_question=normalize_question(question),
            source_entry_id="mv-2",
            outcome="rejected",
            recorded_at="2026-08-07T09:15:02+00:00",
        )
        acceptance = MatchFeedbackRecord(
            normalized_question=normalize_question(question),
            source_entry_id="mv-2",
            outcome="accepted",
            recorded_at="2026-08-08T09:15:02+00:00",
        )

        result = evaluate_suggestion(entry, [decision], feedback=[rejection, acceptance])

        assert result is not None, (
            "net rejections-acceptances == 0 must restore the suggestion (no penalty applied)"
        )
        assert result.source_entry_id == "mv-2"

    def test_unrelated_rejection_does_not_suppress_a_different_pairing(self) -> None:
        """The pairing key is (normalized_question, source_entry_id) — a
        rejection recorded against a different candidate must not penalize
        this one (R3)."""
        question = "Should retries use exponential backoff?"
        entry = _entry("mv-1", question)
        decision = _decision("mv-2", question)

        unrelated_rejection = MatchFeedbackRecord(
            normalized_question=normalize_question(question),
            source_entry_id="mv-different-candidate",
            outcome="rejected",
            recorded_at="2026-08-07T09:15:02+00:00",
        )

        result = evaluate_suggestion(entry, [decision], feedback=[unrelated_rejection])

        assert result is not None
        assert result.source_entry_id == "mv-2"


# ---------------------------------------------------------------------------
# attach_suggestions
# ---------------------------------------------------------------------------


class TestAttachSuggestionsStoreUnavailable:
    @pytest.mark.asyncio
    async def test_uninitialized_store_is_noop(self, tmp_path: Path) -> None:
        client = _client()
        store = RunwayStore(tmp_path / "runway")  # never initialize()d
        entry = _entry("mv-1", "Should retries use exponential backoff?")

        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            # Must not raise.
            await attach_suggestions(client, store, [entry])

        mock_set_state.assert_not_awaited()


class TestAttachSuggestionsPartialFailure:
    @pytest.mark.asyncio
    async def test_set_state_failure_for_one_does_not_block_others(self, tmp_path: Path) -> None:
        store = RunwayStore(tmp_path / "runway")
        await store.initialize()
        await store.append_decision(
            _decision("mv-src-1", "Should retries use exponential backoff?")
        )
        await store.append_decision(
            _decision("mv-src-2", "Should caching use a write-through policy?")
        )

        client = _client()
        entry_a = _entry("mv-a", "Should retries use exponential backoff?")
        entry_b = _entry("mv-b", "Should caching use a write-through policy?")

        async def flaky_set_state(*args: object, **kwargs: object) -> None:
            bead_id = args[0] if args else kwargs.get("bead_id")
            if bead_id == "mv-a":
                raise RuntimeError("bd set-state failed")
            # mv-b (and anything else) succeeds silently.

        mock_set_state = AsyncMock(side_effect=flaky_set_state)
        with patch.object(BeadClient, "set_state", new=mock_set_state):
            # Must not raise even though the first record's write fails.
            await attach_suggestions(client, store, [entry_a, entry_b])

        called_bead_ids = [
            call.args[0] if call.args else call.kwargs.get("bead_id")
            for call in mock_set_state.await_args_list
        ]
        assert "mv-b" in called_bead_ids


# ---------------------------------------------------------------------------
# backfill_suggestions
# ---------------------------------------------------------------------------


class TestBackfillSuggestions:
    @pytest.mark.asyncio
    async def test_evaluates_and_persists_for_entries_without_suggestion(
        self, tmp_path: Path
    ) -> None:
        store = RunwayStore(tmp_path / "runway")
        await store.initialize()
        await store.append_decision(
            _decision("mv-src-1", "Should retries use exponential backoff?")
        )

        client = _client()
        entry = _entry("mv-a", "Should retries use exponential backoff?", suggestion=None)

        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            await backfill_suggestions(client, store, [entry])

        mock_set_state.assert_awaited_once()
        called_bead_id = mock_set_state.await_args.args[0]
        assert called_bead_id == "mv-a"

    @pytest.mark.asyncio
    async def test_never_replaces_an_existing_stored_suggestion(self, tmp_path: Path) -> None:
        store = RunwayStore(tmp_path / "runway")
        await store.initialize()
        # A much better-matching decision now exists in the corpus, but the
        # entry already carries a (possibly stale-looking) suggestion —
        # backfill must never overwrite it (clarify Q5 / R11).
        await store.append_decision(
            _decision("mv-src-1", "Should retries use exponential backoff?")
        )

        existing_suggestion = Suggestion(
            resolution="Some prior recorded value.",
            resolution_type="answered",
            source_entry_id="mv-src-weird",
            source_spec="000-unrelated-spec",
            resolved_at="2020-01-01T00:00:00+00:00",
            confidence=0.5,
            computed_at="2020-01-01T00:00:00+00:00",
        )
        client = _client()
        entry = _entry(
            "mv-a",
            "Should retries use exponential backoff?",
            suggestion=existing_suggestion,
        )

        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            await backfill_suggestions(client, store, [entry])

        mock_set_state.assert_not_awaited()


# ---------------------------------------------------------------------------
# attach_suggestions auto-resolution (spec 055, User Story 4, T029)
#
# Target signature under test (not yet implemented as of this task — a
# parallel T031 agent adds ``AutoResolvePolicyConfig``/
# ``AssumptionResolutionConfig`` to ``maverick.config``; a parallel T032
# agent adds the ``auto_resolve`` parameter + branch below to
# ``attach_suggestions`` itself):
#
#     async def attach_suggestions(
#         client: BeadClient,
#         store: RunwayStore,
#         records: list[AssumptionReportEntry],
#         *,
#         auto_resolve: AutoResolvePolicyConfig | None = None,
#     ) -> None
#
# Every test below that passes ``auto_resolve=...`` currently fails with a
# ``TypeError`` (unexpected keyword argument) — that IS the red state this
# task asserts. ``AutoResolvePolicyConfig`` is imported locally per test
# (not at module level) so a not-yet-landed config class doesn't break
# collection of the rest of this file — same convention this module already
# uses for classify_feedback/record_feedback above.
#
# The auto-resolve branch is expected to call ``ledger.waive`` via
# ``maverick.assumptions.suggestions.ledger.waive`` — i.e. ``suggestions.py``
# imports the ``ledger`` *module* (``from maverick.assumptions import
# ledger``) rather than the bare function, so patching that attribute path
# stays stable regardless of exactly where in the function body the call
# happens. Until that import exists, every ``patch(...)`` call below raises
# ``AttributeError`` (module has no attribute ``ledger``) — also part of the
# expected red state.
#
# ``backfill_suggestions`` deliberately does NOT grow an ``auto_resolve``
# parameter at all (auto-resolution is recording-time only, per the spec) —
# see ``TestBackfillSuggestionsNeverAutoResolves`` below.
# ---------------------------------------------------------------------------

_MATCHING_QUESTION = "Should retries use exponential backoff?"

# A pair of near-but-not-identical questions with a base score of ~0.841
# (matching.py's SequenceMatcher+Jaccard blend) — comfortably above
# PRESENTATION_THRESHOLD (0.75, so a suggestion IS attached) but below any
# confidence_threshold >= 0.9 (so auto-resolve does NOT fire). Used by the
# "confidence below threshold" test.
_PARTIAL_ENTRY_QUESTION = "Should retries use exponential backoff for network calls?"
_PARTIAL_DECISION_QUESTION = "Should retries use exponential backoff for network requests?"


def _matching_decision(**overrides: object) -> DecisionRecord:
    """A decision whose question is an exact textual match for
    ``_MATCHING_QUESTION`` — base score ~1.0, comfortably above every
    threshold used in this section."""
    return _decision("mv-src", _MATCHING_QUESTION, **overrides)  # type: ignore[arg-type]


async def _store_with_decision(tmp_path: Path, decision: DecisionRecord) -> RunwayStore:
    store = RunwayStore(tmp_path / "runway")
    await store.initialize()
    await store.append_decision(decision)
    return store


class TestAttachSuggestionsAutoResolveFires:
    @pytest.mark.asyncio
    async def test_low_severity_enabled_policy_above_threshold_waives_and_marks(
        self, tmp_path: Path
    ) -> None:
        from maverick.assumptions.models import KEY_AUTO_RESOLVED, KEY_SUGGESTION
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.LOW)
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.75)

        mock_set_state = AsyncMock()
        with (
            patch.object(BeadClient, "set_state", new=mock_set_state),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        mock_waive.assert_awaited_once()
        _, kwargs = mock_waive.await_args
        assert kwargs["bead_id"] == "mv-1"
        assert kwargs["waived_by"] == "maverick-resolver"
        # Reason cites the source entry id, source spec, and date/confidence
        # context (research R7).
        assert "mv-src" in kwargs["reason"]
        assert "052-conditional-landing" in kwargs["reason"]

        # KEY_AUTO_RESOLVED ends up set alongside KEY_SUGGESTION — however
        # many `set_state` calls it takes to get there.
        written: dict[str, str] = {}
        for call in mock_set_state.await_args_list:
            state = call.args[1] if len(call.args) > 1 else call.kwargs.get("state", {})
            written.update(state)
        assert written.get(KEY_AUTO_RESOLVED) == "true"
        assert KEY_SUGGESTION in written

    @pytest.mark.asyncio
    async def test_auto_resolved_stamp_lands_before_the_waive(self, tmp_path: Path) -> None:
        """``KEY_AUTO_RESOLVED`` must be written BEFORE ``ledger.waive``.

        ``bd set-state`` is one subprocess call per key, so the stamp and
        the waive are not atomic and either can fail alone. The stamp is
        exactly what lets a human override the machine's decision
        (``maverick review <id>`` bypasses its already-waived refusal only
        for auto-resolved entries), so waiving first would mean a failure
        in between leaves an entry waived by ``maverick-resolver`` that no
        human can ever reopen. Stamping first inverts the failure into the
        harmless direction: an open entry with a stale marker nothing gates
        on.
        """
        from maverick.assumptions.models import KEY_AUTO_RESOLVED
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.LOW)
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.75)

        order: list[str] = []

        async def _set_state(_self, _bead_id, state, **_kwargs):  # noqa: ANN001, ANN202
            if KEY_AUTO_RESOLVED in state:
                order.append("stamp")

        async def _waive(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
            order.append("waive")

        with (
            patch.object(BeadClient, "set_state", new=_set_state),
            patch("maverick.assumptions.suggestions.ledger.waive", new=_waive),
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        assert order == ["stamp", "waive"]

    @pytest.mark.asyncio
    async def test_waive_failure_leaves_entry_unwaived_and_logs_the_cause(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failed auto-waive is the operator's only signal — it must
        carry the actual exception, not just the bead id."""
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.LOW)
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.75)

        with (
            caplog.at_level(logging.WARNING),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch(
                "maverick.assumptions.suggestions.ledger.waive",
                new=AsyncMock(side_effect=RuntimeError("bd rejected the waive")),
            ),
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        assert "bd rejected the waive" in caplog.text


class TestAttachSuggestionsAutoResolveConditions:
    """Each condition's negation, tested independently — auto-resolve only
    fires when ALL of {severity == low, policy enabled, confidence >=
    threshold} hold simultaneously."""

    @pytest.mark.asyncio
    async def test_medium_severity_not_auto_resolved(self, tmp_path: Path) -> None:
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.MEDIUM)
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.75)

        mock_set_state = AsyncMock()
        with (
            patch.object(BeadClient, "set_state", new=mock_set_state),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        mock_waive.assert_not_awaited()
        # A suggestion is still computed and persisted — only auto-resolve
        # is gated on severity.
        mock_set_state.assert_awaited()

    @pytest.mark.asyncio
    async def test_high_severity_not_auto_resolved(self, tmp_path: Path) -> None:
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.HIGH)
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.75)

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        mock_waive.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_legacy_synthesized_medium_severity_not_auto_resolved(
        self, tmp_path: Path
    ) -> None:
        """Legacy entries synthesize ``severity=medium``
        (``_legacy_record_from_details``) — functionally identical to the
        medium-severity case above, so eligibility is already excluded by
        the severity check with no special-casing needed. Constructed
        directly with ``severity=Severity.MEDIUM`` per the task's fixture
        guidance rather than threading a separate legacy-bead fixture
        through this evaluate-only path."""
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.MEDIUM)
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.75)

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        mock_waive.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_policy_none_not_auto_resolved_even_with_perfect_confidence(
        self, tmp_path: Path
    ) -> None:
        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.LOW)

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            # auto_resolve defaults to None — backward compatible no-op.
            await attach_suggestions(client, store, [entry])

        mock_waive.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_policy_disabled_not_auto_resolved_even_with_perfect_confidence(
        self, tmp_path: Path
    ) -> None:
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.LOW)
        # confidence_threshold must be >= 0.75 (config-schema.md guard,
        # pinned by T028) — 0.99 still exercises "perfect confidence"
        # while staying within the valid range; enabled=False alone must
        # suppress auto-resolve regardless of threshold.
        policy = AutoResolvePolicyConfig(enabled=False, confidence_threshold=0.99)

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        mock_waive.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confidence_below_threshold_suggestion_attached_but_not_waived(
        self, tmp_path: Path
    ) -> None:
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(
            tmp_path, _decision("mv-src", _PARTIAL_DECISION_QUESTION)
        )
        client = _client()
        entry = _entry("mv-1", _PARTIAL_ENTRY_QUESTION, severity=Severity.LOW)
        # base score ~0.841 clears PRESENTATION_THRESHOLD (0.75) — a
        # suggestion IS attached — but is below this policy's threshold, so
        # auto-resolve does NOT fire.
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.9)

        mock_set_state = AsyncMock()
        with (
            patch.object(BeadClient, "set_state", new=mock_set_state),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        mock_waive.assert_not_awaited()
        mock_set_state.assert_awaited()  # the suggestion itself is still persisted


class TestAttachSuggestionsAutoResolveExcludedFromCorpus:
    """FR-005: auto-resolution is machine-initiated and structurally
    excluded from the human decision corpus — no DecisionRecord, no
    MatchFeedbackRecord."""

    @pytest.mark.asyncio
    async def test_auto_resolve_writes_no_decision_or_feedback_record(
        self, tmp_path: Path
    ) -> None:
        from maverick.config import AutoResolvePolicyConfig

        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.LOW)
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.75)

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()),
            patch.object(RunwayStore, "append_decision", new=AsyncMock()) as mock_decision,
            patch.object(RunwayStore, "append_match_feedback", new=AsyncMock()) as mock_feedback,
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        mock_decision.assert_not_awaited()
        mock_feedback.assert_not_awaited()


class TestAttachSuggestionsLengthGuard:
    """``_MAX_SUGGESTION_JSON_LENGTH`` guard (quickstart-validation fix):
    ``bd set-state`` silently truncates a state value that overflows its
    internal label-length budget — no error. A suggestion whose encoded
    JSON would risk that must never be persisted; it's treated exactly like
    "no candidate matched" instead."""

    @pytest.mark.asyncio
    async def test_oversized_suggestion_never_persisted_and_stays_none(
        self, tmp_path: Path
    ) -> None:
        # A very long resolution text pushes the encoded JSON comfortably
        # past _MAX_SUGGESTION_JSON_LENGTH.
        long_resolution = "This is a very long adopted answer. " * 10
        store = await _store_with_decision(
            tmp_path,
            _decision(
                "mv-src-long",
                _MATCHING_QUESTION,
                resolution=long_resolution,
            ),
        )
        client = _client()
        entry = _entry("mv-a", _MATCHING_QUESTION)

        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            await attach_suggestions(client, store, [entry])

        mock_set_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_oversized_suggestion_does_not_block_other_records_in_batch(
        self, tmp_path: Path
    ) -> None:
        long_resolution = "This is a very long adopted answer. " * 10
        store = RunwayStore(tmp_path / "runway")
        await store.initialize()
        await store.append_decision(
            _decision("mv-src-long", _MATCHING_QUESTION, resolution=long_resolution)
        )
        await store.append_decision(
            _decision(
                "mv-src-short",
                "Should caching use a write-through policy?",
                resolution="Yes.",
            )
        )

        client = _client()
        oversized_entry = _entry("mv-oversized", _MATCHING_QUESTION)
        fits_entry = _entry("mv-fits", "Should caching use a write-through policy?")

        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            await attach_suggestions(client, store, [oversized_entry, fits_entry])

        called_bead_ids = [
            call.args[0] if call.args else call.kwargs.get("bead_id")
            for call in mock_set_state.await_args_list
        ]
        assert called_bead_ids == ["mv-fits"]

    @pytest.mark.asyncio
    async def test_oversized_suggestion_never_auto_resolves(self, tmp_path: Path) -> None:
        """An unpersistable suggestion must not trigger auto-resolution
        either — eligibility is only ever reached after a successful
        persist."""
        from maverick.config import AutoResolvePolicyConfig

        long_resolution = "This is a very long adopted answer. " * 10
        store = await _store_with_decision(
            tmp_path,
            _decision("mv-src-long", _MATCHING_QUESTION, resolution=long_resolution),
        )
        client = _client()
        entry = _entry("mv-a", _MATCHING_QUESTION, severity=Severity.LOW)
        policy = AutoResolvePolicyConfig(enabled=True, confidence_threshold=0.75)

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            await attach_suggestions(client, store, [entry], auto_resolve=policy)

        mock_set_state.assert_not_awaited()
        mock_waive.assert_not_awaited()

    @staticmethod
    def _resolution_for_target_encoded_length(target: int) -> str:
        """Find a resolution string whose real ``evaluate_suggestion`` output
        (with a live ``computed_at`` timestamp, not a fixed fixture one)
        encodes to exactly *target* chars — avoids drift from
        microsecond-precision timestamp length variance."""
        resolution = ""
        while True:
            entry = _entry("mv-a", _MATCHING_QUESTION)
            decision = _decision("mv-src", _MATCHING_QUESTION, resolution=resolution)
            suggestion = evaluate_suggestion(entry, [decision], feedback=[])
            assert suggestion is not None
            encoded_len = len(suggestion_to_json(suggestion))
            if encoded_len >= target:
                return resolution
            resolution += "x" * (target - encoded_len)

    @pytest.mark.asyncio
    async def test_just_under_limit_is_persisted(self, tmp_path: Path) -> None:
        # A resolution sized so the encoded suggestion lands just under
        # _MAX_SUGGESTION_JSON_LENGTH.
        resolution = self._resolution_for_target_encoded_length(_MAX_SUGGESTION_JSON_LENGTH - 1)

        store = await _store_with_decision(
            tmp_path, _decision("mv-src", _MATCHING_QUESTION, resolution=resolution)
        )
        client = _client()
        entry = _entry("mv-a", _MATCHING_QUESTION)

        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            await attach_suggestions(client, store, [entry])

        mock_set_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_just_over_limit_is_not_persisted(self, tmp_path: Path) -> None:
        # A resolution sized so the encoded suggestion lands just over
        # _MAX_SUGGESTION_JSON_LENGTH.
        resolution = self._resolution_for_target_encoded_length(_MAX_SUGGESTION_JSON_LENGTH + 1)

        store = await _store_with_decision(
            tmp_path, _decision("mv-src", _MATCHING_QUESTION, resolution=resolution)
        )
        client = _client()
        entry = _entry("mv-a", _MATCHING_QUESTION)

        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            await attach_suggestions(client, store, [entry])

        mock_set_state.assert_not_awaited()


class TestBackfillSuggestionsNeverAutoResolves:
    """``backfill_suggestions`` has no ``auto_resolve`` parameter at all
    (recording-time only, per the spec) — auto-resolution can never fire
    from this path regardless of how eligible the entry looks."""

    @pytest.mark.asyncio
    async def test_backfill_never_calls_waive_even_with_eligible_conditions(
        self, tmp_path: Path
    ) -> None:
        store = await _store_with_decision(tmp_path, _matching_decision())
        client = _client()
        entry = _entry("mv-1", _MATCHING_QUESTION, severity=Severity.LOW, suggestion=None)

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch("maverick.assumptions.suggestions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            # No `auto_resolve` kwarg exists to pass here — that's the point.
            await backfill_suggestions(client, store, [entry])

        mock_waive.assert_not_awaited()
