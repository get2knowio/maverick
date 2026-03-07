"""Unit tests for maverick.agents.preflight_briefing.prompts."""

from __future__ import annotations

from maverick.agents.preflight_briefing.prompts import (
    build_preflight_briefing_prompt,
    build_preflight_contrarian_prompt,
)
from maverick.preflight_briefing.models import (
    CodebaseAnalystBrief,
    CriteriaWriterBrief,
    ScopistBrief,
)


def _make_scopist() -> ScopistBrief:
    return ScopistBrief(
        in_scope_items=("Add auth",),
        out_of_scope_items=(),
        boundaries=(),
        scope_rationale="Core requirement",
        summary="Scopist summary",
    )


def _make_codebase_analyst() -> CodebaseAnalystBrief:
    return CodebaseAnalystBrief(
        relevant_modules=("src/auth/",),
        existing_patterns=(),
        integration_points=(),
        complexity_assessment="Low",
        summary="Analyst summary",
    )


def _make_criteria_writer() -> CriteriaWriterBrief:
    return CriteriaWriterBrief(
        success_criteria=("Tests pass",),
        objective_draft="Implement auth",
        measurability_notes="All testable",
        summary="Criteria summary",
    )


class TestBuildPreflightBriefingPrompt:
    def test_includes_prd_content(self) -> None:
        result = build_preflight_briefing_prompt("## Feature\nAdd auth.")
        assert "## Feature" in result
        assert "Add auth." in result

    def test_has_prd_section(self) -> None:
        result = build_preflight_briefing_prompt("content")
        assert "## PRD Content" in result

    def test_returns_string(self) -> None:
        result = build_preflight_briefing_prompt("content")
        assert isinstance(result, str)


class TestBuildPreflightContrarianPrompt:
    def test_includes_prd_content(self) -> None:
        result = build_preflight_contrarian_prompt(
            "The PRD",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
        )
        assert "The PRD" in result

    def test_includes_scopist_brief(self) -> None:
        result = build_preflight_contrarian_prompt(
            "prd",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
        )
        assert "## Scopist Brief" in result
        assert "Scopist summary" in result

    def test_includes_codebase_analyst_brief(self) -> None:
        result = build_preflight_contrarian_prompt(
            "prd",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
        )
        assert "## Codebase Analyst Brief" in result

    def test_includes_criteria_writer_brief(self) -> None:
        result = build_preflight_contrarian_prompt(
            "prd",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
        )
        assert "## Criteria Writer Brief" in result

    def test_briefs_as_json(self) -> None:
        result = build_preflight_contrarian_prompt(
            "prd",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
        )
        assert "```json" in result

    def test_returns_string(self) -> None:
        result = build_preflight_contrarian_prompt(
            "prd",
            _make_scopist(),
            _make_codebase_analyst(),
            _make_criteria_writer(),
        )
        assert isinstance(result, str)
