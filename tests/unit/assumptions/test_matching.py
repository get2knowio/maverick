"""Tests for the pure, deterministic matching module (assumptions/matching.py).

See specs/055-learned-assumption-resolution/contracts/decision-records.md for
the normative matching formula this module implements.
"""

from __future__ import annotations

from maverick.assumptions.matching import (
    PRESENTATION_THRESHOLD,
    REJECTION_PENALTY,
    base_score,
    effective_confidence,
    normalize_question,
    select_best,
)


class TestNormalizeQuestion:
    def test_casefold_strip_punctuation_collapse_whitespace(self) -> None:
        assert normalize_question("Should Retries use EXPONENTIAL backoff?") == (
            normalize_question("should retries use exponential backoff")
        )

    def test_result_has_no_punctuation(self) -> None:
        result = normalize_question("Should retries use exponential backoff?")
        assert result == "should retries use exponential backoff"

    def test_collapses_internal_whitespace(self) -> None:
        result = normalize_question("Should   retries    use\tbackoff?")
        assert result == "should retries use backoff"

    def test_strips_leading_and_trailing_whitespace(self) -> None:
        assert normalize_question("  Should retries use backoff?  ") == (
            "should retries use backoff"
        )

    def test_casefold_handles_unicode(self) -> None:
        # casefold() is stronger than lower() for some unicode (e.g. German ß).
        assert normalize_question("STRASSE") == normalize_question("straße".upper())

    def test_empty_string(self) -> None:
        assert normalize_question("") == ""

    def test_only_punctuation_becomes_empty(self) -> None:
        assert normalize_question("???!!!...") == ""


class TestBaseScoreDeterminism:
    def test_same_args_same_result(self) -> None:
        a = "Should retries use exponential backoff?"
        b = "Should we use exponential backoff for retries?"
        first = base_score(a, b)
        second = base_score(a, b)
        assert first == second

    def test_bounded_in_zero_one(self) -> None:
        pairs = [
            ("Should retries use exponential backoff?", "Completely unrelated text."),
            ("", ""),
            ("a b c", "c b a"),
            ("Same question?", "Same question?"),
        ]
        for a, b in pairs:
            score = base_score(a, b)
            assert 0.0 <= score <= 1.0

    def test_identical_strings_score_at_one(self) -> None:
        text = "Should retries use exponential backoff?"
        assert base_score(text, text) == 1.0

    def test_identical_after_normalization_scores_at_one(self) -> None:
        assert base_score("Should Retries Use Backoff?", "should retries use backoff") == 1.0

    def test_disjoint_strings_score_low(self) -> None:
        score = base_score(
            "Should retries use exponential backoff for network calls",
            "Where should the deployment artifacts be archived permanently",
        )
        assert score < 0.3

    def test_empty_vs_nonempty_does_not_error(self) -> None:
        # Guards the Jaccard divide-by-zero when one side has no tokens.
        score = base_score("", "Should retries use backoff?")
        assert 0.0 <= score <= 1.0

    def test_both_empty_scores_one(self) -> None:
        # SequenceMatcher.ratio() on two empty strings is 1.0; Jaccard term
        # is defined as 0 when both token sets are empty per the contract.
        assert base_score("", "") == 0.5

    def test_symmetric(self) -> None:
        a = "Should retries use exponential backoff?"
        b = "Should backoff be exponential for retries?"
        assert base_score(a, b) == base_score(b, a)


class TestModuleConstants:
    def test_presentation_threshold(self) -> None:
        assert PRESENTATION_THRESHOLD == 0.75

    def test_rejection_penalty(self) -> None:
        assert REJECTION_PENALTY == 0.30


class TestEffectiveConfidence:
    def test_no_history_returns_base_unchanged(self) -> None:
        assert effective_confidence(1.0, rejections=0, acceptances=0) == 1.0
        assert effective_confidence(0.5, rejections=0, acceptances=0) == 0.5

    def test_one_net_rejection_suppresses_exact_match(self) -> None:
        # FR-015: a single net rejection must drop even a perfect base score
        # below PRESENTATION_THRESHOLD.
        result = effective_confidence(1.0, rejections=1, acceptances=0)
        assert result < PRESENTATION_THRESHOLD
        assert result == 0.70

    def test_equal_rejections_and_acceptances_net_zero(self) -> None:
        assert effective_confidence(1.0, rejections=2, acceptances=2) == 1.0

    def test_acceptances_exceeding_rejections_do_not_boost(self) -> None:
        # max(0, rejections - acceptances) floors at zero — no bonus above base.
        assert effective_confidence(0.8, rejections=0, acceptances=5) == 0.8

    def test_multiple_net_rejections_compound(self) -> None:
        result = effective_confidence(1.0, rejections=3, acceptances=0)
        assert result == 1.0 - (0.30 * 3)


class TestSelectBest:
    def test_empty_input_returns_none(self) -> None:
        assert select_best([]) is None

    def test_all_below_threshold_returns_none(self) -> None:
        candidates = [
            (0.5, "2026-08-01T00:00:00+00:00", "mv-1", "payload-1"),
            (0.6, "2026-08-02T00:00:00+00:00", "mv-2", "payload-2"),
        ]
        assert select_best(candidates) is None

    def test_picks_highest_confidence(self) -> None:
        candidates = [
            (0.80, "2026-08-01T00:00:00+00:00", "mv-1", "payload-1"),
            (0.95, "2026-08-02T00:00:00+00:00", "mv-2", "payload-2"),
            (0.76, "2026-08-03T00:00:00+00:00", "mv-3", "payload-3"),
        ]
        assert select_best(candidates) == candidates[1]

    def test_tie_breaks_on_resolved_at_descending(self) -> None:
        candidates = [
            (0.90, "2026-08-01T00:00:00+00:00", "mv-1", "payload-1"),
            (0.90, "2026-08-05T00:00:00+00:00", "mv-2", "payload-2"),
            (0.90, "2026-08-03T00:00:00+00:00", "mv-3", "payload-3"),
        ]
        assert select_best(candidates) == candidates[1]

    def test_tie_breaks_on_source_entry_id_ascending(self) -> None:
        candidates = [
            (0.90, "2026-08-01T00:00:00+00:00", "mv-99", "payload-1"),
            (0.90, "2026-08-01T00:00:00+00:00", "mv-2", "payload-2"),
            (0.90, "2026-08-01T00:00:00+00:00", "mv-42", "payload-3"),
        ]
        assert select_best(candidates) == candidates[1]

    def test_below_threshold_candidates_excluded_even_if_highest(self) -> None:
        candidates = [
            (0.74, "2026-08-05T00:00:00+00:00", "mv-1", "payload-1"),
            (0.75, "2026-08-01T00:00:00+00:00", "mv-2", "payload-2"),
        ]
        assert select_best(candidates) == candidates[1]

    def test_single_candidate_at_exact_threshold_wins(self) -> None:
        candidates = [(0.75, "2026-08-01T00:00:00+00:00", "mv-1", "payload-1")]
        assert select_best(candidates) == candidates[0]
