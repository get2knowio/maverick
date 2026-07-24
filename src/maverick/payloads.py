"""Typed payloads returned by mailbox actors via airframe structured output.

Each :class:`SupervisorInboxPayload` subclass is the result schema for
one actor role. Airframe adapters force the model to call a synthesized
structured-output tool with arguments matching the schema; these models
then validate the returned dict before it flows to the supervisor's
typed domain methods.

The models are intentionally permissive:
- they accept legacy/alternate field names where prior runs emitted them,
- they allow additional properties so schema-compatible extensions are
  not lost.

Stricter workflow/domain models should still be applied deeper in the
pipeline where business invariants matter.

Naming note: ``SUPERVISOR_TOOL_PAYLOAD_MODELS`` and the ``submit_*`` keys
are kept verbatim from the legacy MCP-tool world so prior call sites
(briefing actor's per-aspect lookup, decomposer phase routing) keep
working without renaming. The "tool" name persists; only the adapter
that synthesizes it changed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from maverick.exceptions.base import MaverickError


class SupervisorToolPayloadError(MaverickError):
    """Raised when mailbox tool arguments fail typed intake validation."""

    def __init__(self, tool_name: str, validation_error: ValidationError) -> None:
        self.tool_name = tool_name
        self.validation_error = validation_error
        super().__init__(
            f"Supervisor inbox payload validation failed for {tool_name}: {validation_error}"
        )


class SupervisorInboxPayload(BaseModel):
    """Base model for supervisor inbox payloads.

    Extra fields are preserved because MCP schemas permit additional properties
    and some live prompts still return legacy-but-useful keys that downstream
    formatting code already knows how to consume.
    """

    model_config = ConfigDict(extra="allow", frozen=True)


def _copy_mapping(data: Any) -> dict[str, Any] | Any:
    """Return a shallow dict copy when *data* is mapping-like."""
    if isinstance(data, Mapping):
        return dict(data)
    return data


def _first_present(payload: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first non-None value present in *payload* for *keys*."""
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _prune_assumptions(data: Any) -> Any:
    """Drop malformed assumption entries before validating a submit payload.

    ``assumptions`` is additive context on a load-bearing payload
    (``submit_implementation`` / ``submit_review`` / ``submit_fix_result``).
    A single entry missing its ``question`` or ``adopted_answer`` must not
    fail validation of the whole implementation/review result — it is
    dropped instead. Well-formed entries (and already-parsed
    :class:`AssumptionPayload` instances from a state round-trip) pass
    through untouched.
    """
    payload = _copy_mapping(data)
    if not isinstance(payload, dict):
        return payload
    raw = payload.get("assumptions")
    if not isinstance(raw, (list, tuple)):
        return payload
    kept: list[Any] = []
    for item in raw:
        if isinstance(item, AssumptionPayload):
            kept.append(item)
            continue
        if isinstance(item, Mapping):
            question = item.get("question")
            answer = item.get("adopted_answer")
            if (
                isinstance(question, str)
                and question.strip()
                and isinstance(answer, str)
                and answer.strip()
            ):
                kept.append(item)
    payload["assumptions"] = kept
    return payload


class FileScopePayload(SupervisorInboxPayload):
    """Mailbox payload for file-scope declarations."""

    create: tuple[str, ...] = Field(default_factory=tuple)
    modify: tuple[str, ...] = Field(default_factory=tuple)
    protect: tuple[str, ...] = Field(default_factory=tuple)


class AcceptanceCriterionPayload(SupervisorInboxPayload):
    """Mailbox payload for acceptance criteria."""

    text: str
    trace_ref: str | None = None


#: Allowed values for ``WorkUnitOutlinePayload.complexity``. Treat as a
#: hint about how much model intelligence the bead needs:
#:
#: * ``trivial``  — boilerplate / config / one-file scaffolding (LICENSE,
#:   .gitignore, single-purpose data files). Output volume small.
#: * ``simple``   — mechanical, well-specified, single-file or single-
#:   function changes. Acceptance criteria are unambiguous.
#: * ``moderate`` — typical implementation work: a couple of files,
#:   non-trivial logic, but the design decisions are made.
#: * ``complex`` — architecturally meaningful, cross-cutting, or
#:   reasoning-heavy. Hard to verify mechanically; review-fix loops are
#:   more likely.
#:
#: ``None`` means the decomposer didn't classify (older runs, fallback,
#: or non-decomposer-sourced beads). Phase 1 only displays this; later
#: phases will route models per tier.
WorkUnitComplexity = Literal["trivial", "simple", "moderate", "complex"]


