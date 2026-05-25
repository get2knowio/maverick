"""Burr actions for the ``refuel_maverick`` workflow.

The ``maverick refuel`` workflow runs through these actions exclusively
as of Phase 4 of the xoscar → Burr migration.

Known gaps relative to the pre-migration supervisor (queued for
follow-up):

* Detail fan-out: per-unit retry budget is ``MAX_DETAIL_RETRIES = 1``
  at the current tier. On ``airframe.errors.RuntimeTransientError``
  the unit escalates one rung on the decomposer tier ladder and
  retries; timeouts and persistent no-payload outcomes stay
  abandoned at the current tier (matching the pre-migration
  ``_try_one_tier`` policy). True per-tier runtime bindings — so
  the escalated tier maps to a *different* model — are wired
  through ``runtime_for_agent("decompose")`` today and will
  benefit from later substrate work to support per-tier overrides.
* Cache integration: ``initial_payload`` cache reads pass through
  (resume from a previously-cached run still works), but **the Burr
  driver does not write cache files**. Re-running a Burr-mode refuel
  starts from scratch; rerun on xoscar to re-populate caches.
* Quota error special-handling: treated like any other failure for now.
* Fix-round merge: merges both ``details`` and ``work_units`` from
  the fix payload (handles the case where the fixer splits an
  overloaded unit). New ``work_units`` returned by the fixer are
  appended to the outline; existing ones are replaced by id.

Default driver remains xoscar; opt in via ``MAVERICK_USE_BURR=refuel``.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from burr.core import State, action

from maverick.events import (
    AgentCompleted,
    AgentStarted,
    ProgressEvent,
    StepOutput,
)
from maverick.payloads import (
    SUPERVISOR_TOOL_PAYLOAD_MODELS,
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
    SupervisorInboxPayload,
    dump_supervisor_payload,
)

if TYPE_CHECKING:
    from maverick.agents.decomposer import DecomposerAgent
    from maverick.squadron.refuel import RefuelSquadron


__all__ = [
    "BRIEFING_CONFIG",
    "MAX_DETAIL_RETRIES",
    "MAX_FIX_ROUNDS",
    "PARALLEL_BRIEFING_AGENTS",
    "check_validation",
    "create_beads",
    "detail_fan_out",
    "init_state",
    "outline",
    "parallel_briefings",
    "request_fix",
    "synthesize_briefing",
    "validate",
]

_SOURCE = "refuel-burr"

# Retry budgets — preserved from the pre-Burr supervisor.
MAX_FIX_ROUNDS: int = 3
MAX_DETAIL_RETRIES: int = 1


#: ``(agent_name, display_label, mcp_tool, role_key)`` tuples — same
#: layout as ``REFUEL_BRIEFING_CONFIG`` in the xoscar supervisor.
BRIEFING_CONFIG: tuple[tuple[str, str, str, str], ...] = (
    ("navigator", "Navigator", "submit_navigator_brief", "navigator"),
    ("structuralist", "Structuralist", "submit_structuralist_brief", "structuralist"),
    ("recon", "Recon", "submit_recon_brief", "recon"),
    ("contrarian", "Contrarian", "submit_contrarian_brief", "contrarian"),
)

#: Agent names that run during the first (parallel) briefing phase.
PARALLEL_BRIEFING_AGENTS: tuple[str, ...] = ("navigator", "structuralist", "recon")

_LABEL_FOR: dict[str, str] = {n: lbl for n, lbl, _t, _r in BRIEFING_CONFIG}
_TOOL_FOR: dict[str, str] = {n: tool for n, _lbl, tool, _r in BRIEFING_CONFIG}
_ROLE_FOR: dict[str, str] = {n: role for n, _lbl, _t, role in BRIEFING_CONFIG}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _schema_for(agent_name: str) -> Any:
    tool = _TOOL_FOR[agent_name]
    schema = SUPERVISOR_TOOL_PAYLOAD_MODELS.get(tool)
    if schema is None:
        raise RuntimeError(f"No payload schema registered for tool {tool!r}")
    return schema


async def _run_one_briefing(
    *,
    agent_name: str,
    prompt: str,
    squadron: RefuelSquadron,
    events: asyncio.Queue[ProgressEvent | None],
    provider_label: str,
) -> tuple[str, dict[str, Any]]:
    """Build one briefing agent, run it, emit AgentStarted/Completed.

    Returns ``(role_key, payload_dict)``.
    """
    schema = _schema_for(agent_name)
    label = _LABEL_FOR[agent_name]
    agent = squadron.build_briefing_agent(agent_name=agent_name, result_model=schema)

    await events.put(AgentStarted(step_name="briefing", agent_name=label, provider=provider_label))
    t0 = time.monotonic()
    payload = await agent.brief(prompt)
    await events.put(
        AgentCompleted(
            step_name="briefing",
            agent_name=label,
            duration_seconds=time.monotonic() - t0,
        )
    )
    if not isinstance(payload, SupervisorInboxPayload):
        raise TypeError(
            f"briefing agent {agent_name!r} returned {type(payload).__name__}, "
            f"expected a SupervisorInboxPayload subclass"
        )
    return _ROLE_FOR[agent_name], dump_supervisor_payload(payload)


async def _put_output(
    events: asyncio.Queue[ProgressEvent | None],
    step_name: str,
    message: str,
    *,
    level: str = "info",
    metadata: dict[str, Any] | None = None,
) -> None:
    await events.put(
        StepOutput(
            step_name=step_name,
            message=message,
            display_label="",
            level=level,  # type: ignore[arg-type]
            source=_SOURCE,
            metadata=metadata,
        )
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@action(
    reads=[],
    writes=[
        "briefs",
        "briefing_markdown",
        "outline",
        "accumulated_details",
        "specs",
        "fix_rounds",
        "validation_passed",
        "validation_warnings",
        "epic_id",
        "epic",
        "work_beads",
        "created_map",
        "dependencies",
        "deps_wired",
        "abandoned_unit_ids",
    ],
)
async def init_state(state: State) -> tuple[dict[str, Any], State]:
    """Seed scratch slots used by downstream actions."""
    return {}, state.update(
        briefs={},
        briefing_markdown="",
        outline=None,
        accumulated_details=[],
        specs=[],
        fix_rounds=0,
        validation_passed=False,
        validation_warnings=[],
        epic_id="",
        epic=None,
        work_beads=[],
        created_map={},
        dependencies=[],
        deps_wired=0,
        abandoned_unit_ids=[],
    )


@action(reads=["briefing_prompt", "provider_labels"], writes=["briefs"])
async def parallel_briefings(
    state: State,
    *,
    squadron: RefuelSquadron,
    events: asyncio.Queue[ProgressEvent | None],
    max_concurrent: int,
) -> tuple[dict[str, Any], State]:
    """Run navigator + structuralist + recon in parallel."""
    provider_labels: dict[str, str] = state["provider_labels"]
    sem = asyncio.Semaphore(max(1, max_concurrent))

    async def _bounded(name: str) -> tuple[str, dict[str, Any]]:
        async with sem:
            return await _run_one_briefing(
                agent_name=name,
                prompt=state["briefing_prompt"],
                squadron=squadron,
                events=events,
                provider_label=provider_labels.get(_LABEL_FOR[name], ""),
            )

    results = await asyncio.gather(*(_bounded(n) for n in PARALLEL_BRIEFING_AGENTS))
    briefs = dict(state["briefs"])
    for role_key, payload_dict in results:
        briefs[role_key] = payload_dict
    return {"briefs_collected": list(briefs)}, state.update(briefs=briefs)


@action(
    reads=["briefing_prompt", "raw_content", "briefs", "provider_labels"],
    writes=["briefs"],
)
async def contrarian_briefing(
    state: State,
    *,
    squadron: RefuelSquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Run the contrarian after the parallel briefings are in."""
    from maverick.agents.briefing.prompts import build_contrarian_prompt

    briefs = state["briefs"]
    prompt = build_contrarian_prompt(
        flight_plan_content=state["raw_content"],
        navigator=briefs.get("navigator"),
        structuralist=briefs.get("structuralist"),
        recon=briefs.get("recon"),
    )
    role_key, payload_dict = await _run_one_briefing(
        agent_name="contrarian",
        prompt=prompt,
        squadron=squadron,
        events=events,
        provider_label=state["provider_labels"].get("Contrarian", ""),
    )
    new_briefs = dict(briefs)
    new_briefs[role_key] = payload_dict
    return {"contrarian_done": True}, state.update(briefs=new_briefs)


