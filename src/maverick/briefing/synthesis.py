"""Deterministic synthesis of agent briefs into a BriefingDocument.

Pure function — no I/O, no agent calls.
"""

from __future__ import annotations

from datetime import UTC, datetime

from maverick.briefing.models import (
    BriefingDocument,
    ContrarianBrief,
    NavigatorBrief,
    ReconBrief,
    StructuralistBrief,
)


def synthesize_briefing(
    flight_plan_name: str,
    navigator: NavigatorBrief,
    structuralist: StructuralistBrief,
    recon: ReconBrief,
    contrarian: ContrarianBrief,
) -> BriefingDocument:
    """Merge 4 agent briefs into a single BriefingDocument.

    Extraction rules:
    - key_decisions: titles from navigator's architecture decisions
    - key_risks: descriptions from recon's high-severity risks
    - open_questions: questions from recon's ambiguities

    Args:
        flight_plan_name: Name of the source flight plan.
        navigator: NavigatorBrief from the navigator agent.
        structuralist: StructuralistBrief from the structuralist agent.
        recon: ReconBrief from the recon agent.
        contrarian: ContrarianBrief from the contrarian agent.

    Returns:
        Synthesized BriefingDocument with all briefs and extracted fields.
    """
    key_decisions = tuple(adr.title for adr in navigator.architecture_decisions)

    key_risks = tuple(risk.description for risk in recon.risks if risk.severity == "high")

    open_questions = tuple(ambiguity.question for ambiguity in recon.ambiguities)

    return BriefingDocument(
        flight_plan_name=flight_plan_name,
        created=datetime.now(UTC).isoformat(),
        navigator=navigator,
        structuralist=structuralist,
        recon=recon,
        contrarian=contrarian,
        key_decisions=key_decisions,
        key_risks=key_risks,
        open_questions=open_questions,
    )
