"""Burr actions for the ``generate_flight_plan`` workflow.

Each ``@action`` is a small async function that:

1. Reads what it needs from ``State`` (or its bound dependencies).
2. Calls into the :class:`~maverick.squadron.plan.PlanSquadron` (or an
   on-demand briefing agent built from it) — the substrate-clean
   agent layer.
3. Writes results back to ``State`` and emits any per-agent progress
   events to a bound ``asyncio.Queue``.

The graph that wires these together lives in ``burr_graph.py``.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from burr.core import State, action

from maverick.events import AgentCompleted, AgentStarted, ProgressEvent, StepOutput
from maverick.payloads import (
    SUPERVISOR_TOOL_PAYLOAD_MODELS,
    SubmitFlightPlanPayload,
    SupervisorInboxPayload,
    dump_supervisor_payload,
)

if TYPE_CHECKING:
    from maverick.squadron.plan import PlanSquadron


__all__ = [
    "BRIEFING_CONFIG",
    "PARALLEL_BRIEFING_AGENTS",
    "contrarian_briefing",
    "generate_plan",
    "init_state",
    "parallel_briefings",
    "synthesize_briefing",
    "validate_plan",
    "write_plan",
]

_SOURCE = "plan-burr"


#: ``(agent_name, display_label, mcp_tool, role_key)`` tuples — same
#: layout as the xoscar ``PLAN_BRIEFING_CONFIG`` so per-role configuration
#: stays portable across the two drivers.
BRIEFING_CONFIG: tuple[tuple[str, str, str, str], ...] = (
    ("scopist", "Scopist", "submit_scope", "scope"),
    ("codebase_analyst", "Codebase Analyst", "submit_analysis", "analysis"),
    ("criteria_writer", "Criteria Writer", "submit_criteria", "criteria"),
    ("contrarian", "Contrarian", "submit_challenge", "challenge"),
)

#: Agent names that run during the first (parallel) briefing phase.
PARALLEL_BRIEFING_AGENTS: tuple[str, ...] = (
    "scopist",
    "codebase_analyst",
    "criteria_writer",
)

# Lookup helpers — derived once from BRIEFING_CONFIG so callers don't
# have to walk the tuple themselves.
_LABEL_FOR: dict[str, str] = {n: lbl for n, lbl, _t, _r in BRIEFING_CONFIG}
_TOOL_FOR: dict[str, str] = {n: tool for n, _lbl, tool, _r in BRIEFING_CONFIG}
_ROLE_FOR: dict[str, str] = {n: role for n, _lbl, _t, role in BRIEFING_CONFIG}


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
    squadron: PlanSquadron,
    events: asyncio.Queue[ProgressEvent | None],
    provider_label: str,
) -> tuple[str, dict[str, Any]]:
    """Build a briefing agent, run it, emit AgentStarted/AgentCompleted.

    Returns ``(role_key, payload_dict)``. The action wrappers stash the
    result on ``State["briefs"]`` keyed by role.
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


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@action(reads=[], writes=["briefs", "briefing_markdown", "flight_plan"])
async def init_state(state: State) -> tuple[dict[str, Any], State]:
    """Seed scratch slots used by downstream actions."""
    return {}, state.update(briefs={}, briefing_markdown="", flight_plan=None)


@action(reads=["prd_content", "provider_labels"], writes=["briefs"])
async def parallel_briefings(
    state: State,
    *,
    squadron: PlanSquadron,
    events: asyncio.Queue[ProgressEvent | None],
    max_concurrent: int,
) -> tuple[dict[str, Any], State]:
    """Run scopist + codebase_analyst + criteria_writer in parallel.

    Concurrency capped by ``max_concurrent`` (default 3 — matches the
    legacy ``parallel.max_briefing_agents`` setting). Each sub-task
    builds its own briefing agent via the squadron, so the per-task
    HTTP session/token state is isolated.
    """
    from maverick.agents.preflight_briefing.prompts import (
        build_preflight_briefing_prompt,
    )

    prompt = build_preflight_briefing_prompt(state["prd_content"])
    provider_labels: dict[str, str] = state["provider_labels"]
    sem = asyncio.Semaphore(max(1, max_concurrent))

    async def _bounded(name: str) -> tuple[str, dict[str, Any]]:
        async with sem:
            return await _run_one_briefing(
                agent_name=name,
                prompt=prompt,
                squadron=squadron,
                events=events,
                provider_label=provider_labels.get(_LABEL_FOR[name], ""),
            )

    results = await asyncio.gather(*(_bounded(n) for n in PARALLEL_BRIEFING_AGENTS))
    briefs = dict(state["briefs"])
    for role_key, payload_dict in results:
        briefs[role_key] = payload_dict
    return {"briefs_collected": list(briefs)}, state.update(briefs=briefs)


