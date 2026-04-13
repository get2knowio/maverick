"""Unit tests for maverick.preflight_briefing.serializer."""

from __future__ import annotations

from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown


class TestSerializeBriefsToMarkdown:
    def test_has_title(self) -> None:
        result = serialize_briefs_to_markdown("test-prd")
        # No briefs → empty string
        assert result == ""

    def test_scope_in_scope_items(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            scope={"in_scope": ["Add auth", "Add tests"]},
        )
        assert "# Pre-Flight Briefing: test-prd" in result
        assert "## In Scope" in result
        assert "- Add auth" in result
        assert "- Add tests" in result

    def test_scope_out_of_scope(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            scope={"in_scope": ["X"], "out_scope": ["Mobile app"]},
        )
        assert "## Out of Scope" in result
        assert "- Mobile app" in result

    def test_scope_boundaries(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            scope={"in_scope": ["X"], "boundaries": ["Server-side only"]},
        )
        assert "## Scope Boundaries" in result
        assert "- Server-side only" in result

    def test_analysis_modules(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            analysis={"modules": ["src/auth/"]},
        )
        assert "## Relevant Modules" in result
        assert "- src/auth/" in result

    def test_analysis_patterns(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            analysis={"modules": ["X"], "patterns": ["MaverickAgent pattern"]},
        )
        assert "## Existing Patterns" in result
        assert "- MaverickAgent pattern" in result

    def test_criteria_list(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            criteria={"criteria": ["Tests pass", "Lint clean"]},
        )
        assert "## Success Criteria" in result
        assert "- Tests pass" in result
        assert "- Lint clean" in result

    def test_challenge_risks(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            challenge={"risks": ["Too broad"]},
        )
        assert "## Risks & Challenges" in result
        assert "- Too broad" in result

    def test_challenge_open_questions(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            challenge={"risks": ["X"], "open_questions": ["Rate limiting?"]},
        )
        assert "## Open Questions" in result
        assert "- Rate limiting?" in result

    def test_challenge_consensus(self) -> None:
        result = serialize_briefs_to_markdown(
            "test-prd",
            challenge={"risks": ["X"], "consensus_points": ["Use existing patterns"]},
        )
        assert "## Consensus Points" in result
        assert "- Use existing patterns" in result

    def test_all_briefs_combined(self) -> None:
        result = serialize_briefs_to_markdown(
            "plan",
            scope={"in_scope": ["Auth"]},
            analysis={"modules": ["src/auth/"]},
            criteria={"criteria": ["Tests pass"]},
            challenge={"risks": ["Scope creep"]},
        )
        assert "## In Scope" in result
        assert "## Relevant Modules" in result
        assert "## Success Criteria" in result
        assert "## Risks & Challenges" in result

    def test_returns_string(self) -> None:
        result = serialize_briefs_to_markdown(
            "plan",
            scope={"in_scope": ["X"]},
        )
        assert isinstance(result, str)

    def test_tolerates_legacy_field_names(self) -> None:
        """Accepts both MCP tool field names and legacy Pydantic field names."""
        result = serialize_briefs_to_markdown(
            "plan",
            scope={"in_scope_items": ["Auth"], "out_of_scope_items": ["Mobile"]},
        )
        assert "- Auth" in result
        assert "- Mobile" in result

    def test_summary_fields(self) -> None:
        result = serialize_briefs_to_markdown(
            "plan",
            scope={"in_scope": ["X"], "summary": "Scope is tight"},
            analysis={"modules": ["Y"], "summary": "Codebase is clean"},
        )
        assert "Scope is tight" in result
        assert "Codebase is clean" in result
