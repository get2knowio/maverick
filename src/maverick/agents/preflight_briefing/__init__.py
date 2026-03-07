"""Pre-Flight Briefing Room agents — 4 specialists for PRD analysis.

Public API:
    ScopistAgent: Scope analysis for PRD requirements.
    CodebaseAnalystAgent: Codebase mapping to PRD requirements.
    CriteriaWriterAgent: Success criteria and objective drafting.
    PreFlightContrarianAgent: Challenges to the other 3 agents' briefs.
"""

from __future__ import annotations

from maverick.agents.preflight_briefing.codebase_analyst import CodebaseAnalystAgent
from maverick.agents.preflight_briefing.contrarian import PreFlightContrarianAgent
from maverick.agents.preflight_briefing.criteria_writer import CriteriaWriterAgent
from maverick.agents.preflight_briefing.scopist import ScopistAgent

__all__ = [
    "CodebaseAnalystAgent",
    "CriteriaWriterAgent",
    "PreFlightContrarianAgent",
    "ScopistAgent",
]
