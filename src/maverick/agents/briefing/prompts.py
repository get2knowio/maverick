"""Shared prompt builders for Briefing Room agents."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from maverick.library.actions.decompose import _format_codebase_context

if TYPE_CHECKING:
    from maverick.library.actions.decompose import CodebaseContext
    from maverick.library.actions.open_bead_analysis import OpenBeadAnalysisResult


def build_briefing_prompt(
    flight_plan_content: str,
    codebase_context: CodebaseContext,
    open_bead_context: OpenBeadAnalysisResult | None = None,
) -> str:
    """Build the shared prompt for Navigator, Structuralist, and Recon agents.

    Args:
        flight_plan_content: Raw flight plan Markdown.
        codebase_context: Gathered codebase file contents.
        open_bead_context: Optional open bead analysis for cross-plan awareness.

    Returns:
        Formatted prompt with flight plan, codebase context, and optionally
        open bead context sections.
    """
    context_section = _format_codebase_context(codebase_context)
    prompt = f"## Flight Plan\n\n{flight_plan_content}\n\n## Codebase Context\n\n{context_section}"

    if open_bead_context is not None:
        bead_section = open_bead_context.format_for_prompt()
        if bead_section:
            prompt += f"\n\n{bead_section}"

    return prompt


def build_contrarian_prompt(
    flight_plan_content: str,
    navigator: Any,
    structuralist: Any,
    recon: Any,
) -> str:
    """Build the prompt for the Contrarian agent.

    Embeds all 3 prior briefs as JSON so the contrarian can challenge them.

    Args:
        flight_plan_content: Raw flight plan Markdown.
        navigator: NavigatorBrief from the navigator agent.
        structuralist: StructuralistBrief from the structuralist agent.
        recon: ReconBrief from the recon agent.

    Returns:
        Formatted prompt with flight plan and all 3 agent briefs.
    """

    def _to_json(obj: Any) -> str:
        if hasattr(obj, "model_dump_json"):
            return obj.model_dump_json(indent=2)
        return json.dumps(obj, indent=2, default=str)

    nav_json = _to_json(navigator)
    struct_json = _to_json(structuralist)
    recon_json = _to_json(recon)
    return (
        f"## Flight Plan\n\n{flight_plan_content}"
        f"\n\n## Navigator Brief\n\n```json\n{nav_json}\n```"
        f"\n\n## Structuralist Brief\n\n```json\n{struct_json}\n```"
        f"\n\n## Recon Brief\n\n```json\n{recon_json}\n```"
    )