class WorkUnitOutlinePayload(SupervisorInboxPayload):
    """Mailbox payload for outline work units."""

    id: str
    task: str
    sequence: int | None = None
    parallel_group: str | None = None
    depends_on: tuple[str, ...] = Field(default_factory=tuple)
    file_scope: FileScopePayload = Field(default_factory=FileScopePayload)
    complexity: WorkUnitComplexity | None = None


class WorkUnitDetailPayload(SupervisorInboxPayload):
    """Mailbox payload for detailed work unit data."""

    id: str
    instructions: str
    acceptance_criteria: tuple[AcceptanceCriterionPayload, ...] = Field(default_factory=tuple)
    verification: tuple[str, ...] = Field(default_factory=tuple)
    test_specification: str = ""


class SubmitOutlinePayload(SupervisorInboxPayload):
    """Typed payload for ``submit_outline``."""

    work_units: tuple[WorkUnitOutlinePayload, ...]
    rationale: str | None = None


class SubmitDetailsPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_details``."""

    details: tuple[WorkUnitDetailPayload, ...]


class SubmitFixPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_fix``."""

    work_units: tuple[WorkUnitOutlinePayload, ...]
    details: tuple[WorkUnitDetailPayload, ...]


class AssumptionPayload(SupervisorInboxPayload):
    """An assumption an agent adopted to keep working.

    ``severity`` outside ``{low, medium, high}`` (or absent) is coerced to
    ``"medium"`` rather than rejected (FR-011); ``severity_defaulted`` records
    whether that coercion happened so ``record_assumption`` can persist
    ``assumption_severity_defaulted=true``. It's a derived flag, not
    something the agent is expected to report — but it's a normal field
    (not dump-excluded) so it survives the round trip through
    ``pending_assumptions`` state (dump → burr ``State`` → re-validate).
    """

    question: str = Field(min_length=1)
    adopted_answer: str = Field(min_length=1)
    alternatives: tuple[str, ...] = Field(default_factory=tuple)
    severity: str = "medium"
    severity_defaulted: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce_severity(cls, data: Any) -> Any:
        payload = _copy_mapping(data)
        if isinstance(payload, dict):
            raw = payload.get("severity")
            if raw not in ("low", "medium", "high"):
                payload["severity"] = "medium"
                payload["severity_defaulted"] = True
        return payload


class SubmitImplementationPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_implementation``."""

    summary: str
    files_changed: tuple[str, ...] = Field(default_factory=tuple)
    assumptions: tuple[AssumptionPayload, ...] = Field(default_factory=tuple)

    @model_validator(mode="before")
    @classmethod
    def _drop_malformed_assumptions(cls, data: Any) -> Any:
        return _prune_assumptions(data)


class SubmitFixResultPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_fix_result``."""

    summary: str
    addressed: tuple[str, ...] = Field(default_factory=tuple)
    contested: dict[str, str] = Field(default_factory=dict)
    assumptions: tuple[AssumptionPayload, ...] = Field(default_factory=tuple)

    @model_validator(mode="before")
    @classmethod
    def _drop_malformed_assumptions(cls, data: Any) -> Any:
        return _prune_assumptions(data)


class ReviewFindingPayload(SupervisorInboxPayload):
    """Typed payload for an individual review finding.

    The optional ``reviewer`` field carries provenance — set by the
    runtime when two reviewer actors run in parallel (correctness +
    completeness) so the supervisor can attribute findings back to the
    lens that flagged them. Older payloads (single-reviewer flow,
    legacy decomposer outputs) leave it ``None`` and that's fine.
    """

    severity: Literal["critical", "major", "minor"]
    issue: str
    file: str = ""
    line: int | None = None
    reviewer: Literal["correctness", "completeness"] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        payload = _copy_mapping(data)
        if isinstance(payload, dict):
            payload.setdefault("issue", _first_present(payload, "issue", "message", default=""))
        return payload


class SubmitReviewPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_review``."""

    approved: bool
    findings: tuple[ReviewFindingPayload, ...] = Field(default_factory=tuple)
    findings_count: int | None = None
    assumptions: tuple[AssumptionPayload, ...] = Field(default_factory=tuple)

    @model_validator(mode="before")
    @classmethod
    def _drop_malformed_assumptions(cls, data: Any) -> Any:
        return _prune_assumptions(data)

    @property
    def effective_findings_count(self) -> int:
        """Return explicit finding count when present, else derive it."""
        if self.findings_count is not None:
            return self.findings_count
        return len(self.findings)


class SubmitScopePayload(SupervisorInboxPayload):
    """Typed payload for ``submit_scope``."""

    in_scope: tuple[str, ...]
    out_scope: tuple[str, ...] = Field(default_factory=tuple)
    boundaries: tuple[str, ...] = Field(default_factory=tuple)
    summary: str = ""
    scope_rationale: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        payload = _copy_mapping(data)
        if isinstance(payload, dict):
            payload.setdefault("in_scope", _first_present(payload, "in_scope", "in_scope_items"))
            payload.setdefault(
                "out_scope",
                _first_present(payload, "out_scope", "out_of_scope_items", default=()),
            )
            payload.setdefault(
                "summary",
                _first_present(payload, "summary", "scope_rationale", default=""),
            )
            payload.setdefault(
                "scope_rationale",
                _first_present(payload, "scope_rationale", "summary", default=""),
            )
        return payload


class SubmitAnalysisPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_analysis``."""

    modules: tuple[str, ...]
    patterns: tuple[str, ...] = Field(default_factory=tuple)
    dependencies: tuple[str, ...] = Field(default_factory=tuple)
    complexity_assessment: str = ""
    summary: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        payload = _copy_mapping(data)
        if isinstance(payload, dict):
            payload.setdefault("modules", _first_present(payload, "modules", "relevant_modules"))
            payload.setdefault(
                "patterns",
                _first_present(payload, "patterns", "existing_patterns", default=()),
            )
            payload.setdefault(
                "dependencies",
                _first_present(payload, "dependencies", "integration_points", default=()),
            )
            payload.setdefault(
                "complexity_assessment",
                _first_present(payload, "complexity_assessment", default=""),
            )
        return payload


class SubmitCriteriaPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_criteria``."""

    criteria: tuple[str, ...]
    test_scenarios: tuple[str, ...] = Field(default_factory=tuple)
    objective_draft: str = ""
    measurability_notes: str = ""
    summary: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        payload = _copy_mapping(data)
        if isinstance(payload, dict):
            payload.setdefault("criteria", _first_present(payload, "criteria", "success_criteria"))
        return payload


class SubmitChallengePayload(SupervisorInboxPayload):
    """Typed payload for ``submit_challenge``."""

    risks: tuple[str, ...]
    blind_spots: tuple[str, ...] = Field(default_factory=tuple)
    open_questions: tuple[str, ...] = Field(default_factory=tuple)
    consensus_points: tuple[str, ...] = Field(default_factory=tuple)
    summary: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        payload = _copy_mapping(data)
        if isinstance(payload, dict):
            payload.setdefault("risks", _first_present(payload, "risks", "scope_challenges"))
            payload.setdefault(
                "blind_spots",
                _first_present(payload, "blind_spots", "criteria_challenges", default=()),
            )
            payload.setdefault(
                "open_questions",
                _first_present(
                    payload,
                    "open_questions",
                    "missing_considerations",
                    default=(),
                ),
            )
        return payload


class FlightPlanSuccessCriterionPayload(SupervisorInboxPayload):
    """Typed payload for generated flight-plan success criteria."""

    description: str
    verification: str = ""


class SubmitFlightPlanPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_flight_plan``."""

    objective: str
    context: str = ""
    success_criteria: tuple[FlightPlanSuccessCriterionPayload, ...]
    in_scope: tuple[str, ...] = Field(default_factory=tuple)
    out_of_scope: tuple[str, ...] = Field(default_factory=tuple)
    boundaries: tuple[str, ...] = Field(default_factory=tuple)
    constraints: tuple[str, ...] = Field(default_factory=tuple)
    tags: tuple[str, ...] = Field(default_factory=tuple)
    notes: str = ""
    name: str | None = None
    version: str | None = None


class ArchitectureDecisionPayload(SupervisorInboxPayload):
    """Typed payload for navigator architecture decisions."""

    title: str
    decision: str
    rationale: str = ""
    alternatives_considered: tuple[str, ...] = Field(default_factory=tuple)


class SubmitNavigatorBriefPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_navigator_brief``."""

    architecture_decisions: tuple[ArchitectureDecisionPayload, ...]
    module_structure: str = ""
    integration_points: tuple[str, ...] = Field(default_factory=tuple)
    summary: str


class StructuralEntityPayload(SupervisorInboxPayload):
    """Typed payload for structural entities."""

    name: str
    module_path: str = ""
    fields: tuple[str, ...] = Field(default_factory=tuple)
    relationships: tuple[str, ...] = Field(default_factory=tuple)


class StructuralInterfacePayload(SupervisorInboxPayload):
    """Typed payload for structural interfaces."""

    name: str
    methods: tuple[str, ...] = Field(default_factory=tuple)
    consumers: tuple[str, ...] = Field(default_factory=tuple)


class SubmitStructuralistBriefPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_structuralist_brief``."""

    entities: tuple[StructuralEntityPayload, ...]
    interfaces: tuple[StructuralInterfacePayload, ...] = Field(default_factory=tuple)
    summary: str


class ReconRiskPayload(SupervisorInboxPayload):
    """Typed payload for recon risks."""

    description: str
    severity: Literal["low", "medium", "high"] | str = "medium"
    mitigation: str = ""


class ReconAmbiguityPayload(SupervisorInboxPayload):
    """Typed payload for recon ambiguities."""

    question: str
    context: str = ""
    suggested_resolution: str = ""


class SubmitReconBriefPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_recon_brief``."""

    risks: tuple[ReconRiskPayload, ...]
    ambiguities: tuple[ReconAmbiguityPayload, ...] = Field(default_factory=tuple)
    testing_strategy: str = ""
    suggested_cross_plan_dependencies: tuple[str, ...] = Field(default_factory=tuple)
    summary: str


class ContrarianChallengePayload(SupervisorInboxPayload):
    """Typed payload for contrarian challenges."""

    target: str
    counter_argument: str
    recommendation: str = ""


class ContrarianSimplificationPayload(SupervisorInboxPayload):
    """Typed payload for contrarian simplifications."""

    current_approach: str
    simpler_alternative: str
    tradeoff: str = ""


class SubmitContrarianBriefPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_contrarian_brief``."""

    challenges: tuple[ContrarianChallengePayload, ...]
    simplifications: tuple[ContrarianSimplificationPayload, ...] = Field(default_factory=tuple)
    consensus_points: tuple[str, ...] = Field(default_factory=tuple)
    summary: str


# ---------------------------------------------------------------------------
# One-shot persona payloads. The other four inline personas
# (consolidator / validation-fixer / runway-seed / flight-plan-generator)
# return free-form text via airframe's plain-text execute path; only the
# curator's response is genuinely structured.
# ---------------------------------------------------------------------------


class CurationStepPayload(SupervisorInboxPayload):
    """One step of a curation plan."""

    command: str
    args: tuple[str, ...] = Field(default_factory=tuple)
    reason: str = Field(default="")


class SubmitCurationPlanPayload(SupervisorInboxPayload):
    """Payload for ``maverick.curator`` — ordered list of jj commands."""

    steps: tuple[CurationStepPayload, ...] = Field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Reconcile payloads (spec 051-reconcile-changed-answers). Deliberately carry
# no ``assumptions`` field: a reconcile agent that cannot proceed without
# adopting a new assumption must say so in prose and leave the delta empty;
# the workflow escalates rather than recording a new assumption mid-reconcile.
# ---------------------------------------------------------------------------


class SubmitCorrectionPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_correction``.

    Returned by ``ReconcilerAgent.correct(...)`` after editing the
    working-copy child of the target change.
    """

    summary: str = Field(min_length=1, description="What the correction changes and why.")
    files_touched: tuple[str, ...] = Field(
        default_factory=tuple, description="Repo-relative paths the agent edited."
    )
    no_change_required: bool = Field(
        default=False,
        description="True when the target already reflects the new answer (paraphrase case).",
    )

    @model_validator(mode="after")
    def _check_no_change_required_consistency(self) -> SubmitCorrectionPayload:
        if self.no_change_required and self.files_touched != ():
            raise ValueError(
                "no_change_required=True requires files_touched to be empty, "
                f"got {self.files_touched!r}"
            )
        return self


class SubmitConflictResolutionPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_conflict_resolution``.

    Returned by ``ReconcilerAgent.resolve_conflicts(...)`` per conflicted
    change per round.
    """

    resolved_files: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Files whose conflict markers were fully removed.",
    )
    unresolvable: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Files the agent declines to resolve.",
    )
    notes: str = Field(default="", description="Optional free-form notes on the resolution.")


