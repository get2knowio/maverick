"""Domain models for the Pre-Flight Briefing Room pipeline.

All models are frozen Pydantic BaseModel classes using tuples for
immutable sequences, matching the project convention for agent output
schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Scopist output
# ---------------------------------------------------------------------------


class ScopistBrief(BaseModel):
    """Scopist agent output — PRD scope analysis."""

    model_config = ConfigDict(frozen=True)

    in_scope_items: tuple[str, ...]
    out_of_scope_items: tuple[str, ...]
    boundaries: tuple[str, ...]
    scope_rationale: str
    summary: str


# ---------------------------------------------------------------------------
# CodebaseAnalyst output
# ---------------------------------------------------------------------------


class CodebaseAnalystBrief(BaseModel):
    """CodebaseAnalyst agent output — codebase mapping to PRD requirements."""

    model_config = ConfigDict(frozen=True)

    relevant_modules: tuple[str, ...]
    existing_patterns: tuple[str, ...]
    integration_points: tuple[str, ...]
    complexity_assessment: str
    summary: str


# ---------------------------------------------------------------------------
# CriteriaWriter output
# ---------------------------------------------------------------------------


class CriteriaWriterBrief(BaseModel):
    """CriteriaWriter agent output — success criteria and objective drafts."""

    model_config = ConfigDict(frozen=True)

    success_criteria: tuple[str, ...]
    objective_draft: str
    measurability_notes: str
    summary: str


# ---------------------------------------------------------------------------
# PreFlightContrarian output
# ---------------------------------------------------------------------------


class PreFlightContrarianBrief(BaseModel):
    """PreFlightContrarian agent output — challenges to the other 3 briefs."""

    model_config = ConfigDict(frozen=True)

    scope_challenges: tuple[str, ...]
    criteria_challenges: tuple[str, ...]
    missing_considerations: tuple[str, ...]
    consensus_points: tuple[str, ...]
    summary: str


# ---------------------------------------------------------------------------
# Synthesized document
# ---------------------------------------------------------------------------


class PreFlightBriefingDocument(BaseModel):
    """Synthesized pre-flight briefing combining all 4 agent briefs.

    The synthesis fields (key_scope_items, key_criteria, open_questions) are
    extracted by deterministic code in ``synthesis.py``, not by an agent.
    """

    model_config = ConfigDict(frozen=True)

    prd_name: str
    created: str  # ISO 8601 timestamp

    scopist: ScopistBrief
    codebase_analyst: CodebaseAnalystBrief
    criteria_writer: CriteriaWriterBrief
    contrarian: PreFlightContrarianBrief

    # Synthesis fields
    key_scope_items: tuple[str, ...]
    key_criteria: tuple[str, ...]
    open_questions: tuple[str, ...]