@action(reads=["prd_content", "briefs", "provider_labels"], writes=["briefs"])
async def contrarian_briefing(
    state: State,
    *,
    squadron: PlanSquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Run the contrarian after the parallel briefings are in.

    Sequential by design — the contrarian's prompt incorporates the
    three earlier briefs and acts as a critique pass over them.
    """
    briefs = state["briefs"]
    scope_json = json.dumps(briefs.get("scope") or {}, indent=2)
    analysis_json = json.dumps(briefs.get("analysis") or {}, indent=2)
    criteria_json = json.dumps(briefs.get("criteria") or {}, indent=2)
    prompt = (
        f"## PRD Content\n\n{state['prd_content']}\n\n"
        f"## Scopist Analysis\n\n```json\n{scope_json}\n```\n\n"
        f"## Codebase Analysis\n\n```json\n{analysis_json}\n```\n\n"
        f"## Success Criteria\n\n```json\n{criteria_json}\n```\n\n"
        f"Challenge these analyses. Identify risks, blind spots, "
        f"and missing considerations."
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


@action(reads=["plan_name", "briefs"], writes=["briefing_markdown"])
async def synthesize_briefing(state: State) -> tuple[dict[str, Any], State]:
    """Render the four briefs into a single markdown block."""
    from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

    briefs = state["briefs"]
    md = serialize_briefs_to_markdown(
        state["plan_name"],
        scope=briefs.get("scope"),
        analysis=briefs.get("analysis"),
        criteria=briefs.get("criteria"),
        challenge=briefs.get("challenge"),
    )
    return {"briefing_markdown_length": len(md)}, state.update(briefing_markdown=md)


@action(
    reads=["prd_content", "briefing_markdown"],
    writes=["flight_plan"],
)
async def generate_plan(
    state: State,
    *,
    squadron: PlanSquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Hand the briefing to the generator agent."""
    await events.put(
        StepOutput(
            step_name="plan",
            message="Sending briefing to flight-plan generator",
            display_label="",
            level="info",
            source=_SOURCE,
            metadata=None,
        )
    )
    parts = [f"## PRD Content\n\n{state['prd_content']}"]
    if state["briefing_markdown"]:
        parts.append(f"## Pre-Flight Briefing\n\n{state['briefing_markdown']}")
    prompt = "\n\n".join(parts)
    payload = await squadron.generator.generate(prompt)
    plan_dict = dump_supervisor_payload(payload)
    sc_count = len(payload.success_criteria)
    await events.put(
        StepOutput(
            step_name="plan",
            message=f"Flight plan generated ({sc_count} success criteria); validating",
            display_label="",
            level="success",
            source=_SOURCE,
            metadata={"success_criteria_count": sc_count},
        )
    )
    return {"success_criteria_count": sc_count}, state.update(flight_plan=plan_dict)


@action(reads=["plan_name", "prd_content", "flight_plan"], writes=["validation_passed"])
async def validate_plan(
    state: State,
    *,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Validate the generated plan via the existing V1-V9 file validators.

    Renders the plan to markdown into a tmp file, runs the existing
    :func:`maverick.flight.validator.validate_flight_plan_file` over it,
    surfaces any issues as warnings. Same shape as
    the legacy ``PlanValidatorActor`` deleted during the Burr migration,
    just inlined here so we don't depend on a deterministic actor.
    """
    import tempfile

    from maverick.flight.validator import validate_flight_plan_file
    from maverick.workflows.generate_flight_plan.markdown import (
        render_flight_plan_markdown,
    )

    flight_plan_dict = state["flight_plan"]
    if flight_plan_dict is None:
        raise RuntimeError("validate_plan ran with no flight plan in state")

    passed = True
    warnings: tuple[str, ...] = ()
    try:
        flight_plan = SubmitFlightPlanPayload.model_validate(flight_plan_dict)
        plan_name = str(flight_plan.name or state["plan_name"] or "plan")
        markdown = render_flight_plan_markdown(
            plan_name=plan_name,
            prd_content=state["prd_content"],
            flight_plan=flight_plan,
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(markdown)
            tmp_path = Path(tmp.name)
        try:
            issues = validate_flight_plan_file(tmp_path)
            warnings = tuple(f"{issue.location}: {issue.message}" for issue in issues)
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 — preserve legacy lenient behaviour
        passed = False
        warnings = (str(exc),)

    if passed and warnings:
        await events.put(
            StepOutput(
                step_name="plan",
                message=f"Validation warnings ({len(warnings)}); continuing to write",
                display_label="",
                level="warning",
                source=_SOURCE,
                metadata={"warning_count": len(warnings)},
            )
        )
    elif passed:
        await events.put(
            StepOutput(
                step_name="plan",
                message="Validation passed",
                display_label="",
                level="success",
                source=_SOURCE,
                metadata=None,
            )
        )
    else:
        await events.put(
            StepOutput(
                step_name="plan",
                message=f"Validation errored: {warnings[0]}",
                display_label="",
                level="error",
                source=_SOURCE,
                metadata=None,
            )
        )
    return {"validation_passed": passed}, state.update(validation_passed=passed)


@action(
    reads=["plan_name", "prd_content", "flight_plan", "briefing_markdown"],
    writes=["flight_plan_path", "briefing_path"],
)
async def write_plan(
    state: State,
    *,
    output_dir: str,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Render markdown + write the plan + (optional) briefing to disk."""
    from maverick.workflows.generate_flight_plan.markdown import (
        render_flight_plan_markdown,
    )

    flight_plan_dict = state["flight_plan"]
    if flight_plan_dict is None:
        raise RuntimeError("write_plan ran with no flight plan in state")

    flight_plan = SubmitFlightPlanPayload.model_validate(flight_plan_dict)
    flight_plan_md = render_flight_plan_markdown(
        plan_name=state["plan_name"],
        prd_content=state["prd_content"],
        flight_plan=flight_plan,
    )
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    flight_plan_path = out_dir / "flight-plan.md"
    flight_plan_path.write_text(flight_plan_md, encoding="utf-8")

    briefing_path: str | None = None
    if state["briefing_markdown"]:
        briefing_file = out_dir / "preflight-briefing.md"
        briefing_file.write_text(state["briefing_markdown"], encoding="utf-8")
        briefing_path = str(briefing_file)

    sc_count = len(flight_plan.success_criteria)
    await events.put(
        StepOutput(
            step_name="plan",
            message=f"Flight plan written ({sc_count} success criteria)",
            display_label="",
            level="success",
            source=_SOURCE,
            metadata={"success_criteria_count": sc_count},
        )
    )
    return {"flight_plan_path": str(flight_plan_path)}, state.update(
        flight_plan_path=str(flight_plan_path),
        briefing_path=briefing_path,
    )
