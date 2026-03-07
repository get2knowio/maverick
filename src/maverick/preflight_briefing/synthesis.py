"""Deterministic synthesis of agent briefs into a PreFlightBriefingDocument.

Pure function — no I/O, no agent calls.
"""

from __future__ import annotations

from datetime import UTC, datetime

from maverick.preflight_briefing.models import (
    CodebaseAnalystBrief,
    CriteriaWriterBrief,
    PreFlightBriefingDocument,
    PreFlightContrarianBrief,
    ScopistBrief,
)


def synthesize_preflight_briefing(
    prd_name: str,
    scopist: ScopistBrief,
    codebase_analyst: CodebaseAnalystBrief,
    criteria_writer: CriteriaWriterBrief,
    contrarian: PreFlightContrarianBrief,
) -> PreFlightBriefingDocument:
    """Merge 4 agent briefs into a single PreFlightBriefingDocument.

    Extraction rules:
    - key_scope_items: scopist's in_scope_items
    - key_criteria: criteria_writer's success_criteria
    - open_questions: contrarian's missing_considerations

    Args:
        prd_name: Name of the source PRD.
        scopist: ScopistBrief from the scopist agent.
        codebase_analyst: CodebaseAnalystBrief from the codebase analyst agent.
        criteria_writer: CriteriaWriterBrief from the criteria writer agent.
        contrarian: PreFlightContrarianBrief from the contrarian agent.

    Returns:
        Synthesized PreFlightBriefingDocument with all briefs and extracted fields.
    """
    key_scope_items = scopist.in_scope_items
    key_criteria = criteria_writer.success_criteria
    open_questions = contrarian.missing_considerations

    return PreFlightBriefingDocument(
        prd_name=prd_name,
        created=datetime.now(UTC).isoformat(),
        scopist=scopist,
        codebase_analyst=codebase_analyst,
        criteria_writer=criteria_writer,
        contrarian=contrarian,
        key_scope_items=key_scope_items,
        key_criteria=key_criteria,
        open_questions=open_questions,
    )
