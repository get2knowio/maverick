"""Typed request/response envelopes for xoscar actors in the refuel path.

These frozen dataclasses replace the ``dict[str, Any]`` payloads that the
Thespian ``receiveMessage`` handlers keyed off a ``"type"`` string. They
carry the same fields as the legacy dicts so the migration is
field-for-field reversible during review.

Scope is intentionally narrow: these are the *supervisor → agent*
typed requests, plus the deterministic-actor result types. Inbound
MCP tool payloads are already Pydantic-typed in
``src/maverick/tools/supervisor_inbox/models.py`` (``SubmitOutlinePayload``
et al.) — agents pass those objects straight through to the supervisor's
typed domain methods rather than redefining them here.

Plan and fly workflows will grow their own envelopes in later phases;
keeping them in separate modules prevents one big "all messages" file.
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


__all__ = [
    "BeadsCreatedResult",
    "BriefingRequest",
    "CreateBeadsRequest",
    "DecomposerContext",
    "DetailRequest",
    "FixRequest",
    "NudgeRequest",
    "OutlineRequest",
    "PromptError",
    "ValidateRequest",
    "ValidationResult",
]
