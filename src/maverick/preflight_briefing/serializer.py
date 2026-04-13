"""Serialize raw briefing dicts to Markdown.

Replaces the previous Pydantic-based synthesis + serialization pipeline.
Agent briefs arrive as raw dicts from MCP tool calls — the MCP tool schemas
are the single source of truth for field names, not Pydantic models.
"""

from __future__ import annotations

import json
from typing import Any


def serialize_briefs_to_markdown(
    plan_name: str,
    *,
    scope: dict[str, Any] | None = None,
    analysis: dict[str, Any] | None = None,
    criteria: dict[str, Any] | None = None,
    challenge: dict[str, Any] | None = None,
) -> str:
    """Render raw briefing dicts as structured Markdown.

    Args:
        plan_name: Name of the flight plan.
        scope: Scopist agent output (submit_scope MCP tool args).
        analysis: Codebase analyst output (submit_analysis MCP tool args).
        criteria: Criteria writer output (submit_criteria MCP tool args).
        challenge: Contrarian output (submit_challenge MCP tool args).

    Returns:
        Markdown string suitable for prompt injection or disk persistence.
    """
    lines: list[str] = [f"# Pre-Flight Briefing: {plan_name}", ""]

    # --- Scope ---
    if scope:
        in_scope = scope.get("in_scope") or scope.get("in_scope_items") or []
        out_scope = scope.get("out_scope") or scope.get("out_of_scope_items") or []
        boundaries = scope.get("boundaries") or []
        summary = scope.get("summary") or scope.get("scope_rationale") or ""

        if summary:
            lines.extend(["## Scope Summary", "", summary, ""])
        if in_scope:
            lines.extend(["## In Scope", ""])
            lines.extend(f"- {item}" for item in in_scope)
            lines.append("")
        if out_scope:
            lines.extend(["## Out of Scope", ""])
            lines.extend(f"- {item}" for item in out_scope)
            lines.append("")
        if boundaries:
            lines.extend(["## Scope Boundaries", ""])
            lines.extend(f"- {item}" for item in boundaries)
            lines.append("")

    # --- Codebase Analysis ---
    if analysis:
        modules = analysis.get("modules") or analysis.get("relevant_modules") or []
        patterns = analysis.get("patterns") or analysis.get("existing_patterns") or []
        deps = analysis.get("dependencies") or analysis.get("integration_points") or []
        complexity = analysis.get("complexity_assessment") or ""
        summary = analysis.get("summary") or ""

        if summary:
            lines.extend(["## Codebase Analysis", "", summary, ""])
        if modules:
            lines.extend(["## Relevant Modules", ""])
            lines.extend(f"- {m}" for m in modules)
            lines.append("")
        if patterns:
            lines.extend(["## Existing Patterns", ""])
            lines.extend(f"- {p}" for p in patterns)
            lines.append("")
        if deps:
            lines.extend(["## Integration Points", ""])
            lines.extend(f"- {d}" for d in deps)
            lines.append("")
        if complexity:
            lines.extend(["## Complexity Assessment", "", complexity, ""])

    # --- Success Criteria ---
    if criteria:
        crit_list = criteria.get("criteria") or criteria.get("success_criteria") or []
        scenarios = criteria.get("test_scenarios") or []
        objective = criteria.get("objective_draft") or ""
        summary = criteria.get("summary") or ""

        if summary:
            lines.extend(["## Criteria Summary", "", summary, ""])
        if crit_list:
            lines.extend(["## Success Criteria", ""])
            lines.extend(f"- {c}" for c in crit_list)
            lines.append("")
        if objective:
            lines.extend(["## Objective Draft", "", objective, ""])
        if scenarios:
            lines.extend(["## Test Scenarios", ""])
            lines.extend(f"- {s}" for s in scenarios)
            lines.append("")

    # --- Contrarian Challenges ---
    if challenge:
        risks = challenge.get("risks") or challenge.get("scope_challenges") or []
        blind_spots = challenge.get("blind_spots") or challenge.get("criteria_challenges") or []
        questions = (
            challenge.get("open_questions") or challenge.get("missing_considerations") or []
        )
        consensus = challenge.get("consensus_points") or []
        summary = challenge.get("summary") or ""

        if summary:
            lines.extend(["## Contrarian Summary", "", summary, ""])
        if risks:
            lines.extend(["## Risks & Challenges", ""])
            lines.extend(f"- {r}" for r in risks)
            lines.append("")
        if blind_spots:
            lines.extend(["## Blind Spots", ""])
            lines.extend(f"- {b}" for b in blind_spots)
            lines.append("")
        if questions:
            lines.extend(["## Open Questions", ""])
            lines.extend(f"- {q}" for q in questions)
            lines.append("")
        if consensus:
            lines.extend(["## Consensus Points", ""])
            lines.extend(f"- {p}" for p in consensus)
            lines.append("")

    # Fallback: if we got dicts but couldn't extract any known fields,
    # dump the raw JSON so nothing is silently lost.
    if not any([scope, analysis, criteria, challenge]):
        return ""

    result = "\n".join(lines)
    if result.strip() == f"# Pre-Flight Briefing: {plan_name}":
        # Got dicts but no recognized fields — dump raw JSON
        parts = [f"# Pre-Flight Briefing: {plan_name}", ""]
        for label, data in [
            ("Scope", scope),
            ("Analysis", analysis),
            ("Criteria", criteria),
            ("Challenges", challenge),
        ]:
            if data:
                json_block = f"```json\n{json.dumps(data, indent=2)}\n```"
                parts.extend([f"## {label}", "", json_block, ""])
        return "\n".join(parts)

    return result
