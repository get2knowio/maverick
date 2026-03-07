"""Pre-Flight Briefing Room — multi-agent PRD consultation pipeline.

Provides domain models, deterministic synthesis, and serialization for
pre-flight briefing documents produced by 4 specialist agents (Scopist,
CodebaseAnalyst, CriteriaWriter, PreFlightContrarian).

Public API:
    PreFlightBriefingDocument: Synthesized briefing with all agent briefs.
    synthesize_preflight_briefing: Deterministic merge of 4 briefs into a document.
    serialize_preflight_briefing: Render a PreFlightBriefingDocument to Markdown.
"""

from __future__ import annotations

from maverick.preflight_briefing.models import (
    CodebaseAnalystBrief,
    CriteriaWriterBrief,
    PreFlightBriefingDocument,
    PreFlightContrarianBrief,
    ScopistBrief,
)
from maverick.preflight_briefing.serializer import serialize_preflight_briefing
from maverick.preflight_briefing.synthesis import synthesize_preflight_briefing

__all__ = [
    "CodebaseAnalystBrief",
    "CriteriaWriterBrief",
    "PreFlightBriefingDocument",
    "PreFlightContrarianBrief",
    "ScopistBrief",
    "serialize_preflight_briefing",
    "synthesize_preflight_briefing",
]
