"""Pre-Flight Briefing Room — multi-agent PRD consultation pipeline.

Provides serialization for pre-flight briefing documents produced by
4 specialist agents (Scopist, CodebaseAnalyst, CriteriaWriter,
PreFlightContrarian).

Agent briefs originate as typed payloads (see :mod:`maverick.payloads`)
from the OpenCode-backed ``BriefingActor``s. The serializer below
accepts the dumped dict form so existing callers don't have to thread
the typed objects through.

Public API:
    serialize_briefs_to_markdown: Render raw brief dicts to Markdown.
"""

from __future__ import annotations

from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

__all__ = [
    "serialize_briefs_to_markdown",
]
