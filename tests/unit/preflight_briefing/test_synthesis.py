"""Unit tests for maverick.preflight_briefing.synthesis."""

from __future__ import annotations

from maverick.preflight_briefing.models import (
    CodebaseAnalystBrief,
    CriteriaWriterBrief,
    PreFlightContrarianBrief,
    ScopistBrief,
)
from maverick.preflight_briefing.synthesis import synthesize_preflight_briefing


def _make_scopist(
    in_scope_items: tuple[str, ...] = (),
) -> ScopistBrief:
    return ScopistBrief(
        in_scope_items=in_scope_items,
        out_of_scope_items=(),
        boundaries=(),
        scope_rationale="Rationale",
        summary="Scopist summary",
    )


def _make_codebase_analyst() -> CodebaseAnalystBrief:
    return CodebaseAnalystBrief(
        relevant_modules=(),
        existing_patterns=(),
        integration_points=(),
        complexity_assessment="Low",
        summary="Analyst summary",
    )


def _make_criteria_writer(
    success_criteria: tuple[str, ...] = (),
) -> CriteriaWriterBrief:
    return CriteriaWriterBrief(
        success_criteria=success_criteria,
        objective_draft="Draft objective",
        measurability_notes="All measurable",
        summary="Criteria summary",
    )


def _make_contrarian(
    missing_considerations: tuple[str, ...] = (),
) -> PreFlightContrarianBrief:
    return PreFlightContrarianBrief(
        scope_challenges=(),
        criteria_challenges=(),
        missing_considerations=missing_considerations,
        consensus_points=(),
        summary="Contrarian summary",
    )


class TestSynthesizePreflightBriefing:
    def test_basic_synthesis(self) -> None:
        doc = synthesize_preflight_briefing(
            "test-prd",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
            _make_contrarian(),
        )
        assert doc.prd_name == "test-prd"
        assert doc.created  # ISO timestamp is set

    def test_key_scope_items_from_scopist(self) -> None:
        scopist = _make_scopist(in_scope_items=("Add auth", "Add tests"))
        doc = synthesize_preflight_briefing(
            "plan",
            scopist,
            _make_codebase_analyst(),
            _make_criteria_writer(),
            _make_contrarian(),
        )
        assert doc.key_scope_items == ("Add auth", "Add tests")

    def test_key_criteria_from_criteria_writer(self) -> None:
        criteria = _make_criteria_writer(success_criteria=("Tests pass", "Lint clean"))
        doc = synthesize_preflight_briefing(
            "plan",
            _make_scopist(),
            _make_codebase_analyst(),
            criteria,
            _make_contrarian(),
        )
        assert doc.key_criteria == ("Tests pass", "Lint clean")

    def test_open_questions_from_contrarian(self) -> None:
        contrarian = _make_contrarian(missing_considerations=("Rate limiting?", "Error handling?"))
        doc = synthesize_preflight_briefing(
            "plan",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
            contrarian,
        )
        assert doc.open_questions == ("Rate limiting?", "Error handling?")

    def test_empty_inputs_produce_empty_synthesis(self) -> None:
        doc = synthesize_preflight_briefing(
            "empty",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
            _make_contrarian(),
        )
        assert doc.key_scope_items == ()
        assert doc.key_criteria == ()
        assert doc.open_questions == ()

    def test_created_is_iso_format(self) -> None:
        doc = synthesize_preflight_briefing(
            "plan",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
            _make_contrarian(),
        )
        assert "T" in doc.created

    def test_all_briefs_preserved(self) -> None:
        scopist = _make_scopist()
        analyst = _make_codebase_analyst()
        criteria = _make_criteria_writer()
        contrarian = _make_contrarian()
        doc = synthesize_preflight_briefing("plan", scopist, analyst, criteria, contrarian)
        assert doc.scopist is scopist
        assert doc.codebase_analyst is analyst
        assert doc.criteria_writer is criteria
        assert doc.contrarian is contrarian
