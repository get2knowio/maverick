"""Typed models for the spec-chain workflow (`maverick spec`).

Persisted state (``ChainState``, nested ``StepRecord``), the clarify
answering-path convergence type (``ClarifyDecision``), the agent
structured-output schema (``StepReport`` + ``ReportedQuestion`` /
``ReportedFinding``), the analyze-finding-to-remediation-bead type
(``AnalyzeFinding``), and the CLI-facing summary (``SpecChainReport``).

See specs/050-headless-spec-chain/data-model.md for the authoritative
contract.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maverick.assumptions.models import Severity
from maverick.workflows.spec_chain.constants import CHAIN_STEP_ORDER, ChainStep

__all__ = [
    "AnalyzeFinding",
    "ChainState",
    "ChainStatus",
    "ClarifyDecision",
    "ReportedFinding",
    "ReportedQuestion",
    "SpecChainReport",
    "StepRecord",
    "StepReport",
    "StepStatus",
    "next_step",
]

#: Feature name: non-empty, filesystem-safe slug (data-model.md
#: "Validation rules"). Rejects path separators and leading dots so a
#: feature name can never traverse outside `specs/` or the hidden
#: workspace root.
_FEATURE_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

StepStatus = Literal["pending", "in_progress", "succeeded", "failed", "skipped"]
ChainStatus = Literal["running", "halted", "completed", "failed"]


class StepRecord(BaseModel):
    """Outcome of one attempted chain step, nested in :class:`ChainState`."""

    model_config = ConfigDict(frozen=True)

    step: ChainStep = Field(description="Which chain step this record tracks")
    status: StepStatus = Field(description="Current status of this step")
    attempts: int = Field(default=0, description="Tenacity-visible attempt count")
    artifacts: list[str] = Field(
        default_factory=list,
        description="Feature-dir-relative paths landed by this step",
    )
    landed: bool = Field(
        default=False,
        description="Whether artifacts were synced to the user checkout",
    )
    error: str | None = Field(default=None, description="Classified failure summary")
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)


@dataclass(frozen=True, slots=True)
class ClarifyDecision:
    """One clarify question plus the answer adopted on the user's behalf.

    The convergence type for both answering paths (R2): interception and
    non-interactive-upgrade decisions both produce this shape before being
    filed via ``record_standalone_assumption``.
    """

    question: str
    adopted_answer: str
    alternatives: tuple[str, ...]
    severity: Severity
    severity_defaulted: bool
    path: Literal["interception", "non_interactive"]
    ledger_bead_id: str | None = None


class ChainState(BaseModel):
    """Persisted spec-chain run state.

    Written atomically to ``.maverick/runs/<run-id>/spec-chain.json`` after
    every step transition (see contracts/chain-state.md).
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, description="Guards future migrations")
    run_id: str = Field(description="Matches the .maverick/runs/ directory name")
    feature: str = Field(description="User-supplied feature name (resume key)")
    feature_dir: str | None = Field(
        default=None,
        description="specs/NNN-<feature> allocated by specify; None until specify lands",
    )
    prd_path: str = Field(description="User-supplied PRD path (checkout-relative)")
    prd_digest: str = Field(description="sha256 of PRD content at chain start")
    workspace_path: str = Field(description="Hidden workspace root for this run")
    status: ChainStatus = Field(description="Overall chain status")
    steps: dict[ChainStep, StepRecord] = Field(
        default_factory=dict, description="One record per attempted step"
    )
    clarify_decisions: list[ClarifyDecision] = Field(
        default_factory=list, description="Filed clarify decisions (audit copy)"
    )
    remediation_bead_ids: list[str] = Field(
        default_factory=list, description="Created remediation-finding bead ids"
    )
    started_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _check_step_progression_invariant(self) -> ChainState:
        """A step may be ``in_progress`` only if all prior steps succeeded."""
        for step, record in self.steps.items():
            if record.status != "in_progress":
                continue
            idx = CHAIN_STEP_ORDER.index(step)
            for prior in CHAIN_STEP_ORDER[:idx]:
                prior_record = self.steps.get(prior)
                if prior_record is None or prior_record.status != "succeeded":
                    raise ValueError(
                        f"step {step!r} is in_progress but prior step {prior!r} has not succeeded"
                    )
        return self

    @model_validator(mode="after")
    def _check_feature_is_filesystem_safe_slug(self) -> ChainState:
        if not self.feature or not _FEATURE_SLUG_RE.match(self.feature):
            raise ValueError(
                f"feature must be a non-empty, filesystem-safe slug: {self.feature!r}"
            )
        return self


def next_step(steps: Mapping[ChainStep, StepRecord]) -> ChainStep | None:
    """Derive the next step to run from :data:`CHAIN_STEP_ORDER`.

    Returns the first step that is missing or not ``succeeded`` (a failed
    step is retried, not skipped over). ``None`` when every step has
    succeeded.
    """
    for step in CHAIN_STEP_ORDER:
        record = steps.get(step)
        if record is None or record.status != "succeeded":
            return step
    return None


class ReportedQuestion(BaseModel):
    """A clarify question and adopted answer as reported by the agent."""

    question: str
    adopted_answer: str
    alternatives: list[str] = Field(default_factory=list)


class ReportedFinding(BaseModel):
    """An analyze finding as reported by the agent."""

    title: str
    category: str
    severity_hint: str
    location: str
    summary: str


class StepReport(BaseModel):
    """Structured-output schema for :class:`SpecChainAgent` step reports.

    The workflow treats the filesystem as ground truth for step success
    (R9); this report is telemetry and a parse accelerator, not the
    source of truth.
    """

    status: Literal["completed", "blocked", "failed"]
    artifacts: list[str] = Field(default_factory=list)
    questions: list[ReportedQuestion] = Field(default_factory=list)
    findings: list[ReportedFinding] = Field(default_factory=list)
    detail: str = Field(description="Free-text summary or failure reason")


@dataclass(frozen=True, slots=True)
class AnalyzeFinding:
    """One analyze finding, ready to become a standalone remediation bead."""

    title: str
    category: str
    severity_hint: str
    location: str
    summary: str
    feature_dir: str

    @property
    def fingerprint(self) -> str:
        """sha256 hex digest of normalized ``title + location`` (R6 idempotency)."""
        normalized = f"{self.title.strip().casefold()}|{self.location.strip().casefold()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SpecChainReport:
    """Final chain-run summary returned to the CLI (FR-019)."""

    feature_dir: str | None
    status: ChainStatus
    steps: tuple[StepRecord, ...] = field(default_factory=tuple)
    ledger_entry_count: int = 0
    remediation_bead_count: int = 0
    resume_hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "feature_dir": self.feature_dir,
            "status": self.status,
            "steps": [step.model_dump(mode="json") for step in self.steps],
            "ledger_entry_count": self.ledger_entry_count,
            "remediation_bead_count": self.remediation_bead_count,
            "resume_hint": self.resume_hint,
        }
