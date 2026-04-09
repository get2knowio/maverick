"""Unit tests for maverick.briefing.serializer."""

from __future__ import annotations

from maverick.briefing.models import (
    ArchitectureDecision,
    BriefingDocument,
    Challenge,
    ContrarianBrief,
    EntitySketch,
    NavigatorBrief,
    ReconBrief,
    StructuralistBrief,
)
from maverick.briefing.serializer import serialize_briefing


def _make_minimal_doc() -> BriefingDocument:
    return BriefingDocument(
        flight_plan_name="test-plan",
        created="2026-03-06T00:00:00+00:00",
        navigator=NavigatorBrief(
            architecture_decisions=(),
            module_structure="src/",
            integration_points=(),
            summary="Nav summary",
        ),
        structuralist=StructuralistBrief(entities=(), interfaces=(), summary="Struct summary"),
        recon=ReconBrief(
            risks=(),
            ambiguities=(),
            testing_strategy="Unit tests",
            summary="Recon summary",
        ),
        contrarian=ContrarianBrief(
            challenges=(),
            simplifications=(),
            consensus_points=(),
            summary="Contrarian summary",
        ),
        key_decisions=(),
        key_risks=(),
        open_questions=(),
    )


class TestSerializeBriefing:
    def test_has_yaml_frontmatter(self) -> None:
        result = serialize_briefing(_make_minimal_doc())
        assert result.startswith("---\n")
        assert "flight-plan: test-plan" in result

    def test_has_summary_section(self) -> None:
        result = serialize_briefing(_make_minimal_doc())
        assert "## Summary" in result
        assert "### Navigator" in result
        assert "Nav summary" in result
        assert "### Structuralist" in result
        assert "### Recon" in result
        assert "### Contrarian" in result

    def test_key_decisions_omitted_when_empty(self) -> None:
        result = serialize_briefing(_make_minimal_doc())
        assert "## Key Decisions" not in result

    def test_key_decisions_present_when_populated(self) -> None:
        doc = _make_minimal_doc().model_copy(
            update={"key_decisions": ("Use Pydantic", "Use REST")}
        )
        result = serialize_briefing(doc)
        assert "## Key Decisions" in result
        assert "- Use Pydantic" in result
        assert "- Use REST" in result

    def test_key_risks_present_when_populated(self) -> None:
        doc = _make_minimal_doc().model_copy(update={"key_risks": ("API breakage",)})
        result = serialize_briefing(doc)
        assert "## Key Risks" in result
        assert "- API breakage" in result

    def test_open_questions_present_when_populated(self) -> None:
        doc = _make_minimal_doc().model_copy(update={"open_questions": ("Auth mechanism?",)})
        result = serialize_briefing(doc)
        assert "## Open Questions" in result
        assert "- Auth mechanism?" in result

    def test_architecture_decisions_rendered(self) -> None:
        nav = NavigatorBrief(
            architecture_decisions=(
                ArchitectureDecision(
                    title="Use REST",
                    decision="REST API",
                    rationale="Simplicity",
                    alternatives_considered=("GraphQL",),
                ),
            ),
            module_structure="src/",
            integration_points=(),
            summary="Nav",
        )
        doc = _make_minimal_doc().model_copy(update={"navigator": nav})
        result = serialize_briefing(doc)
        assert "## Architecture Decisions" in result
        assert "### Use REST" in result
        assert "**Decision:** REST API" in result
        assert "- GraphQL" in result

    def test_data_model_rendered(self) -> None:
        struct = StructuralistBrief(
            entities=(
                EntitySketch(
                    name="User",
                    module_path="src/models.py",
                    fields=("email: str",),
                    relationships=("has_many: Post",),
                ),
            ),
            interfaces=(),
            summary="Struct",
        )
        doc = _make_minimal_doc().model_copy(update={"structuralist": struct})
        result = serialize_briefing(doc)
        assert "## Data Model" in result
        assert "### User" in result
        assert "`email: str`" in result

    def test_challenges_rendered(self) -> None:
        contrarian = ContrarianBrief(
            challenges=(
                Challenge(
                    target="Microservices",
                    counter_argument="Over-engineering",
                    recommendation="Use monolith",
                ),
            ),
            simplifications=(),
            consensus_points=(),
            summary="Contrarian",
        )
        doc = _make_minimal_doc().model_copy(update={"contrarian": contrarian})
        result = serialize_briefing(doc)
        assert "## Challenges" in result
        assert "### Microservices" in result

    def test_returns_string(self) -> None:
        result = serialize_briefing(_make_minimal_doc())
        assert isinstance(result, str)
