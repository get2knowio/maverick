"""Shared prompt builders for Pre-Flight Briefing Room agents."""

from __future__ import annotations

import json
from typing import Any


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
    scopist: dict[str, Any],
    codebase_analyst: dict[str, Any],
    criteria_writer: dict[str, Any],
) -> str:
    """Build the prompt for the PreFlightContrarian agent.

    Embeds all 3 prior briefs as JSON so the contrarian can challenge them.

    Args:
        prd_content: Raw PRD Markdown content.
        scopist: Raw dict from scopist MCP tool call.
        codebase_analyst: Raw dict from codebase analyst MCP tool call.
        criteria_writer: Raw dict from criteria writer MCP tool call.

    Returns:
        Formatted prompt with PRD and all 3 agent briefs.
    """
    scopist_json = json.dumps(scopist, indent=2)
    analyst_json = json.dumps(codebase_analyst, indent=2)
    criteria_json = json.dumps(criteria_writer, indent=2)
    return (
        f"## PRD Content\n\n{prd_content}"
        f"\n\n## Scopist Brief\n\n```json\n{scopist_json}\n```"
        f"\n\n## Codebase Analyst Brief\n\n```json\n{analyst_json}\n```"
        f"\n\n## Criteria Writer Brief\n\n```json\n{criteria_json}\n```"
    )
