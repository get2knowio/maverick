"""Unit tests for maverick.preflight_briefing.models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.preflight_briefing.models import (
    CodebaseAnalystBrief,
    CriteriaWriterBrief,
    PreFlightBriefingDocument,
    PreFlightContrarianBrief,
    ScopistBrief,
)

# ---------------------------------------------------------------------------
# ScopistBrief
# ---------------------------------------------------------------------------


class TestScopistBrief:
    def test_valid_construction(self) -> None:
        brief = ScopistBrief(
            in_scope_items=("Add auth module",),
            out_of_scope_items=("Mobile app",),
            boundaries=("Server-side only",),
            scope_rationale="Auth is core to the PRD",
            summary="Scope analysis",
        )
        assert brief.in_scope_items == ("Add auth module",)
        assert brief.summary == "Scope analysis"

    def test_frozen(self) -> None:
        brief = ScopistBrief(
            in_scope_items=(),
            out_of_scope_items=(),
            boundaries=(),
            scope_rationale="",
            summary="S",
        )
        with pytest.raises(ValidationError):
            brief.summary = "new"  # type: ignore[misc]

    def test_empty_tuples(self) -> None:
        brief = ScopistBrief(
            in_scope_items=(),
            out_of_scope_items=(),
            boundaries=(),
            scope_rationale="",
            summary="",
        )
        assert brief.in_scope_items == ()


# ---------------------------------------------------------------------------
# CodebaseAnalystBrief
# ---------------------------------------------------------------------------


class TestCodebaseAnalystBrief:
    def test_valid_construction(self) -> None:
        brief = CodebaseAnalystBrief(
            relevant_modules=("src/auth/",),
            existing_patterns=("MaverickAgent pattern",),
            integration_points=("CLI entry point",),
            complexity_assessment="Medium",
            summary="Codebase mapping",
        )
        assert brief.relevant_modules == ("src/auth/",)
        assert brief.complexity_assessment == "Medium"

    def test_frozen(self) -> None:
        brief = CodebaseAnalystBrief(
            relevant_modules=(),
            existing_patterns=(),
            integration_points=(),
            complexity_assessment="",
            summary="S",
        )
        with pytest.raises(ValidationError):
            brief.summary = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CriteriaWriterBrief
# ---------------------------------------------------------------------------


class TestCriteriaWriterBrief:
    def test_valid_construction(self) -> None:
        brief = CriteriaWriterBrief(
            success_criteria=("Auth endpoint returns 200",),
            objective_draft="Implement JWT auth",
            measurability_notes="All criteria are testable",
            summary="Criteria draft",
        )
        assert brief.success_criteria == ("Auth endpoint returns 200",)
        assert brief.objective_draft == "Implement JWT auth"

    def test_frozen(self) -> None:
        brief = CriteriaWriterBrief(
            success_criteria=(),
            objective_draft="",
            measurability_notes="",
            summary="S",
        )
        with pytest.raises(ValidationError):
            brief.summary = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PreFlightContrarianBrief
# ---------------------------------------------------------------------------


class TestPreFlightContrarianBrief:
    def test_valid_construction(self) -> None:
        brief = PreFlightContrarianBrief(
            scope_challenges=("Scope too broad",),
            criteria_challenges=("Criterion 3 is vague",),
            missing_considerations=("Rate limiting not addressed",),
            consensus_points=("Use existing auth patterns",),
            summary="Contrarian review",
        )
        assert brief.scope_challenges == ("Scope too broad",)
        assert brief.consensus_points == ("Use existing auth patterns",)

    def test_frozen(self) -> None:
        brief = PreFlightContrarianBrief(
            scope_challenges=(),
            criteria_challenges=(),
            missing_considerations=(),
            consensus_points=(),
            summary="S",
        )
        with pytest.raises(ValidationError):
            brief.summary = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PreFlightBriefingDocument
# ---------------------------------------------------------------------------


class TestPreFlightBriefingDocument:
    def _make_doc(self) -> PreFlightBriefingDocument:
        return PreFlightBriefingDocument(
            prd_name="test-prd",
            created="2026-03-06T00:00:00+00:00",
            scopist=ScopistBrief(
                in_scope_items=("Add auth",),
                out_of_scope_items=(),
                boundaries=(),
                scope_rationale="Core requirement",
                summary="scopist",
            ),
            codebase_analyst=CodebaseAnalystBrief(
                relevant_modules=(),
                existing_patterns=(),
                integration_points=(),
                complexity_assessment="Low",
                summary="analyst",
            ),
            criteria_writer=CriteriaWriterBrief(
                success_criteria=("Tests pass",),
                objective_draft="Implement auth",
                measurability_notes="",
                summary="criteria",
            ),
            contrarian=PreFlightContrarianBrief(
                scope_challenges=(),
                criteria_challenges=(),
                missing_considerations=("Edge case X",),
                consensus_points=(),
                summary="contrarian",
            ),
            key_scope_items=("Add auth",),
            key_criteria=("Tests pass",),
            open_questions=("Edge case X",),
        )

    def test_valid_construction(self) -> None:
        doc = self._make_doc()
        assert doc.prd_name == "test-prd"
        assert len(doc.key_scope_items) == 1
        assert len(doc.key_criteria) == 1

    def test_frozen(self) -> None:
        doc = self._make_doc()
        with pytest.raises(ValidationError):
            doc.prd_name = "new"  # type: ignore[misc]

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            PreFlightBriefingDocument(  # type: ignore[call-arg]
                prd_name="test",
                created="2026-03-06",
            )

    def test_empty_synthesis_fields(self) -> None:
        doc = PreFlightBriefingDocument(
            prd_name="empty",
            created="2026-03-06T00:00:00+00:00",
            scopist=ScopistBrief(
                in_scope_items=(),
                out_of_scope_items=(),
                boundaries=(),
                scope_rationale="",
                summary="",
            ),
            codebase_analyst=CodebaseAnalystBrief(
                relevant_modules=(),
                existing_patterns=(),
                integration_points=(),
                complexity_assessment="",
                summary="",
            ),
            criteria_writer=CriteriaWriterBrief(
                success_criteria=(),
                objective_draft="",
                measurability_notes="",
                summary="",
            ),
            contrarian=PreFlightContrarianBrief(
                scope_challenges=(),
                criteria_challenges=(),
                missing_considerations=(),
                consensus_points=(),
                summary="",
            ),
            key_scope_items=(),
            key_criteria=(),
            open_questions=(),
        )
        assert doc.key_scope_items == ()
        assert doc.key_criteria == ()
        assert doc.open_questions == ()

    def test_round_trip_serialization(self) -> None:
        doc = self._make_doc()
        data = doc.model_dump()
        reconstructed = PreFlightBriefingDocument(**data)
        assert reconstructed == doc
