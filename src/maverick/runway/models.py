"""Data models for runway knowledge store.

Frozen Pydantic models for episodic records (JSONL) and query results.
Follows the pattern from ``maverick.models.review_models``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BeadOutcome",
    "CostEntry",
    "DecisionRecord",
    "FixAttemptRecord",
    "MatchFeedbackRecord",
    "RunwayIndex",
    "RunwayPassage",
    "RunwayQueryResult",
    "RunwayReviewFinding",
    "RunwayStatus",
]


# -----------------------------------------------------------------------------
# Episodic Models (JSONL records)
# -----------------------------------------------------------------------------


class BeadOutcome(BaseModel):
    """Episodic record of a completed bead execution.

    Attributes:
        bead_id: Unique bead identifier.
        epic_id: Parent epic identifier.
        flight_plan: Name of the originating flight plan.
        title: Human-readable bead title.
        timestamp: When the bead completed.
        files_changed: Files modified during this bead.
        validation_passed: Whether validation passed.
        review_findings_count: Number of review findings.
        review_fixed_count: Number of findings fixed.
        key_decisions: Notable decisions made during implementation.
        mistakes_caught: Mistakes identified and corrected.
    """

    model_config = ConfigDict(frozen=True)

    bead_id: str
    epic_id: str
    flight_plan: str = ""
    title: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    files_changed: list[str] = Field(default_factory=list)
    validation_passed: bool = False
    review_findings_count: int = 0
    review_fixed_count: int = 0
    key_decisions: list[str] = Field(default_factory=list)
    mistakes_caught: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeadOutcome:
        """Create BeadOutcome from dictionary."""
        return cls.model_validate(data)


class RunwayReviewFinding(BaseModel):
    """Episodic record of a single review finding.

    Attributes:
        finding_id: Unique finding identifier (e.g. "F001").
        bead_id: Bead this finding was raised against.
        reviewer: Which reviewer raised it ("spec" or "technical").
        severity: Finding severity level.
        category: Classification of the issue type.
        file_path: File path affected.
        description: Description of the finding.
        resolution: How the finding was resolved.
    """

    model_config = ConfigDict(frozen=True)

    finding_id: str
    bead_id: str
    reviewer: str = ""
    severity: str = ""
    category: str = ""
    file_path: str = ""
    description: str = ""
    resolution: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunwayReviewFinding:
        """Create RunwayReviewFinding from dictionary."""
        return cls.model_validate(data)


class FixAttemptRecord(BaseModel):
    """Episodic record of a single fix attempt.

    Attributes:
        attempt_id: Unique attempt identifier.
        finding_id: Finding this attempt addressed.
        bead_id: Bead during which the attempt was made.
        approach: Description of the fix approach taken.
        succeeded: Whether the fix succeeded.
        failure_reason: Reason for failure (empty if succeeded).
    """

    model_config = ConfigDict(frozen=True)

    attempt_id: str
    finding_id: str
    bead_id: str
    approach: str = ""
    succeeded: bool = False
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FixAttemptRecord:
        """Create FixAttemptRecord from dictionary."""
        return cls.model_validate(data)


class CostEntry(BaseModel):
    """Episodic record of one airframe-routed model invocation.

    Captured per send by :meth:`Agent._emit_cost` so workflow runs can
    be aggregated for cost / token reporting without re-parsing
    structlog files.

    Attributes:
        timestamp: ISO timestamp when the send completed.
        actor: Logging tag for the originating actor (e.g.
            ``"reviewer[fly-supervisor:reviewer]"``).
        tier: Tier name resolved for this send (``"review"`` etc., or
            ``"inline"`` when an explicit StepConfig override was used).
        provider_id: Airframe canonical ``provider_id``
            (``"claude"`` / ``"github-copilot"`` / etc.).
        model_id: Vendor model identifier from the runtime's binding.
        cost_usd: Dollar cost reported by the runtime (None when the
            adapter can't compute one).
        input_tokens: Prompt tokens consumed.
        output_tokens: Completion tokens emitted.
        cache_read_tokens: Provider cache-hit token count (Anthropic
            primarily; ``0`` elsewhere).
        cache_write_tokens: Provider cache-write token count.
        finish: Stop reason reported by the adapter
            (``"end_turn"`` / ``"stop"`` / ``"length"`` / ``"tool_calls"``).
        bead_id: Optional bead identifier when known from the workflow
            context. Empty for non-bead-scoped sends.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    actor: str = ""
    tier: str = ""
    provider_id: str | None = None
    model_id: str | None = None
    cost_usd: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    finish: str | None = None
    bead_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CostEntry:
        """Create CostEntry from dictionary."""
        return cls.model_validate(data)


class DecisionRecord(BaseModel):
    """Append-only record of one terminal human resolution of an assumption.

    Lives in ``.maverick/runway/decisions.jsonl`` (store root, not
    ``episodic/`` — never pruned by consolidation; see
    ``specs/055-learned-assumption-resolution/data-model.md``). Written only
    by the human review surfaces (``maverick review``, single and bulk
    waive) — never by scheduler auto-waives or auto-resolution (FR-005).

    Collapse rule (read side): group by ``source_entry_id``, latest
    ``resolved_at`` wins as the authoritative version; earlier lines remain
    as history (FR-003).

    Attributes:
        source_entry_id: Assumption bead id the decision resolved — the
            decision's stable identity.
        question: Original question text (from the entry's ``## Question``
            section).
        normalized_question: ``matching.normalize_question(question)`` at
            the time of writing, carried by the JSONL schema
            (contracts/decision-records.md) so the corpus is greppable and
            diffable on its own. Deliberately **not** a matching input:
            ``evaluate_suggestion`` re-normalizes ``question`` on every
            comparison instead, so rows written before a normalizer change
            can never silently score against stale text. Treat this field
            as derived output, and don't optimize matching to read it.
        adopted_answer: What the agent had adopted.
        resolution_type: ``"answered"`` or ``"waived"``.
        resolution: Answer text, or waive reason.
        severity: Entry severity at resolution (``low``/``medium``/``high``).
        owner_spec: Owning spec of the resolved entry.
        resolved_by: Git user name (same source as ``waived_by`` today).
        resolved_at: UTC ISO-8601 timestamp.
    """

    model_config = ConfigDict(frozen=True)

    source_entry_id: str
    question: str
    normalized_question: str
    adopted_answer: str
    resolution_type: Literal["answered", "waived"]
    resolution: str
    severity: str
    owner_spec: str
    resolved_by: str
    resolved_at: str

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionRecord:
        """Create DecisionRecord from dictionary."""
        return cls.model_validate(data)


class MatchFeedbackRecord(BaseModel):
    """Append-only record of a human's accept/reject decision on one
    presented suggestion — the feedback loop that penalizes a pairing's
    future match confidence (User Story 3, 055-learned-assumption-resolution).

    Lives in ``.maverick/runway/match-feedback.jsonl`` (store root, same
    never-pruned placement as ``decisions.jsonl`` — spec 055 R1). Written
    only by the human review surfaces, mirroring :class:`DecisionRecord`.

    Attributes:
        normalized_question: ``matching.normalize_question(question)`` of
            the entry the suggestion was presented against — paired with
            ``source_entry_id`` to identify which (entry, candidate)
            pairing this feedback penalizes/rewards.
        source_entry_id: The decision-corpus entry the presented suggestion
            matched.
        outcome: ``"accepted"`` or ``"rejected"``.
        recorded_at: UTC ISO-8601 timestamp the feedback was recorded.
    """

    model_config = ConfigDict(frozen=True)

    normalized_question: str
    source_entry_id: str
    outcome: Literal["accepted", "rejected"]
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchFeedbackRecord:
        """Create MatchFeedbackRecord from dictionary."""
        return cls.model_validate(data)


# -----------------------------------------------------------------------------
# Index Model
# -----------------------------------------------------------------------------


class RunwayIndex(BaseModel):
    """Runway index metadata stored in ``index.json``.

    Attributes:
        version: Schema version for forward compatibility.
        last_consolidated: ISO timestamp of last consolidation run.
        entities: Known entity names referenced across runway.
        episodic_counts: Record counts per episodic file.
        suppressed_patterns: Patterns the user has deleted from AGENTS.md.
    """

    model_config = ConfigDict(frozen=True)

    version: int = 1
    last_consolidated: str = ""
    entities: list[str] = Field(default_factory=list)
    episodic_counts: dict[str, int] = Field(default_factory=dict)
    suppressed_patterns: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunwayIndex:
        """Create RunwayIndex from dictionary."""
        return cls.model_validate(data)


# -----------------------------------------------------------------------------
# Query Models
# -----------------------------------------------------------------------------


class RunwayPassage(BaseModel):
    """A single passage returned from a runway query.

    Attributes:
        source_file: Relative path within the runway directory.
        content: Text content of the passage.
        score: BM25 relevance score.
        line_start: Starting line number in the source file.
        line_end: Ending line number in the source file.
    """

    model_config = ConfigDict(frozen=True)

    source_file: str
    content: str
    score: float = 0.0
    line_start: int = 0
    line_end: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()


class RunwayQueryResult(BaseModel):
    """Envelope for runway query results.

    Attributes:
        passages: Ranked passages matching the query.
        query: The original query text.
        total_candidates: Total passages considered before ranking.
    """

    model_config = ConfigDict(frozen=True)

    passages: list[RunwayPassage] = Field(default_factory=list)
    query: str = ""
    total_candidates: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()


# -----------------------------------------------------------------------------
# Status Model
# -----------------------------------------------------------------------------


class RunwayStatus(BaseModel):
    """Status summary of a runway store.

    Attributes:
        initialized: Whether the runway directory structure exists.
        bead_outcome_count: Number of bead outcome records.
        review_finding_count: Number of review finding records.
        fix_attempt_count: Number of fix attempt records.
        semantic_files: List of semantic markdown files.
        total_size_bytes: Total size of all runway files.
        last_consolidated: ISO timestamp of last consolidation.
    """

    model_config = ConfigDict(frozen=True)

    initialized: bool = False
    bead_outcome_count: int = 0
    review_finding_count: int = 0
    fix_attempt_count: int = 0
    semantic_files: list[str] = Field(default_factory=list)
    total_size_bytes: int = 0
    last_consolidated: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Alias for ``model_dump()``."""
        return self.model_dump()
