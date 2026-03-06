"""Briefing Room agents — 4 specialist agents for flight plan analysis.

Public API:
    NavigatorAgent: Architecture, module layout, ADRs.
    StructuralistAgent: Data models, interfaces, type contracts.
    ReconAgent: Risks, ambiguities, testing strategy.
    ContrarianAgent: Challenges, simplifications, consensus.
"""

from __future__ import annotations

from maverick.agents.briefing.contrarian import ContrarianAgent
from maverick.agents.briefing.navigator import NavigatorAgent
from maverick.agents.briefing.recon import ReconAgent
from maverick.agents.briefing.structuralist import StructuralistAgent

__all__ = [
    "ContrarianAgent",
    "NavigatorAgent",
    "ReconAgent",
    "StructuralistAgent",
]
