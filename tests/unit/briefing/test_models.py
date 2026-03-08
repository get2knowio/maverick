"""Unit tests for maverick.briefing.models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.briefing.models import (
    Ambiguity,
    ArchitectureDecision,
    BriefingDocument,
    Challenge,
    ContrarianBrief,
    EntitySketch,
    InterfaceSketch,
    NavigatorBrief,
    ReconBrief,
    RiskFlag,
    Simplification,
    StructuralistBrief,
)

# ---------------------------------------------------------------------------
# ArchitectureDecision
# ---------------------------------------------------------------------------


class TestArchitectureDecision:
    def test_valid_construction(self) -> None:
        adr = ArchitectureDecision(
            title="Use Pydantic",
            decision="Use Pydantic for validation",
            rationale="Type safety",
            alternatives_considered=("dataclasses", "attrs"),
        )
        assert adr.title == "Use Pydantic"
        assert len(adr.alternatives_considered) == 2

    def test_frozen(self) -> None:
        adr = ArchitectureDecision(
            title="T", decision="D", rationale="R", alternatives_considered=()
        )
        with pytest.raises(ValidationError):
            adr.title = "new"  # type: ignore[misc]

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            ArchitectureDecision(title="T", decision="D")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# NavigatorBrief
# ---------------------------------------------------------------------------


class TestNavigatorBrief:
    def test_valid_construction(self) -> None:
        brief = NavigatorBrief(
            architecture_decisions=(),
            module_structure="src/auth/",
            integration_points=("API gateway",),
            summary="Architecture overview",
        )
        assert brief.summary == "Architecture overview"
        assert brief.integration_points == ("API gateway",)

    def test_frozen(self) -> None:
        brief = NavigatorBrief(
            architecture_decisions=(),
            module_structure="",
            integration_points=(),
            summary="S",
        )
        with pytest.raises(ValidationError):
            brief.summary = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EntitySketch / InterfaceSketch / StructuralistBrief
# ---------------------------------------------------------------------------


class TestStructuralistModels:
    def test_entity_sketch(self) -> None:
        entity = EntitySketch(
            name="User",
            module_path="src/models.py",
            fields=("email: str", "name: str"),
            relationships=("has_many: Post",),
        )
        assert entity.name == "User"
        assert len(entity.fields) == 2

    def test_interface_sketch(self) -> None:
        iface = InterfaceSketch(
            name="Repository",
            methods=("get(id: str) -> Model",),
            consumers=("UserService",),
        )
        assert iface.name == "Repository"

    def test_structuralist_brief(self) -> None:
        brief = StructuralistBrief(
            entities=(),
            interfaces=(),
            summary="Data model overview",
        )
        assert brief.summary == "Data model overview"


# ---------------------------------------------------------------------------
# RiskFlag / Ambiguity / ReconBrief
# ---------------------------------------------------------------------------


class TestReconModels:
    def test_risk_flag_valid_severities(self) -> None:
        for sev in ("low", "medium", "high"):
            risk = RiskFlag(description="D", severity=sev, mitigation="M")  # type: ignore[arg-type]
            assert risk.severity == sev

    def test_risk_flag_invalid_severity(self) -> None:
        with pytest.raises(ValidationError):
            RiskFlag(description="D", severity="critical", mitigation="M")  # type: ignore[arg-type]

    def test_ambiguity(self) -> None:
        a = Ambiguity(
            question="What auth?",
            context="No auth specified",
            suggested_resolution="Use JWT",
        )
        assert a.question == "What auth?"

    def test_recon_brief(self) -> None:
        brief = ReconBrief(
            risks=(),
            ambiguities=(),
            testing_strategy="Unit + integration",
            summary="Risk analysis",
        )
        assert brief.testing_strategy == "Unit + integration"

    def test_recon_brief_suggested_cross_plan_deps_default(self) -> None:
        brief = ReconBrief(
            risks=(),
            ambiguities=(),
            testing_strategy="test",
            summary="summary",
        )
        assert brief.suggested_cross_plan_dependencies == ()

    def test_recon_brief_suggested_cross_plan_deps(self) -> None:
        brief = ReconBrief(
            risks=(),
            ambiguities=(),
            testing_strategy="test",
            summary="summary",
            suggested_cross_plan_dependencies=("add-auth", "add-db"),
        )
        assert brief.suggested_cross_plan_dependencies == (
            "add-auth",
            "add-db",
        )


# ---------------------------------------------------------------------------
# Challenge / Simplification / ContrarianBrief
# ---------------------------------------------------------------------------


class TestContrarianModels:
    def test_challenge(self) -> None:
        c = Challenge(
            target="Microservices",
            counter_argument="Over-engineering",
            recommendation="Use monolith",
        )
        assert c.target == "Microservices"

    def test_simplification(self) -> None:
        s = Simplification(
            current_approach="Custom ORM",
            simpler_alternative="SQLAlchemy",
            tradeoff="Less control",
        )
        assert s.current_approach == "Custom ORM"

    def test_contrarian_brief(self) -> None:
        brief = ContrarianBrief(
            challenges=(),
            simplifications=(),
            consensus_points=("Use Python",),
            summary="Contrarian review",
        )
        assert brief.consensus_points == ("Use Python",)


# ---------------------------------------------------------------------------
# BriefingDocument
# ---------------------------------------------------------------------------


class TestBriefingDocument:
    def _make_doc(self) -> BriefingDocument:
        return BriefingDocument(
            flight_plan_name="test-plan",
            created="2026-03-06T00:00:00+00:00",
            navigator=NavigatorBrief(
                architecture_decisions=(),
                module_structure="",
                integration_points=(),
                summary="nav",
            ),
            structuralist=StructuralistBrief(
                entities=(), interfaces=(), summary="struct"
            ),
            recon=ReconBrief(
                risks=(),
                ambiguities=(),
                testing_strategy="",
                summary="recon",
            ),
            contrarian=ContrarianBrief(
                challenges=(),
                simplifications=(),
                consensus_points=(),
                summary="contrarian",
            ),
            key_decisions=("Use Pydantic",),
            key_risks=("API breakage",),
            open_questions=("Auth mechanism?",),
        )

    def test_valid_construction(self) -> None:
        doc = self._make_doc()
        assert doc.flight_plan_name == "test-plan"
        assert len(doc.key_decisions) == 1

    def test_frozen(self) -> None:
        doc = self._make_doc()
        with pytest.raises(ValidationError):
            doc.flight_plan_name = "new"  # type: ignore[misc]

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            BriefingDocument(  # type: ignore[call-arg]
                flight_plan_name="test",
                created="2026-03-06",
            )

    def test_empty_synthesis_fields(self) -> None:
        doc = BriefingDocument(
            flight_plan_name="empty",
            created="2026-03-06T00:00:00+00:00",
            navigator=NavigatorBrief(
                architecture_decisions=(),
                module_structure="",
                integration_points=(),
                summary="",
            ),
            structuralist=StructuralistBrief(entities=(), interfaces=(), summary=""),
            recon=ReconBrief(risks=(), ambiguities=(), testing_strategy="", summary=""),
            contrarian=ContrarianBrief(
                challenges=(),
                simplifications=(),
                consensus_points=(),
                summary="",
            ),
            key_decisions=(),
            key_risks=(),
            open_questions=(),
        )
        assert doc.key_decisions == ()
        assert doc.key_risks == ()
        assert doc.open_questions == ()