@action(reads=["briefs"], writes=["briefing_markdown"])
async def synthesize_briefing(state: State) -> tuple[dict[str, Any], State]:
    """Render the four briefs into a single markdown block."""
    from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

    briefs = state["briefs"]
    md = serialize_briefs_to_markdown(
        state.get("plan_name", "refuel"),
        scope=briefs.get("navigator"),
        analysis=briefs.get("structuralist"),
        criteria=briefs.get("recon"),
        challenge=briefs.get("contrarian"),
    )
    return {"briefing_markdown_length": len(md)}, state.update(briefing_markdown=md)


# ---------------------------------------------------------------------------
# Decomposition: outline → detail fan-out → validate (+ fix loop) → beads
# ---------------------------------------------------------------------------


_DEFAULT_TIER = "default"


@action(
    reads=["raw_content", "codebase_context", "briefing_markdown", "open_bead_context"],
    writes=["outline"],
)
async def outline(
    state: State,
    *,
    squadron: RefuelSquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Acquire a decomposer from the pool and run the outline pass."""
    await _put_output(events, "decompose", "Requesting outline")
    decomposer: DecomposerAgent = await squadron.decomposer_pool.acquire(_DEFAULT_TIER)
    await events.put(AgentStarted(step_name="decompose", agent_name="outline", provider=""))
    t0 = time.monotonic()
    try:
        # DecomposerAgent.outline builds its own prompt from these kwargs.
        payload = await decomposer.outline(
            flight_plan_content=state["raw_content"],
            codebase_context=state["codebase_context"],
            briefing=state["briefing_markdown"] or None,
            runway_context=state.get("runway_context_text") or None,
        )
    finally:
        await squadron.decomposer_pool.release(decomposer, _DEFAULT_TIER)
    await events.put(
        AgentCompleted(
            step_name="decompose",
            agent_name="outline",
            duration_seconds=time.monotonic() - t0,
        )
    )
    if not isinstance(payload, SubmitOutlinePayload):
        raise TypeError(
            f"decomposer.outline returned {type(payload).__name__}, expected SubmitOutlinePayload"
        )
    outline_dict = dump_supervisor_payload(payload)
    unit_count = len(outline_dict.get("work_units", ()))
    await _put_output(
        events,
        "decompose",
        f"Outline produced {unit_count} work units",
        metadata={"work_unit_count": unit_count},
    )
    return {"work_unit_count": unit_count}, state.update(outline=outline_dict)


_REFUEL_TIER_LADDER: tuple[str, ...] = (
    _DEFAULT_TIER,
    "trivial",
    "simple",
    "moderate",
    "complex",
)


def _refuel_tier_for_level(level: int) -> str:
    """Pick the decomposer tier name for an escalation level."""
    if level <= 0:
        return _REFUEL_TIER_LADDER[0]
    if level >= len(_REFUEL_TIER_LADDER):
        return _REFUEL_TIER_LADDER[-1]
    return _REFUEL_TIER_LADDER[level]


async def _run_one_detail(
    *,
    unit_id: str,
    decomposer: DecomposerAgent,
    retries_remaining: int,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any] | None, str]:
    """Run detail for a single unit with retry-on-timeout budget.

    Returns ``(detail_or_None, failure_kind)`` where ``failure_kind`` is
    one of ``""`` (success), ``"timeout"``, ``"transient"``, or
    ``"no_payload"``. ``transient`` lets the caller escalate to the
    next tier; the others propagate up as abandon.
    """
    from airframe.errors import RuntimeTransientError

    label = unit_id
    await events.put(AgentStarted(step_name="decompose", agent_name=label, provider=""))
    t0 = time.monotonic()
    attempts = retries_remaining + 1
    last_payload: dict[str, Any] | None = None
    failure_kind = "no_payload"
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            payload = await decomposer.detail(unit_ids=(unit_id,))
        except TimeoutError:
            if attempt + 1 >= attempts:
                failure_kind = "timeout"
                last_error = "timed out"
                break
            continue
        except RuntimeTransientError as exc:
            failure_kind = "transient"
            last_error = str(exc)
            break
        if not isinstance(payload, SubmitDetailsPayload):
            raise TypeError(
                f"decomposer.detail returned {type(payload).__name__}, "
                f"expected SubmitDetailsPayload"
            )
        payload_dict = dump_supervisor_payload(payload)
        details = payload_dict.get("details", []) or []
        matching = [d for d in details if (d.get("id") or d.get("unit_id")) == unit_id]
        if matching:
            last_payload = matching[0]
            failure_kind = ""
            break
        if attempt + 1 >= attempts:
            break

    await events.put(
        AgentCompleted(
            step_name="decompose",
            agent_name=label,
            duration_seconds=time.monotonic() - t0,
            success=last_payload is not None,
            error=last_error if last_payload is None else None,
        )
    )
    return last_payload, failure_kind


async def _run_detail_with_escalation(
    *,
    unit_id: str,
    squadron: RefuelSquadron,
    retries_remaining: int,
    events: asyncio.Queue[ProgressEvent | None],
) -> dict[str, Any] | None:
    """Run one unit's detail pass with per-unit tier escalation.

    On ``RuntimeTransientError``, bumps to the next tier on
    :data:`_REFUEL_TIER_LADDER` and re-acquires a decomposer from the
    pool for that tier. Returns the unit's detail payload on success
    or ``None`` once the ladder is exhausted (or a non-transient
    failure terminates the loop). Timeouts and persistent
    no-payload outcomes are treated as final at the current tier —
    they don't escalate.
    """
    level = 0
    max_level = len(_REFUEL_TIER_LADDER) - 1
    while True:
        tier = _refuel_tier_for_level(level)
        decomposer = await squadron.decomposer_pool.acquire(tier)
        try:
            detail, failure = await _run_one_detail(
                unit_id=unit_id,
                decomposer=decomposer,
                retries_remaining=retries_remaining,
                events=events,
            )
        finally:
            await squadron.decomposer_pool.release(decomposer, tier)
        if detail is not None:
            return detail
        if failure != "transient" or level >= max_level:
            return None
        next_tier = _refuel_tier_for_level(level + 1)
        await _put_output(
            events,
            "decompose",
            f"Unit {unit_id}: transient failure on tier '{tier}'; escalating to '{next_tier}'",
            level="warning",
            metadata={"unit_id": unit_id, "from_tier": tier, "to_tier": next_tier},
        )
        level += 1


@action(
    reads=["outline"],
    writes=["accumulated_details", "abandoned_unit_ids"],
)
async def detail_fan_out(
    state: State,
    *,
    squadron: RefuelSquadron,
    events: asyncio.Queue[ProgressEvent | None],
    pool_size: int,
) -> tuple[dict[str, Any], State]:
    """Fan out per-unit detail requests across the decomposer pool.

    Phase 2 simplifications (see module docstring): single-tier
    dispatch, no escalation, no cache write. Per-unit retry budget
    matches the legacy ``MAX_DETAIL_RETRIES``.
    """
    outline_dict = state["outline"]
    if outline_dict is None:
        raise RuntimeError("detail_fan_out ran without an outline")

    unit_ids = [u["id"] for u in outline_dict.get("work_units", []) if u.get("id")]
    if not unit_ids:
        return {"unit_count": 0}, state

    await _put_output(events, "decompose", f"Requesting details for {len(unit_ids)} units")
    sem = asyncio.Semaphore(max(1, pool_size))
    accumulated: list[dict[str, Any]] = []
    abandoned: list[str] = []
    lock = asyncio.Lock()

    async def _one(unit_id: str) -> None:
        async with sem:
            detail = await _run_detail_with_escalation(
                unit_id=unit_id,
                squadron=squadron,
                retries_remaining=MAX_DETAIL_RETRIES,
                events=events,
            )
        async with lock:
            if detail is None:
                abandoned.append(unit_id)
            else:
                accumulated.append(detail)

    await asyncio.gather(*(_one(u) for u in unit_ids))

    await _put_output(
        events,
        "decompose",
        f"Detail fan-out complete ({len(accumulated)} done, {len(abandoned)} abandoned)",
        metadata={"completed": len(accumulated), "abandoned": len(abandoned)},
    )
    return (
        {"completed_count": len(accumulated), "abandoned_count": len(abandoned)},
        state.update(accumulated_details=accumulated, abandoned_unit_ids=abandoned),
    )


def _merge_to_specs(
    outline_dict: dict[str, Any],
    accumulated_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge outline + per-unit details into WorkUnitSpec dicts."""
    details_by_id = {d.get("id") or d.get("unit_id"): d for d in accumulated_details}
    specs: list[dict[str, Any]] = []
    for unit in outline_dict.get("work_units", []):
        uid = unit.get("id")
        if not uid:
            continue
        detail = details_by_id.get(uid)
        if detail is None:
            # Outline-only — minimal spec with empty acceptance criteria.
            spec = {**unit, "acceptance_criteria": [], "file_scope": unit.get("file_scope", [])}
        else:
            spec = {**unit, **detail}
        specs.append(spec)
    return specs


@action(
    reads=["outline", "accumulated_details"],
    writes=["specs", "validation_passed", "validation_warnings"],
)
async def validate(
    state: State,
    *,
    events: asyncio.Queue[ProgressEvent | None],
    expected_sc_refs: tuple[str, ...] = (),
    sc_count: int = 0,
) -> tuple[dict[str, Any], State]:
    """Run the same deterministic validator the xoscar workflow uses."""
    from maverick.library.actions.decompose import validate_decomposition
    from maverick.workflows.refuel_maverick.models import WorkUnitSpec

    outline_dict = state["outline"]
    if outline_dict is None:
        raise RuntimeError("validate ran without an outline")

    specs = _merge_to_specs(outline_dict, state["accumulated_details"])
    # ``validate_decomposition`` returns a list of gap strings on
    # success (empty == passed) and *raises* ``ValueError`` /
    # ``SCCoverageError`` on schema-level issues (cycles, dangling
    # depends_on, uncovered SCs). Mirror the xoscar supervisor's
    # behaviour and surface either path as ``validation_warnings``.
    gaps: list[str] = []
    try:
        spec_models = [WorkUnitSpec.model_validate(s) for s in specs]
        result = validate_decomposition(
            spec_models,
            success_criteria_count=sc_count,
            expected_sc_refs=list(expected_sc_refs) if expected_sc_refs else None,
        )
        gaps = list(result)
    except ValueError as exc:
        gaps = [str(exc)]
    passed = not gaps

    if passed:
        await _put_output(events, "decompose", "Validation passed", level="success")
    else:
        await _put_output(
            events,
            "decompose",
            f"Validation found {len(gaps)} gap(s)",
            level="warning",
            metadata={"gap_count": len(gaps)},
        )

    return {"passed": passed, "gap_count": len(gaps)}, state.update(
        specs=specs,
        validation_passed=passed,
        validation_warnings=list(gaps),
    )


@action(
    reads=["specs", "validation_warnings", "fix_rounds", "outline", "accumulated_details"],
    writes=["accumulated_details", "outline", "fix_rounds"],
)
async def request_fix(
    state: State,
    *,
    squadron: RefuelSquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """One round of decomposer fix dispatch.

    Merges both ``details`` (refined acceptance criteria / verification
    steps) and ``work_units`` (outline-level changes — e.g. when the
    fixer splits an overloaded unit) from the returned ``SubmitFixPayload``
    into State. Matches the pre-migration supervisor's behaviour; without
    the outline merge, splits introduced by the fixer would be silently
    dropped.
    """
    new_fix_rounds = state["fix_rounds"] + 1
    await _put_output(
        events,
        "decompose",
        f"Requesting fix (round {new_fix_rounds}/{MAX_FIX_ROUNDS})",
        metadata={"fix_round": new_fix_rounds},
    )
    decomposer = await squadron.decomposer_pool.acquire(_DEFAULT_TIER)
    label = f"fix-round-{new_fix_rounds}"
    await events.put(AgentStarted(step_name="decompose", agent_name=label, provider=""))
    t0 = time.monotonic()
    try:
        payload = await decomposer.fix(
            coverage_gaps=tuple(state["validation_warnings"]),
            overloaded=(),
        )
    finally:
        await squadron.decomposer_pool.release(decomposer, _DEFAULT_TIER)
    await events.put(
        AgentCompleted(
            step_name="decompose",
            agent_name=label,
            duration_seconds=time.monotonic() - t0,
        )
    )

    if not isinstance(payload, SubmitFixPayload):
        raise TypeError(
            f"decomposer.fix returned {type(payload).__name__}, expected SubmitFixPayload"
        )
    payload_dict = dump_supervisor_payload(payload)
    fix_details = payload_dict.get("details", []) or []
    fix_work_units = payload_dict.get("work_units", []) or []

    # Merge fix deltas into accumulated_details (replace by unit_id
    # where the fixer sent a new version; append where it's new).
    accumulated = list(state["accumulated_details"])
    by_id = {d.get("id") or d.get("unit_id"): i for i, d in enumerate(accumulated)}
    for d in fix_details:
        uid = d.get("id") or d.get("unit_id")
        if uid is None:
            continue
        if uid in by_id:
            accumulated[by_id[uid]] = d
        else:
            accumulated.append(d)
            by_id[uid] = len(accumulated) - 1

    # Merge work_units deltas back into the outline. Handles the case
    # where the fixer adds a new unit (splitting an overloaded one).
    # Existing units with the same id are replaced; new ids are
    # appended. Outline-only fields (id, task, sequence, depends_on,
    # file_scope, complexity) are taken verbatim from the fix payload.
    outline_dict = dict(state["outline"] or {})
    outline_units = list(outline_dict.get("work_units", []))
    outline_by_id = {u.get("id"): i for i, u in enumerate(outline_units)}
    new_units = 0
    for wu in fix_work_units:
        uid = wu.get("id")
        if uid is None:
            continue
        if uid in outline_by_id:
            outline_units[outline_by_id[uid]] = wu
        else:
            outline_units.append(wu)
            outline_by_id[uid] = len(outline_units) - 1
            new_units += 1
    outline_dict["work_units"] = outline_units

    if new_units:
        await _put_output(
            events,
            "decompose",
            f"Fix introduced {new_units} new work unit(s)",
            metadata={"new_unit_count": new_units},
        )

    return {"fix_rounds": new_fix_rounds, "new_units": new_units}, state.update(
        accumulated_details=accumulated,
        outline=outline_dict,
        fix_rounds=new_fix_rounds,
    )


@action(reads=["validation_passed", "fix_rounds"], writes=["validation_complete"])
async def check_validation(state: State) -> tuple[dict[str, Any], State]:
    """Router action: did validation pass, or are we out of fix budget?"""
    done = bool(state["validation_passed"]) or state["fix_rounds"] >= MAX_FIX_ROUNDS
    return {"validation_complete": done}, state.update(validation_complete=done)


@action(
    reads=["specs"],
    writes=[
        "epic_id",
        "epic",
        "work_beads",
        "created_map",
        "dependencies",
        "deps_wired",
    ],
)
async def create_beads(
    state: State,
    *,
    cwd: str,
    plan_name: str,
    plan_objective: str,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Persist work-unit specs as a beads epic with task children.

    Ports the body of
    the legacy ``BeadCreatorActor.create_beads`` deleted during the
    Burr migration.
    """
    from maverick.library.actions.beads import create_beads as create_beads_action
    from maverick.library.actions.beads import wire_dependencies
    from maverick.workflows.refuel_maverick.models import WorkUnitSpec

    raw_specs = state["specs"]
    if not raw_specs:
        await _put_output(events, "decompose", "No specs to create beads from", level="warning")
        return {"bead_count": 0}, state

    specs = [WorkUnitSpec.model_validate(s) if isinstance(s, dict) else s for s in raw_specs]
    epic_def: dict[str, Any] = {
        "title": plan_name,
        "bead_type": "epic",
        "priority": 1,
        "category": "user_story",
        "description": plan_objective,
        "task_list": [s.id for s in specs],
    }
    work_defs: list[dict[str, Any]] = [
        {
            "title": (s.task or "")[:490],
            "bead_type": "task",
            "priority": 2,
            "category": "user_story",
            "description": ((s.instructions or "") or (s.task or ""))[:500],
            "user_story_id": s.id,
        }
        for s in specs
    ]

    creation = await create_beads_action(
        epic_definition=epic_def,
        work_definitions=work_defs,
        cwd=cwd,
    )

    extracted_deps = _extract_deps(specs)
    wire_result = None
    if extracted_deps:
        wire_result = await wire_dependencies(
            work_definitions=work_defs,
            created_map=creation.created_map,
            tasks_content="",
            extracted_deps=json.dumps(extracted_deps),
            cwd=cwd,
        )

    epic_dict = creation.epic if isinstance(creation.epic, dict) else None
    epic_id = (epic_dict or {}).get("bd_id", "") if epic_dict else ""
    wired_deps = list(getattr(wire_result, "dependencies", ()) or ()) if wire_result else []

    await _put_output(
        events,
        "decompose",
        f"Created epic {epic_id!r} with {len(creation.work_beads)} children",
        level="success",
        metadata={
            "epic_id": epic_id,
            "bead_count": len(creation.work_beads),
            "deps_wired": len(wired_deps),
        },
    )
    return {"epic_id": epic_id, "bead_count": len(creation.work_beads)}, state.update(
        epic_id=epic_id,
        epic=epic_dict,
        work_beads=list(creation.work_beads),
        created_map=dict(creation.created_map),
        dependencies=wired_deps,
        deps_wired=len(wired_deps),
    )


def _extract_deps(specs: list[Any]) -> list[list[str]]:
    """``[[source_id, target_id], ...]`` from spec.depends_on entries."""
    deps: list[list[str]] = []
    for spec in specs:
        source = getattr(spec, "id", None) or (spec.get("id") if isinstance(spec, dict) else None)
        if not source:
            continue
        raw_deps = (
            getattr(spec, "depends_on", None)
            or (spec.get("depends_on") if isinstance(spec, dict) else None)
            or ()
        )
        for target in raw_deps:
            if target:
                deps.append([source, target])
    return deps
