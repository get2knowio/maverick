"""Typed request/response envelopes for xoscar actors.

These frozen dataclasses are the supervisor-to-agent typed-request and
deterministic-actor result surfaces. Inbound MCP tool payloads are
already Pydantic-typed in ``src/maverick/tools/agent_inbox/models.py``
(``SubmitOutlinePayload`` et al.) — agents pass those objects straight
through to the supervisor's typed domain methods rather than
redefining them here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Supervisor → Decomposer (ACP kickoff)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DecomposerContext:
    """One-time broadcast sent to each pool decomposer before the first
    detail fan-out. Keeps subsequent ``DetailRequest`` messages tiny
    instead of re-shipping ~60KB of outline + flight plan + verification
    per unit."""

    outline_json: str
    flight_plan_content: str
    verification_properties: str


@dataclass(frozen=True, slots=True)
class OutlineRequest:
    flight_plan_content: str
    codebase_context: Any = None
    briefing: str | None = None
    runway_context: str | None = None
    validation_feedback: str | None = None


@dataclass(frozen=True, slots=True)
class DetailRequest:
    unit_ids: tuple[str, ...]

    @classmethod
    def for_unit(cls, unit_id: str) -> DetailRequest:
        return cls(unit_ids=(unit_id,))


@dataclass(frozen=True, slots=True)
class FixRequest:
    outline_json: str = "{}"
    details_json: str = "{}"
    verification_properties: str = ""
    coverage_gaps: tuple[str, ...] = ()
    overloaded: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NudgeRequest:
    """Supervisor → agent prompt re-send when the MCP tool never arrived."""

    expected_tool: str
    unit_id: str | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Supervisor → Briefing actors (refuel)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BriefingRequest:
    """Supervisor sends one of these to each briefing actor. The agent
    name is embedded so the actor can pass it back in logs and errors."""

    agent_name: str
    prompt: str


# ---------------------------------------------------------------------------
# Supervisor → Deterministic actors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidateRequest:
    """Payload sent from supervisor to ``ValidatorActor``.

    ``specs`` is typed ``Any`` here to avoid a circular import with
    ``maverick.workflows.refuel_maverick.models.WorkUnitSpec`` — the
    validator cares only that the sequence is iterable and matches
    ``validate_decomposition``'s expectations.
    """

    specs: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    error_type: str | None = None  # "coverage" | "other" | None
    gaps: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class CreateBeadsRequest:
    """Payload sent from supervisor to ``BeadCreatorActor``."""

    specs: tuple[Any, ...]
    deps: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class BeadsCreatedResult:
    success: bool
    epic_id: str = ""
    bead_count: int = 0
    deps_wired: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# Agent → Supervisor (error channel)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PromptError:
    """Agent's ACP call failed — reported to the supervisor via an
    in-pool RPC so the supervisor can requeue, re-nudge, or escalate."""

    phase: str
    error: str
    quota_exhausted: bool = False
    unit_id: str | None = None


# ---------------------------------------------------------------------------
# Fly workflow envelopes (Phase 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImplementRequest:
    """Supervisor → ImplementerActor prompt for implementation work.

    The supervisor builds the full prompt (work unit + briefing +
    runway context); this envelope carries that prompt plus the
    ``bead_id`` for logs and error routing.
    """

    bead_id: str
    prompt: str


@dataclass(frozen=True, slots=True)
class FlyFixRequest:
    """Supervisor → ImplementerActor fix-round prompt.

    Named distinctly from the decompose-flow ``FixRequest`` — fly carries
    the prompt text already composed by the supervisor from review/gate
    findings rather than a typed findings list.
    """

    bead_id: str
    prompt: str


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    """Supervisor → ReviewerActor request for a new bead review.

    The reviewer builds the full prompt internally from these fields so
    the supervisor doesn't have to know about first-review vs follow-up
    prompt differences.
    """

    bead_id: str
    bead_description: str = ""
    work_unit_md: str = ""
    briefing_context: str = ""


@dataclass(frozen=True, slots=True)
class AggregateReviewRequest:
    """Supervisor → ReviewerActor request for the epic-level aggregate review."""

    objective: str
    bead_list: str
    diff_stat: str
    bead_count: int


@dataclass(frozen=True, slots=True)
class NewBeadRequest:
    """Supervisor → implementer/reviewer signal to rotate session state."""

    bead_id: str


# --- Deterministic fly-actor requests/results ---


@dataclass(frozen=True, slots=True)
class GateRequest:
    cwd: str
    timeout_seconds: float = 600.0


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    summary: str = ""
    stages: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ACRequest:
    description: str
    cwd: str


@dataclass(frozen=True, slots=True)
class ACResult:
    passed: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpecRequest:
    cwd: str


@dataclass(frozen=True, slots=True)
class SpecResult:
    passed: bool
    details: str = ""
    findings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CommitRequest:
    bead_id: str
    title: str
    cwd: str
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class CommitResult:
    success: bool
    commit_sha: str | None = None
    tag: str | None = None
    error: str = ""


# ---------------------------------------------------------------------------
# Plan-generation workflow envelopes (Phase 3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GenerateRequest:
    """Supervisor → GeneratorActor kickoff.

    The supervisor builds the composite PRD + briefing prompt and
    hands it over. The agent submits a flight plan via
    ``submit_flight_plan`` → ``flight_plan_ready`` on the supervisor.
    """

    prompt: str


@dataclass(frozen=True, slots=True)
class PlanValidateRequest:
    """Supervisor → PlanValidatorActor request.

    ``flight_plan`` is the dumped ``SubmitFlightPlanPayload`` (dict
    form) so the validator can re-render the markdown without pulling
    in Pydantic dependencies inside the actor.
    """

    flight_plan: dict[str, Any]
    plan_name: str
    prd_content: str = ""


@dataclass(frozen=True, slots=True)
class PlanValidateResult:
    passed: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WritePlanRequest:
    flight_plan_markdown: str
    briefing_markdown: str = ""


@dataclass(frozen=True, slots=True)
class WritePlanResult:
    flight_plan_path: str
    briefing_path: str | None = None


__all__ = [
    "ACRequest",
    "ACResult",
    "AggregateReviewRequest",
    "BeadsCreatedResult",
    "BriefingRequest",
    "CommitRequest",
    "CommitResult",
    "CreateBeadsRequest",
    "DecomposerContext",
    "DetailRequest",
    "FixRequest",
    "FlyFixRequest",
    "GateRequest",
    "GateResult",
    "GenerateRequest",
    "ImplementRequest",
    "NewBeadRequest",
    "NudgeRequest",
    "OutlineRequest",
    "PlanValidateRequest",
    "PlanValidateResult",
    "PromptError",
    "ReviewRequest",
    "SpecRequest",
    "SpecResult",
    "ValidateRequest",
    "ValidationResult",
    "WritePlanRequest",
    "WritePlanResult",
]
