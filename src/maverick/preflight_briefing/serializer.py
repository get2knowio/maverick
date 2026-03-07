"""Serialize a PreFlightBriefingDocument to Markdown.

Follows the ``src/maverick/briefing/serializer.py`` pattern.
"""

from __future__ import annotations

from maverick.preflight_briefing.models import PreFlightBriefingDocument


def serialize_preflight_briefing(doc: PreFlightBriefingDocument) -> str:
    """Render a PreFlightBriefingDocument as Markdown.

    Args:
        doc: The pre-flight briefing document to serialize.

    Returns:
        Markdown string suitable for prompt injection or disk persistence.
    """
    lines: list[str] = []

    lines.append(f"# Pre-Flight Briefing: {doc.prd_name}")
    lines.append("")

    # --- Summaries ---
    lines.append("## Agent Summaries")
    lines.append("")
    lines.append("### Scopist")
    lines.append("")
    lines.append(doc.scopist.summary)
    lines.append("")
    lines.append("### Codebase Analyst")
    lines.append("")
    lines.append(doc.codebase_analyst.summary)
    lines.append("")
    lines.append("### Criteria Writer")
    lines.append("")
    lines.append(doc.criteria_writer.summary)
    lines.append("")
    lines.append("### Contrarian")
    lines.append("")
    lines.append(doc.contrarian.summary)
    lines.append("")

    # --- Key Scope Items ---
    if doc.key_scope_items:
        lines.append("## Key Scope Items")
        lines.append("")
        for item in doc.key_scope_items:
            lines.append(f"- {item}")
        lines.append("")

    # --- Out of Scope ---
    if doc.scopist.out_of_scope_items:
        lines.append("## Out of Scope")
        lines.append("")
        for item in doc.scopist.out_of_scope_items:
            lines.append(f"- {item}")
        lines.append("")

    # --- Boundaries ---
    if doc.scopist.boundaries:
        lines.append("## Scope Boundaries")
        lines.append("")
        for item in doc.scopist.boundaries:
            lines.append(f"- {item}")
        lines.append("")

    # --- Key Criteria ---
    if doc.key_criteria:
        lines.append("## Success Criteria")
        lines.append("")
        for criterion in doc.key_criteria:
            lines.append(f"- {criterion}")
        lines.append("")

    # --- Objective Draft ---
    if doc.criteria_writer.objective_draft:
        lines.append("## Objective Draft")
        lines.append("")
        lines.append(doc.criteria_writer.objective_draft)
        lines.append("")

    # --- Codebase Analysis ---
    if doc.codebase_analyst.relevant_modules:
        lines.append("## Relevant Modules")
        lines.append("")
        for module in doc.codebase_analyst.relevant_modules:
            lines.append(f"- {module}")
        lines.append("")

    if doc.codebase_analyst.existing_patterns:
        lines.append("## Existing Patterns")
        lines.append("")
        for pattern in doc.codebase_analyst.existing_patterns:
            lines.append(f"- {pattern}")
        lines.append("")

    if doc.codebase_analyst.integration_points:
        lines.append("## Integration Points")
        lines.append("")
        for point in doc.codebase_analyst.integration_points:
            lines.append(f"- {point}")
        lines.append("")

    if doc.codebase_analyst.complexity_assessment:
        lines.append("## Complexity Assessment")
        lines.append("")
        lines.append(doc.codebase_analyst.complexity_assessment)
        lines.append("")

    # --- Contrarian Challenges ---
    if doc.contrarian.scope_challenges:
        lines.append("## Scope Challenges")
        lines.append("")
        for challenge in doc.contrarian.scope_challenges:
            lines.append(f"- {challenge}")
        lines.append("")

    if doc.contrarian.criteria_challenges:
        lines.append("## Criteria Challenges")
        lines.append("")
        for challenge in doc.contrarian.criteria_challenges:
            lines.append(f"- {challenge}")
        lines.append("")

    # --- Open Questions ---
    if doc.open_questions:
        lines.append("## Open Questions")
        lines.append("")
        for question in doc.open_questions:
            lines.append(f"- {question}")
        lines.append("")

    # --- Consensus ---
    if doc.contrarian.consensus_points:
        lines.append("## Consensus Points")
        lines.append("")
        for point in doc.contrarian.consensus_points:
            lines.append(f"- {point}")
        lines.append("")

    return "\n".join(lines)