class SemanticFinding(SupervisorInboxPayload):
    """One descendant analysis result within ``submit_semantic_dependents``."""

    change_id: str = Field(description="jj change id of the analyzed descendant.")
    dependent: bool = Field(description="Whether this descendant depends on the old assumption.")
    reason: str = Field(default="", description="Why this code depends on the old assumption.")
    fix_instructions: str = Field(
        default="",
        description="Imperative instructions for the fix (empty when dependent=False).",
    )

    @model_validator(mode="after")
    def _check_fix_instructions_when_dependent(self) -> SemanticFinding:
        if self.dependent and not self.fix_instructions.strip():
            raise ValueError("dependent=True requires non-empty fix_instructions")
        return self


class SubmitSemanticDependentsPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_semantic_dependents``.

    Returned by ``SemanticDependentsAgent.analyze(...)`` for a batch of
    descendant diffs.
    """

    findings: tuple[SemanticFinding, ...] = Field(
        default_factory=tuple, description="One finding per analyzed descendant."
    )


SUPERVISOR_TOOL_PAYLOAD_MODELS: dict[str, type[SupervisorInboxPayload]] = {
    "submit_outline": SubmitOutlinePayload,
    "submit_details": SubmitDetailsPayload,
    "submit_fix": SubmitFixPayload,
    "submit_implementation": SubmitImplementationPayload,
    "submit_review": SubmitReviewPayload,
    "submit_fix_result": SubmitFixResultPayload,
    "submit_scope": SubmitScopePayload,
    "submit_analysis": SubmitAnalysisPayload,
    "submit_criteria": SubmitCriteriaPayload,
    "submit_challenge": SubmitChallengePayload,
    "submit_flight_plan": SubmitFlightPlanPayload,
    "submit_navigator_brief": SubmitNavigatorBriefPayload,
    "submit_structuralist_brief": SubmitStructuralistBriefPayload,
    "submit_recon_brief": SubmitReconBriefPayload,
    "submit_contrarian_brief": SubmitContrarianBriefPayload,
    "submit_correction": SubmitCorrectionPayload,
    "submit_conflict_resolution": SubmitConflictResolutionPayload,
    "submit_semantic_dependents": SubmitSemanticDependentsPayload,
}


def parse_supervisor_tool_payload(
    tool_name: str,
    arguments: Mapping[str, Any] | None,
) -> SupervisorInboxPayload:
    """Validate and normalize mailbox tool arguments into a typed payload."""
    model_cls = SUPERVISOR_TOOL_PAYLOAD_MODELS.get(tool_name)
    if model_cls is None:
        raise ValueError(f"Unknown supervisor inbox tool: {tool_name}")

    try:
        return model_cls.model_validate(arguments or {})
    except ValidationError as exc:
        raise SupervisorToolPayloadError(tool_name, exc) from exc


def dump_supervisor_payload(payload: SupervisorInboxPayload) -> dict[str, Any]:
    """Return a JSON-compatible dictionary for a typed mailbox payload."""
    return payload.model_dump(mode="json", exclude_none=True)


__all__ = [
    "AcceptanceCriterionPayload",
    "ArchitectureDecisionPayload",
    "AssumptionPayload",
    "ContrarianChallengePayload",
    "ContrarianSimplificationPayload",
    "CurationStepPayload",
    "FileScopePayload",
    "FlightPlanSuccessCriterionPayload",
    "ReconAmbiguityPayload",
    "ReconRiskPayload",
    "ReviewFindingPayload",
    "SemanticFinding",
    "StructuralEntityPayload",
    "StructuralInterfacePayload",
    "SubmitAnalysisPayload",
    "SubmitChallengePayload",
    "SubmitConflictResolutionPayload",
    "SubmitContrarianBriefPayload",
    "SubmitCorrectionPayload",
    "SubmitCriteriaPayload",
    "SubmitCurationPlanPayload",
    "SubmitDetailsPayload",
    "SubmitFixPayload",
    "SubmitFixResultPayload",
    "SubmitFlightPlanPayload",
    "SubmitImplementationPayload",
    "SubmitNavigatorBriefPayload",
    "SubmitOutlinePayload",
    "SubmitReconBriefPayload",
    "SubmitReviewPayload",
    "SubmitScopePayload",
    "SubmitSemanticDependentsPayload",
    "SubmitStructuralistBriefPayload",
    "SupervisorInboxPayload",
    "SupervisorToolPayloadError",
    "WorkUnitDetailPayload",
    "WorkUnitOutlinePayload",
    "dump_supervisor_payload",
    "parse_supervisor_tool_payload",
]
