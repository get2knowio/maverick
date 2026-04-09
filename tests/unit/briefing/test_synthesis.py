"""Unit tests for maverick.briefing.synthesis."""

from __future__ import annotations

from maverick.briefing.models import (
    Ambiguity,
    ArchitectureDecision,
    ContrarianBrief,
    NavigatorBrief,
    ReconBrief,
    RiskFlag,
    StructuralistBrief,
)
from maverick.briefing.synthesis import synthesize_briefing


def _make_navigator(
    decisions: tuple[ArchitectureDecision, ...] = (),
) -> NavigatorBrief:
    return NavigatorBrief(
        architecture_decisions=decisions,
        module_structure="src/",
        integration_points=(),
        summary="Nav summary",
    )


def _make_structuralist() -> StructuralistBrief:
    return StructuralistBrief(entities=(), interfaces=(), summary="Struct summary")


def _make_recon(
    risks: tuple[RiskFlag, ...] = (),
    ambiguities: tuple[Ambiguity, ...] = (),
) -> ReconBrief:
    return ReconBrief(
        risks=risks,
        ambiguities=ambiguities,
        testing_strategy="Unit tests",
        summary="Recon summary",
    )


def _make_contrarian() -> ContrarianBrief:
    return ContrarianBrief(
        challenges=(),
        simplifications=(),
        consensus_points=(),
        summary="Contrarian summary",
    )


class TestSynthesizeBriefing:
    def test_basic_synthesis(self) -> None:
        doc = synthesize_briefing(
            "test-plan",
            _make_navigator(),
            _make_structuralist(),
            _make_recon(),
            _make_contrarian(),
        )
        assert doc.flight_plan_name == "test-plan"
        assert doc.created  # ISO timestamp is set

    def test_key_decisions_from_navigator_adrs(self) -> None:
        nav = _make_navigator(
            decisions=(
                ArchitectureDecision(
                    title="Use REST",
                    decision="REST API",
                    rationale="Simplicity",
                    alternatives_considered=("GraphQL",),
                ),
                ArchitectureDecision(
                    title="Use PostgreSQL",
                    decision="PostgreSQL",
                    rationale="Reliability",
                    alternatives_considered=(),
                ),
            )
        )
        doc = synthesize_briefing(
            "plan", nav, _make_structuralist(), _make_recon(), _make_contrarian()
        )
        assert doc.key_decisions == ("Use REST", "Use PostgreSQL")

    def test_key_risks_from_high_severity_only(self) -> None:
        recon = _make_recon(
            risks=(
                RiskFlag(description="Minor issue", severity="low", mitigation="Ignore"),
                RiskFlag(description="Critical bug", severity="high", mitigation="Fix"),
                RiskFlag(description="Medium issue", severity="medium", mitigation="Watch"),
            )
        )
        doc = synthesize_briefing(
            "plan", _make_navigator(), _make_structuralist(), recon, _make_contrarian()
        )
        assert doc.key_risks == ("Critical bug",)

    def test_open_questions_from_ambiguities(self) -> None:
        recon = _make_recon(
            ambiguities=(
                Ambiguity(
                    question="What auth?",
                    context="No spec",
                    suggested_resolution="Use JWT",
                ),
            )
        )
        doc = synthesize_briefing(
            "plan", _make_navigator(), _make_structuralist(), recon, _make_contrarian()
        )
        assert doc.open_questions == ("What auth?",)

    def test_empty_inputs_produce_empty_synthesis(self) -> None:
        doc = synthesize_briefing(
            "empty",
            _make_navigator(),
            _make_structuralist(),
            _make_recon(),
            _make_contrarian(),
        )
        assert doc.key_decisions == ()
        assert doc.key_risks == ()
        assert doc.open_questions == ()

    def test_created_is_iso_format(self) -> None:
        doc = synthesize_briefing(
            "plan",
            _make_navigator(),
            _make_structuralist(),
            _make_recon(),
            _make_contrarian(),
        )
        # ISO format contains 'T' separator and timezone info
        assert "T" in doc.created

    def test_all_briefs_preserved(self) -> None:
        nav = _make_navigator()
        struct = _make_structuralist()
        recon = _make_recon()
        contrarian = _make_contrarian()
        doc = synthesize_briefing("plan", nav, struct, recon, contrarian)
        assert doc.navigator is nav
        assert doc.structuralist is struct
        assert doc.recon is recon
        assert doc.contrarian is contrarian
