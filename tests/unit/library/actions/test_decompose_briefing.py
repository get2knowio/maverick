"""Unit tests for briefing enrichment of build_decomposition_prompt."""

from __future__ import annotations

from maverick.briefing.models import (
    Ambiguity,
    ArchitectureDecision,
    BriefingDocument,
    ContrarianBrief,
    EntitySketch,
    NavigatorBrief,
    ReconBrief,
    RiskFlag,
    StructuralistBrief,
)
from maverick.library.actions.decompose import (
    CodebaseContext,
    build_decomposition_prompt,
)


def _make_briefing(
    decisions: tuple[ArchitectureDecision, ...] = (),
    entities: tuple[EntitySketch, ...] = (),
    risks: tuple[RiskFlag, ...] = (),
    ambiguities: tuple[Ambiguity, ...] = (),
) -> BriefingDocument:
    return BriefingDocument(
        flight_plan_name="test-plan",
        created="2026-03-06T00:00:00+00:00",
        navigator=NavigatorBrief(
            architecture_decisions=decisions,
            module_structure="src/",
            integration_points=(),
            summary="Nav",
        ),
        structuralist=StructuralistBrief(entities=entities, interfaces=(), summary="Struct"),
        recon=ReconBrief(
            risks=risks,
            ambiguities=ambiguities,
            testing_strategy="Unit tests",
            summary="Recon",
        ),
        contrarian=ContrarianBrief(
            challenges=(),
            simplifications=(),
            consensus_points=(),
            summary="Contrarian",
        ),
        key_decisions=tuple(d.title for d in decisions),
        key_risks=tuple(r.description for r in risks if r.severity == "high"),
        open_questions=tuple(a.question for a in ambiguities),
    )


class TestBuildDecompositionPromptWithBriefing:
    def test_without_briefing_unchanged(self) -> None:
        """Without briefing, prompt has no briefing section."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        prompt = build_decomposition_prompt("plan", ctx)
        assert "Briefing Room Analysis" not in prompt

    def test_none_briefing_unchanged(self) -> None:
        """Explicit None briefing produces same result as omitting it."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        prompt = build_decomposition_prompt("plan", ctx, briefing=None)
        assert "Briefing Room Analysis" not in prompt

    def test_with_briefing_has_section(self) -> None:
        """With briefing, prompt includes Briefing Room Analysis section."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        briefing = _make_briefing()
        prompt = build_decomposition_prompt("plan", ctx, briefing=briefing)
        assert "## Briefing Room Analysis" in prompt

    def test_key_decisions_in_prompt(self) -> None:
        """Key decisions from briefing appear in prompt."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        briefing = _make_briefing(
            decisions=(
                ArchitectureDecision(
                    title="Use REST",
                    decision="REST API",
                    rationale="Simple",
                    alternatives_considered=(),
                ),
            )
        )
        prompt = build_decomposition_prompt("plan", ctx, briefing=briefing)
        assert "### Key Architecture Decisions" in prompt
        assert "Use REST" in prompt

    def test_data_model_in_prompt(self) -> None:
        """Entity sketches from briefing appear in prompt."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        briefing = _make_briefing(
            entities=(
                EntitySketch(
                    name="User",
                    module_path="src/models.py",
                    fields=("email: str",),
                    relationships=(),
                ),
            )
        )
        prompt = build_decomposition_prompt("plan", ctx, briefing=briefing)
        assert "### Data Model" in prompt
        assert "User" in prompt
        assert "src/models.py" in prompt

    def test_key_risks_in_prompt(self) -> None:
        """High-severity risks from briefing appear in prompt."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        briefing = _make_briefing(
            risks=(
                RiskFlag(
                    description="API breakage",
                    severity="high",
                    mitigation="Version",
                ),
            )
        )
        prompt = build_decomposition_prompt("plan", ctx, briefing=briefing)
        assert "### Key Risks" in prompt
        assert "API breakage" in prompt

    def test_open_questions_in_prompt(self) -> None:
        """Open questions from briefing appear in prompt."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        briefing = _make_briefing(
            ambiguities=(
                Ambiguity(
                    question="What auth?",
                    context="Not specified",
                    suggested_resolution="JWT",
                ),
            )
        )
        prompt = build_decomposition_prompt("plan", ctx, briefing=briefing)
        assert "### Open Questions" in prompt
        assert "What auth?" in prompt

    def test_briefing_before_instructions(self) -> None:
        """Briefing section appears before Instructions section."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        briefing = _make_briefing()
        prompt = build_decomposition_prompt("plan", ctx, briefing=briefing)
        briefing_idx = prompt.index("Briefing Room Analysis")
        instructions_idx = prompt.index("## Instructions")
        assert briefing_idx < instructions_idx

    def test_flight_plan_still_present(self) -> None:
        """Flight plan content is still in the prompt with briefing."""
        ctx = CodebaseContext(files=(), missing_files=(), total_size=0)
        briefing = _make_briefing()
        prompt = build_decomposition_prompt("My Flight Plan", ctx, briefing=briefing)
        assert "My Flight Plan" in prompt
