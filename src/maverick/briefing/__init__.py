"""Briefing Room — multi-agent consultation pipeline.

Provides domain models, deterministic synthesis, and serialization for
briefing documents produced by the 4 specialist agents (Navigator,
Structuralist, Recon, Contrarian).

Public API:
    BriefingDocument: Synthesized briefing with all agent briefs.
    synthesize_briefing: Deterministic merge of 4 briefs into a document.
    serialize_briefing: Render a BriefingDocument to Markdown+YAML.
"""

from __future__ import annotations

from maverick.briefing.models import (
    Ambiguity,
    ArchitectureDecision,
    BriefingDocument,
    Challenge,
    ContrarianBrief,
    EntitySketch,
    InterfaceSketch,
    NavigatorBrief,
    ReconBrief,
    RiskFlag,
    Simplification,
    StructuralistBrief,
)
from maverick.briefing.serializer import serialize_briefing
from maverick.briefing.synthesis import synthesize_briefing

__all__ = [
    "Ambiguity",
    "ArchitectureDecision",
    "BriefingDocument",
    "Challenge",
    "ContrarianBrief",
    "EntitySketch",
    "InterfaceSketch",
    "NavigatorBrief",
    "ReconBrief",
    "RiskFlag",
    "Simplification",
    "StructuralistBrief",
    "serialize_briefing",
    "synthesize_briefing",
]
