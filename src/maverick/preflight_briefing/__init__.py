"""Pre-Flight Briefing Room — multi-agent PRD consultation pipeline.

Provides serialization for pre-flight briefing documents produced by
4 specialist agents (Scopist, CodebaseAnalyst, CriteriaWriter,
PreFlightContrarian).

Agent briefs are raw dicts from MCP tool calls — the MCP tool schemas
in ``maverick.tools.agent_inbox.schemas`` are the single source
of truth for field names.

Public API:
    serialize_briefs_to_markdown: Render raw brief dicts to Markdown.
"""

from __future__ import annotations

from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

__all__ = [
    "serialize_briefs_to_markdown",
]
