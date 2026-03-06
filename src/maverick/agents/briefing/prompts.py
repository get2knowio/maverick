"""Shared prompt builders for Briefing Room agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from maverick.library.actions.decompose import _format_codebase_context

if TYPE_CHECKING:
    from maverick.briefing.models import NavigatorBrief, ReconBrief, StructuralistBrief
    from maverick.library.actions.decompose import CodebaseContext


def build_briefing_prompt(
    flight_plan_content: str,
    codebase_context: CodebaseContext,
) -> str:
    """Build the shared prompt for Navigator, Structuralist, and Recon agents.

    Args:
        flight_plan_content: Raw flight plan Markdown.
        codebase_context: Gathered codebase file contents.

    Returns:
        Formatted prompt with flight plan and codebase context sections.
    """
    context_section = _format_codebase_context(codebase_context)
    return (
        f"## Flight Plan\n\n{flight_plan_content}"
        f"\n\n## Codebase Context\n\n{context_section}"
    )


def build_contrarian_prompt(
    flight_plan_content: str,
    navigator: NavigatorBrief,
    structuralist: StructuralistBrief,
    recon: ReconBrief,
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
    nav_json = navigator.model_dump_json(indent=2)
    struct_json = structuralist.model_dump_json(indent=2)
    recon_json = recon.model_dump_json(indent=2)
    return (
        f"## Flight Plan\n\n{flight_plan_content}"
        f"\n\n## Navigator Brief\n\n```json\n{nav_json}\n```"
        f"\n\n## Structuralist Brief\n\n```json\n{struct_json}\n```"
        f"\n\n## Recon Brief\n\n```json\n{recon_json}\n```"
    )
