"""Unit tests for maverick.preflight_briefing.serializer."""

from __future__ import annotations

from maverick.preflight_briefing.models import (
    CodebaseAnalystBrief,
    CriteriaWriterBrief,
    PreFlightBriefingDocument,
    PreFlightContrarianBrief,
    ScopistBrief,
)
from maverick.preflight_briefing.serializer import serialize_preflight_briefing


def _make_minimal_doc() -> PreFlightBriefingDocument:
    return PreFlightBriefingDocument(
        prd_name="test-prd",
        created="2026-03-06T00:00:00+00:00",
        scopist=ScopistBrief(
            in_scope_items=(),
            out_of_scope_items=(),
            boundaries=(),
            scope_rationale="",
            summary="Scopist summary",
        ),
        codebase_analyst=CodebaseAnalystBrief(
            relevant_modules=(),
            existing_patterns=(),
            integration_points=(),
            complexity_assessment="",
            summary="Analyst summary",
        ),
        criteria_writer=CriteriaWriterBrief(
            success_criteria=(),
            objective_draft="",
            measurability_notes="",
            summary="Criteria summary",
        ),
        contrarian=PreFlightContrarianBrief(
            scope_challenges=(),
            criteria_challenges=(),
            missing_considerations=(),
            consensus_points=(),
            summary="Contrarian summary",
        ),
        key_scope_items=(),
        key_criteria=(),
        open_questions=(),
    )


class TestSerializePreflightBriefing:
    def test_has_title(self) -> None:
        result = serialize_preflight_briefing(_make_minimal_doc())
        assert "# Pre-Flight Briefing: test-prd" in result

    def test_has_summary_section(self) -> None:
        result = serialize_preflight_briefing(_make_minimal_doc())
        assert "## Agent Summaries" in result
        assert "### Scopist" in result
        assert "Scopist summary" in result
        assert "### Codebase Analyst" in result
        assert "### Criteria Writer" in result
        assert "### Contrarian" in result

    def test_scope_items_omitted_when_empty(self) -> None:
        result = serialize_preflight_briefing(_make_minimal_doc())
        assert "## Key Scope Items" not in result

    def test_scope_items_present_when_populated(self) -> None:
        doc = _make_minimal_doc().model_copy(update={"key_scope_items": ("Add auth", "Add tests")})
        result = serialize_preflight_briefing(doc)
        assert "## Key Scope Items" in result
        assert "- Add auth" in result
        assert "- Add tests" in result

    def test_criteria_present_when_populated(self) -> None:
        doc = _make_minimal_doc().model_copy(update={"key_criteria": ("Tests pass",)})
        result = serialize_preflight_briefing(doc)
        assert "## Success Criteria" in result
        assert "- Tests pass" in result

    def test_open_questions_present_when_populated(self) -> None:
        doc = _make_minimal_doc().model_copy(update={"open_questions": ("Rate limiting?",)})
        result = serialize_preflight_briefing(doc)
        assert "## Open Questions" in result
        assert "- Rate limiting?" in result

    def test_out_of_scope_rendered(self) -> None:
        scopist = ScopistBrief(
            in_scope_items=(),
            out_of_scope_items=("Mobile app",),
            boundaries=(),
            scope_rationale="",
            summary="S",
        )
        doc = _make_minimal_doc().model_copy(update={"scopist": scopist})
        result = serialize_preflight_briefing(doc)
        assert "## Out of Scope" in result
        assert "- Mobile app" in result

    def test_relevant_modules_rendered(self) -> None:
        analyst = CodebaseAnalystBrief(
            relevant_modules=("src/auth/",),
            existing_patterns=(),
            integration_points=(),
            complexity_assessment="",
            summary="A",
        )
        doc = _make_minimal_doc().model_copy(update={"codebase_analyst": analyst})
        result = serialize_preflight_briefing(doc)
        assert "## Relevant Modules" in result
        assert "- src/auth/" in result

    def test_scope_challenges_rendered(self) -> None:
        contrarian = PreFlightContrarianBrief(
            scope_challenges=("Too broad",),
            criteria_challenges=(),
            missing_considerations=(),
            consensus_points=(),
            summary="C",
        )
        doc = _make_minimal_doc().model_copy(update={"contrarian": contrarian})
        result = serialize_preflight_briefing(doc)
        assert "## Scope Challenges" in result
        assert "- Too broad" in result

    def test_consensus_rendered(self) -> None:
        contrarian = PreFlightContrarianBrief(
            scope_challenges=(),
            criteria_challenges=(),
            missing_considerations=(),
            consensus_points=("Use existing patterns",),
            summary="C",
        )
        doc = _make_minimal_doc().model_copy(update={"contrarian": contrarian})
        result = serialize_preflight_briefing(doc)
        assert "## Consensus Points" in result
        assert "- Use existing patterns" in result

    def test_returns_string(self) -> None:
        result = serialize_preflight_briefing(_make_minimal_doc())
        assert isinstance(result, str)
