"""Typed intake models for supervisor inbox MCP tool payloads.

The MCP tool schemas remain the agent-facing contract. These models sit on the
Python side of that boundary so supervisors can validate and normalize tool
arguments immediately after receipt instead of threading raw ``dict[str, Any]``
through downstream workflow code.

The models are intentionally permissive:
- they mirror the mailbox tool schemas closely,
- they accept legacy/alternate field names where the runtime already does,
- they allow additional properties so schema-compatible extensions are not lost.

Stricter workflow/domain models should still be applied deeper in the pipeline
where business invariants matter.
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


class FileScopePayload(SupervisorInboxPayload):
    """Mailbox payload for file-scope declarations."""

    create: tuple[str, ...] = Field(default_factory=tuple)
    modify: tuple[str, ...] = Field(default_factory=tuple)
    protect: tuple[str, ...] = Field(default_factory=tuple)


class AcceptanceCriterionPayload(SupervisorInboxPayload):
    """Mailbox payload for acceptance criteria."""

    text: str
    trace_ref: str | None = None


class WorkUnitOutlinePayload(SupervisorInboxPayload):
    """Mailbox payload for outline work units."""

    id: str
    task: str
    sequence: int | None = None
    parallel_group: str | None = None
    depends_on: tuple[str, ...] = Field(default_factory=tuple)
    file_scope: FileScopePayload = Field(default_factory=FileScopePayload)


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


class SubmitImplementationPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_implementation``."""

    summary: str
    files_changed: tuple[str, ...] = Field(default_factory=tuple)


class SubmitFixResultPayload(SupervisorInboxPayload):
    """Typed payload for ``submit_fix_result``."""

    summary: str
    addressed: tuple[str, ...] = Field(default_factory=tuple)
    contested: dict[str, str] = Field(default_factory=dict)


class ReviewFindingPayload(SupervisorInboxPayload):
    """Typed payload for an individual review finding."""

    severity: Literal["critical", "major", "minor"]
    issue: str
    file: str = ""
    line: int | None = None

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
    "ContrarianChallengePayload",
    "ContrarianSimplificationPayload",
    "FileScopePayload",
    "FlightPlanSuccessCriterionPayload",
    "ReconAmbiguityPayload",
    "ReconRiskPayload",
    "ReviewFindingPayload",
    "StructuralEntityPayload",
    "StructuralInterfacePayload",
    "SubmitAnalysisPayload",
    "SubmitChallengePayload",
    "SubmitContrarianBriefPayload",
    "SubmitCriteriaPayload",
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
    "SubmitStructuralistBriefPayload",
    "SupervisorInboxPayload",
    "SupervisorToolPayloadError",
    "WorkUnitDetailPayload",
    "WorkUnitOutlinePayload",
    "dump_supervisor_payload",
    "parse_supervisor_tool_payload",
]
