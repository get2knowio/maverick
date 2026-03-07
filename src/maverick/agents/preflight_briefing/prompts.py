"""Shared prompt builders for Pre-Flight Briefing Room agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.preflight_briefing.models import (
        CodebaseAnalystBrief,
        CriteriaWriterBrief,
        ScopistBrief,
    )


def build_preflight_briefing_prompt(prd_content: str) -> str:
    """Build the shared prompt for Scopist, CodebaseAnalyst, and CriteriaWriter.

    Unlike the existing briefing room which passes codebase context in the
    prompt, the pre-flight agents get PLANNER_TOOLS to explore the codebase
    themselves (the PRD doesn't have in-scope file paths to pre-gather).

    Args:
        prd_content: Raw PRD Markdown content.

    Returns:
        Formatted prompt with PRD content section.
    """
    return f"## PRD Content\n\n{prd_content}"


def build_preflight_contrarian_prompt(
    prd_content: str,
    scopist: ScopistBrief,
    codebase_analyst: CodebaseAnalystBrief,
    criteria_writer: CriteriaWriterBrief,
) -> str:
    """Build the prompt for the PreFlightContrarian agent.

    Embeds all 3 prior briefs as JSON so the contrarian can challenge them.

    Args:
        prd_content: Raw PRD Markdown content.
        scopist: ScopistBrief from the scopist agent.
        codebase_analyst: CodebaseAnalystBrief from the codebase analyst agent.
        criteria_writer: CriteriaWriterBrief from the criteria writer agent.

    Returns:
        Formatted prompt with PRD and all 3 agent briefs.
    """
    scopist_json = scopist.model_dump_json(indent=2)
    analyst_json = codebase_analyst.model_dump_json(indent=2)
    criteria_json = criteria_writer.model_dump_json(indent=2)
    return (
        f"## PRD Content\n\n{prd_content}"
        f"\n\n## Scopist Brief\n\n```json\n{scopist_json}\n```"
        f"\n\n## Codebase Analyst Brief\n\n```json\n{analyst_json}\n```"
        f"\n\n## Criteria Writer Brief\n\n```json\n{criteria_json}\n```"
    )
