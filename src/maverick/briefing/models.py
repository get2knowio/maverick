"""Domain models for the Briefing Room pipeline.

All models are frozen Pydantic BaseModel classes using tuples for
immutable sequences, matching the project convention for agent output
schemas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Navigator output
# ---------------------------------------------------------------------------


class ArchitectureDecision(BaseModel):
    """A single architecture decision record (ADR)."""

    model_config = ConfigDict(frozen=True)

    title: str
    decision: str
    rationale: str
    alternatives_considered: tuple[str, ...]


class NavigatorBrief(BaseModel):
    """Navigator agent output — architecture and module layout."""

    model_config = ConfigDict(frozen=True)

    architecture_decisions: tuple[ArchitectureDecision, ...]
    module_structure: str
    integration_points: tuple[str, ...]
    summary: str


# ---------------------------------------------------------------------------
# Structuralist output
# ---------------------------------------------------------------------------


class EntitySketch(BaseModel):
    """A proposed data entity with fields and relationships."""

    model_config = ConfigDict(frozen=True)

    name: str
    module_path: str
    fields: tuple[str, ...]  # "name: type" strings
    relationships: tuple[str, ...]


class InterfaceSketch(BaseModel):
    """A proposed interface/protocol with methods and consumers."""

    model_config = ConfigDict(frozen=True)

    name: str
    methods: tuple[str, ...]
    consumers: tuple[str, ...]


class StructuralistBrief(BaseModel):
    """Structuralist agent output — data models and interfaces."""

    model_config = ConfigDict(frozen=True)

    entities: tuple[EntitySketch, ...]
    interfaces: tuple[InterfaceSketch, ...]
    summary: str


# ---------------------------------------------------------------------------
# Recon output
# ---------------------------------------------------------------------------


class RiskFlag(BaseModel):
    """A risk identified during reconnaissance."""

    model_config = ConfigDict(frozen=True)

    description: str
    severity: Literal["low", "medium", "high"]
    mitigation: str


class Ambiguity(BaseModel):
    """An ambiguity or underspecified area in the flight plan."""

    model_config = ConfigDict(frozen=True)

    question: str
    context: str
    suggested_resolution: str


class ReconBrief(BaseModel):
    """Recon agent output — risks, ambiguities, and testing strategy."""

    model_config = ConfigDict(frozen=True)

    risks: tuple[RiskFlag, ...]
    ambiguities: tuple[Ambiguity, ...]
    testing_strategy: str
    summary: str
    suggested_cross_plan_dependencies: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Contrarian output
# ---------------------------------------------------------------------------


class Challenge(BaseModel):
    """A challenge to a proposed approach or assumption."""

    model_config = ConfigDict(frozen=True)

    target: str
    counter_argument: str
    recommendation: str


class Simplification(BaseModel):
    """A proposed simplification of the current approach."""

    model_config = ConfigDict(frozen=True)

    current_approach: str
    simpler_alternative: str
    tradeoff: str


class ContrarianBrief(BaseModel):
    """Contrarian agent output — challenges and simplifications."""

    model_config = ConfigDict(frozen=True)

    challenges: tuple[Challenge, ...]
    simplifications: tuple[Simplification, ...]
    consensus_points: tuple[str, ...]
    summary: str


# ---------------------------------------------------------------------------
# Synthesized document
# ---------------------------------------------------------------------------


class BriefingDocument(BaseModel):
    """Synthesized briefing combining all 4 agent briefs.

    The synthesis fields (key_decisions, key_risks, open_questions) are
    extracted by deterministic code in ``synthesis.py``, not by an agent.
    """

    model_config = ConfigDict(frozen=True)

    flight_plan_name: str
    created: str  # ISO 8601 timestamp

    navigator: NavigatorBrief
    structuralist: StructuralistBrief
    recon: ReconBrief
    contrarian: ContrarianBrief

    # Synthesis fields
    key_decisions: tuple[str, ...]
    key_risks: tuple[str, ...]
    open_questions: tuple[str, ...]
