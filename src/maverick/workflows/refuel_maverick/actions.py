"""Burr actions for the ``refuel_maverick`` workflow.

These actions *are* the ``maverick refuel`` workflow — there is no other
driver and no flag to select one.

Behaviour worth knowing before changing anything here:

* **Detail fan-out retries.** Per-unit budget is
  ``MAX_DETAIL_RETRIES = 1`` at the current tier, and a
  ``RuntimeTransientError`` spends it before escalating. Timeouts and
  persistent no-payload outcomes are final at the current tier — they
  don't escalate.
* **Tier escalation.** The ladder comes from the squadron
  (:func:`_tier_ladder`), so a rung can only name a tier the squadron
  built a distinct provider/model binding for. With no
  ``actors.refuel.decomposer.tiers`` configured the ladder is a single
  rung and nothing escalates, because there is nothing to escalate *to*.
* **Quota.** A provider limit is not a model-quality problem, so it
  neither retries nor escalates: the first unit to hit one aborts the
  whole fan-out with :class:`ProviderQuotaError` rather than letting
  every remaining unit re-hit the same wall and then building beads from
  a truncated plan.
* **Cache.** ``cache_dir = <cwd>/.maverick/plans/<plan>/refuel-cache/``
  is both written and read. :func:`init_state` seeds briefs, outline,
  and per-unit details from it; each producing action short-circuits on
  an already-populated slot. Envelopes are versioned
  (:data:`CACHE_SCHEMA_VERSION`) and fail closed — see
  :func:`_read_cache_json`.
* **Fix-round merge.** Merges both ``details`` and ``work_units`` from
  the fix payload (handles the fixer splitting an overloaded unit). New
  ``work_units`` are appended to the outline; existing ones are replaced
  by id.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from burr.core import State, action

from maverick.events import (
    AgentCompleted,
    AgentStarted,
    ProgressEvent,
    StepOutput,
)
from maverick.exceptions.quota import ProviderQuotaError, is_quota_error
from maverick.payloads import (
    SUPERVISOR_TOOL_PAYLOAD_MODELS,
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
    SupervisorInboxPayload,
    dump_supervisor_payload,
)
from maverick.squadron.tiers import DEFAULT_TIER

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
#: layout as the legacy ``REFUEL_BRIEFING_CONFIG``.
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


async def _briefing_failed(
    events: asyncio.Queue[ProgressEvent | None],
    agent_name: str,
    exc: BaseException,
) -> None:
    """Report a briefing agent failure without aborting the workflow.

    Briefings are evidence-gathering, and every downstream consumer
    already treats each brief as optional —
    :func:`~maverick.preflight_briefing.serializer.serialize_briefs_to_markdown`
    takes all four as ``| None``. So one agent failing should cost its
    brief, not the run.

    It used to cost the run: a contrarian that could not produce valid
    structured output ("max structured output retries") aborted refuel
    outright, discarding three briefs that had already succeeded (#135
    subtask 5). That is the exact case Core Principle 3 — "one agent
    failing must not crash the workflow" — exists to prevent.
    """
    await _put_output(
        events,
        "briefing",
        f"Briefing agent {agent_name!r} failed; continuing without its brief: {exc}",
        level="warning",
        metadata={"agent": agent_name, "error": str(exc)},
    )


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


#: Envelope version for every file under ``<plan>/refuel-cache/``.
#:
#: Bump whenever the *meaning* of a cached payload changes. A cache
#: written by a different version is discarded rather than adapted —
#: reusing a drifted brief or outline silently produces beads that don't
#: match the plan, which is far worse than paying for regeneration.
CACHE_SCHEMA_VERSION: int = 1

#: ``kind`` discriminators, so a file that lands in the wrong slot (a
#: copy-paste, a bad merge) is rejected instead of parsed as its neighbour.
CACHE_KIND_BRIEFINGS = "briefings"
CACHE_KIND_OUTLINE = "outline"
CACHE_KIND_DETAIL = "detail"


async def _write_cache_json(
    path: Path,
    payload: Any,
    *,
    kind: str,
    events: asyncio.Queue[ProgressEvent | None] | None,
    label: str,
) -> None:
    """Write ``payload`` to ``path`` inside a versioned envelope.

    Best-effort: any ``OSError`` (or other filesystem hiccup) is
    logged as a warning via ``events`` and swallowed so the refuel
    run still completes. Creates parent directories on demand.
    """
    envelope = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "kind": kind,
        "payload": payload,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(envelope, indent=2, default=str, sort_keys=True),
            encoding="utf-8",
        )
    except OSError as exc:
        if events is not None:
            await _put_output(
                events,
                "decompose",
                f"Refuel cache write failed ({label}): {exc}",
                level="warning",
                metadata={"path": str(path), "label": label},
            )


async def _write_briefings_cache(
    briefs: dict[str, Any],
    *,
    cache_dir: str,
    events: asyncio.Queue[ProgressEvent | None] | None,
) -> None:
    """Persist whatever briefs exist so far.

    Called after *each* briefing phase rather than once at the end. The
    cache's whole purpose is to make a failed run cheap to retry, and a
    single write at the end of the briefing sequence cannot do that — a
    contrarian failure discarded three completed briefs (#135 subtask 5).
    """
    if not cache_dir or not briefs:
        return
    await _write_cache_json(
        Path(cache_dir) / "briefings.json",
        briefs,
        kind=CACHE_KIND_BRIEFINGS,
        events=events,
        label="briefings",
    )


def _read_cache_json(path: Path, *, kind: str) -> Any | None:
    """Read a versioned cache envelope, or ``None`` if it can't be trusted.

    Fails closed on every ambiguity — missing file, unreadable file,
    malformed JSON, non-object envelope, unknown ``schema_version``, or
    a ``kind`` that doesn't match what the caller asked for. The cost of
    a wrong answer here is a plan decomposed from stale evidence; the
    cost of a false negative is one regeneration.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        envelope = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(envelope, dict):
        return None
    if envelope.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None
    if envelope.get("kind") != kind:
        return None
    # A cached ``null`` is indistinguishable from "absent" downstream, so
    # treat it as a miss rather than seeding a slot with nothing.
    return envelope.get("payload")


def _load_cached_details(cache_dir: Path) -> dict[str, dict[str, Any]]:
    """Load every per-unit detail under ``<cache_dir>/details/``.

    Returns ``{unit_id: detail}``. Individual unreadable or drifted files
    are skipped, so a partially-corrupt cache degrades to regenerating
    only the units it lost.
    """
    details_dir = cache_dir / "details"
    try:
        entries = sorted(details_dir.glob("*.json"))
    except OSError:
        return {}
    loaded: dict[str, dict[str, Any]] = {}
    for entry in entries:
        payload = _read_cache_json(entry, kind=CACHE_KIND_DETAIL)
        if not isinstance(payload, dict):
            continue
        # Trust the payload's own id over the filename: the filename is
        # derived from it at write time, but only the payload is what
        # downstream merging keys on.
        unit_id = payload.get("id") or payload.get("unit_id") or entry.stem
        if unit_id:
            loaded[str(unit_id)] = payload
    return loaded


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
        "cached_details",
        "specs",
        "fix_rounds",
        "validation_passed",
        "validation_warnings",
        "untraced_criteria",
        "epic_id",
        "epic",
        "work_beads",
        "created_map",
        "dependencies",
        "deps_wired",
        "abandoned_unit_ids",
    ],
)
async def init_state(
    state: State,
    *,
    cache_dir: str = "",
    events: asyncio.Queue[ProgressEvent | None] | None = None,
) -> tuple[dict[str, Any], State]:
    """Seed scratch slots used by downstream actions.

    When ``cache_dir`` names a populated ``refuel-cache/`` from an
    earlier run, its briefs / outline / per-unit details are loaded here
    and the actions that would have produced them short-circuit. Doing
    the disk read once, in one action, keeps every producer a pure
    function of state.

    Anything the cache can't vouch for is simply absent — see
    :func:`_read_cache_json`.
    """
    briefs: dict[str, Any] = {}
    outline_dict: dict[str, Any] | None = None
    cached_details: dict[str, dict[str, Any]] = {}

    if cache_dir:
        root = Path(cache_dir)
        cached_briefs = _read_cache_json(root / "briefings.json", kind=CACHE_KIND_BRIEFINGS)
        if isinstance(cached_briefs, dict):
            briefs = cached_briefs
        cached_outline = _read_cache_json(root / "outline.json", kind=CACHE_KIND_OUTLINE)
        if isinstance(cached_outline, dict):
            outline_dict = cached_outline
        cached_details = _load_cached_details(root)

        if events is not None and (briefs or outline_dict is not None or cached_details):
            await _put_output(
                events,
                "decompose",
                (
                    f"Reusing refuel cache: {len(briefs)} briefs, "
                    f"outline {'hit' if outline_dict else 'miss'}, "
                    f"{len(cached_details)} unit details"
                ),
                metadata={
                    "brief_count": len(briefs),
                    "outline_cached": outline_dict is not None,
                    "detail_count": len(cached_details),
                },
            )

    return {}, state.update(
        briefs=briefs,
        briefing_markdown="",
        outline=outline_dict,
        accumulated_details=[],
        cached_details=cached_details,
        specs=[],
        fix_rounds=0,
        validation_passed=False,
        validation_warnings=[],
        untraced_criteria=[],
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
    cache_dir: str = "",
) -> tuple[dict[str, Any], State]:
    """Run navigator + structuralist + recon in parallel.

    Roles already present in ``briefs`` (seeded from cache by
    :func:`init_state`) are skipped — a cached brief is the same
    evidence at zero cost.
    """
    provider_labels: dict[str, str] = state["provider_labels"]
    existing: dict[str, Any] = dict(state["briefs"])
    pending = [n for n in PARALLEL_BRIEFING_AGENTS if _ROLE_FOR[n] not in existing]
    if not pending:
        await _put_output(
            events,
            "briefing",
            "Reusing cached briefings",
            metadata={"cached_roles": sorted(existing)},
        )
        return {"briefs_collected": list(existing), "from_cache": True}, state
    sem = asyncio.Semaphore(max(1, max_concurrent))

    async def _bounded(name: str) -> tuple[str, dict[str, Any]] | None:
        async with sem:
            try:
                return await _run_one_briefing(
                    agent_name=name,
                    prompt=state["briefing_prompt"],
                    squadron=squadron,
                    events=events,
                    provider_label=provider_labels.get(_LABEL_FOR[name], ""),
                )
            except Exception as exc:  # noqa: BLE001 — see _briefing_failed
                await _briefing_failed(events, name, exc)
                return None

    results = await asyncio.gather(*(_bounded(n) for n in pending))
    briefs = existing
    for result in results:
        if result is None:
            continue
        role_key, payload_dict = result
        briefs[role_key] = payload_dict

    # Persist as soon as the parallel phase lands, not after the
    # contrarian: the contrarian is a separate agent that can fail on its
    # own, and when it did, three successful briefs (290s of work) were
    # thrown away because the only cache write sat downstream of it.
    await _write_briefings_cache(briefs, cache_dir=cache_dir, events=events)
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
    cache_dir: str = "",
) -> tuple[dict[str, Any], State]:
    """Run the contrarian after the parallel briefings are in.

    Skipped entirely when a cached contrarian brief was seeded.
    """
    from maverick.agents.briefing.prompts import build_contrarian_prompt

    briefs = state["briefs"]
    if _ROLE_FOR["contrarian"] in briefs:
        return {"contrarian_done": True, "from_cache": True}, state
    prompt = build_contrarian_prompt(
        flight_plan_content=state["raw_content"],
        navigator=briefs.get("navigator"),
        structuralist=briefs.get("structuralist"),
        recon=briefs.get("recon"),
    )
    try:
        role_key, payload_dict = await _run_one_briefing(
            agent_name="contrarian",
            prompt=prompt,
            squadron=squadron,
            events=events,
            provider_label=state["provider_labels"].get("Contrarian", ""),
        )
    except Exception as exc:  # noqa: BLE001 — see _briefing_failed
        await _briefing_failed(events, "contrarian", exc)
        return {"contrarian_done": False, "failed": True}, state

    new_briefs = dict(briefs)
    new_briefs[role_key] = payload_dict
    await _write_briefings_cache(new_briefs, cache_dir=cache_dir, events=events)
    return {"contrarian_done": True}, state.update(briefs=new_briefs)


@action(reads=["briefs"], writes=["briefing_markdown"])
async def synthesize_briefing(
    state: State,
    *,
    cache_dir: str = "",
    events: asyncio.Queue[ProgressEvent | None] | None = None,
) -> tuple[dict[str, Any], State]:
    """Render the four briefs into a single markdown block.

    When ``cache_dir`` is set, persists the raw brief payloads to
    ``<cache_dir>/briefings.json`` so a subsequent run (manual or
    automated resume) can rebuild from the same evidence without
    spending agent budget. Cache failures are non-fatal.
    """
    from maverick.preflight_briefing.serializer import serialize_briefs_to_markdown

    briefs = state["briefs"]
    md = serialize_briefs_to_markdown(
        state.get("plan_name", "refuel"),
        scope=briefs.get("navigator"),
        analysis=briefs.get("structuralist"),
        criteria=briefs.get("recon"),
        challenge=briefs.get("contrarian"),
    )
    if cache_dir and briefs:
        await _write_cache_json(
            Path(cache_dir) / "briefings.json",
            briefs,
            kind=CACHE_KIND_BRIEFINGS,
            events=events,
            label="briefings",
        )
    return {"briefing_markdown_length": len(md)}, state.update(briefing_markdown=md)


# ---------------------------------------------------------------------------
# Decomposition: outline → detail fan-out → validate (+ fix loop) → beads
# ---------------------------------------------------------------------------


#: Re-exported so this module's pool keys can't drift from the tier
#: names the squadron builds bindings for. It used to be a local
#: ``"default"`` while every other tier surface used ``"_default"``;
#: with real per-tier bindings that divergence would silently route a
#: tier lookup to the wrong (or no) override.
_DEFAULT_TIER = DEFAULT_TIER


@action(
    reads=["raw_content", "codebase_context", "briefing_markdown", "open_bead_context"],
    writes=["outline"],
)
async def outline(
    state: State,
    *,
    squadron: RefuelSquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cache_dir: str = "",
) -> tuple[dict[str, Any], State]:
    """Acquire a decomposer from the pool and run the outline pass.

    Short-circuits when :func:`init_state` already seeded an outline from
    ``<cache_dir>/outline.json``. Otherwise persists the outline payload
    there after the agent returns. Cache failures are non-fatal.
    """
    if state["outline"] is not None:
        cached_units = len(state["outline"].get("work_units", ()))
        await _put_output(
            events,
            "decompose",
            f"Reusing cached outline ({cached_units} work units)",
            metadata={"work_unit_count": cached_units, "from_cache": True},
        )
        return {"work_unit_count": cached_units, "from_cache": True}, state

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
    if cache_dir:
        await _write_cache_json(
            Path(cache_dir) / "outline.json",
            outline_dict,
            kind=CACHE_KIND_OUTLINE,
            events=events,
            label="outline",
        )
    return {"work_unit_count": unit_count}, state.update(outline=outline_dict)


def _tier_ladder(squadron: RefuelSquadron) -> tuple[str, ...]:
    """The tier names a failed unit escalates along, cheapest-first.

    Sourced from the squadron so the ladder can never name a tier whose
    binding the squadron wouldn't actually vary. Falls back to the
    base-binding-only ladder for stub squadrons in tests.
    """
    ladder = getattr(squadron, "decomposer_escalation_ladder", None)
    if ladder is None:
        return (_DEFAULT_TIER,)
    return ladder() or (_DEFAULT_TIER,)


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

    Transient errors consume the same-tier retry budget before they are
    reported. They used to short-circuit it and rely on the escalation
    ladder for a second attempt, which only worked because every tier
    resolved to the same binding; now that the ladder climbs real
    bindings (and is empty when none are configured), the same-binding
    retry a network blip needs has to happen here.
    """
    from airframe.errors import RuntimeBudgetExceededError, RuntimeTransientError

    label = unit_id
    await events.put(AgentStarted(step_name="decompose", agent_name=label, provider=""))
    t0 = time.monotonic()
    attempts = retries_remaining + 1
    last_payload: dict[str, Any] | None = None
    failure_kind = "no_payload"
    last_error: str | None = None
    try:
        for attempt in range(attempts):
            try:
                payload = await decomposer.detail(unit_ids=(unit_id,))
            except TimeoutError:
                if attempt + 1 >= attempts:
                    failure_kind = "timeout"
                    last_error = "timed out"
                    break
                continue
            except RuntimeBudgetExceededError as exc:
                raise ProviderQuotaError(str(exc), agent_name=f"decomposer:{unit_id}") from exc
            except RuntimeTransientError as exc:
                # Some providers report a hard quota as a transient
                # 429/5xx. Retrying or escalating that burns wall-clock
                # against a limit that won't move until it resets.
                if is_quota_error(str(exc)):
                    raise ProviderQuotaError(str(exc), agent_name=f"decomposer:{unit_id}") from exc
                failure_kind = "transient"
                last_error = str(exc)
                if attempt + 1 >= attempts:
                    break
                continue
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
    except ProviderQuotaError as exc:
        # Close out the agent's progress row before unwinding, or the
        # UI leaves a spinner running for a unit that will never finish.
        await events.put(
            AgentCompleted(
                step_name="decompose",
                agent_name=label,
                duration_seconds=time.monotonic() - t0,
                success=False,
                error=str(exc),
            )
        )
        raise

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

    On ``RuntimeTransientError`` that survives the same-tier retry
    budget, moves to the next tier on the squadron's ladder
    (:func:`_tier_ladder`) and re-acquires a decomposer bound to that
    tier's model. Returns the unit's detail payload on success or
    ``None`` once the ladder is exhausted (or a non-transient failure
    terminates the loop). Timeouts and persistent no-payload outcomes
    are treated as final at the current tier — they don't escalate.

    :class:`ProviderQuotaError` propagates untouched: a exhausted
    provider limit is not a model-quality problem, so climbing the tier
    ladder just spends wall-clock re-hitting the same wall. The caller
    aborts the run.
    """
    ladder = _tier_ladder(squadron)
    for level, tier in enumerate(ladder):
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
        if failure != "transient" or level + 1 >= len(ladder):
            return None
        next_tier = ladder[level + 1]
        await _put_output(
            events,
            "decompose",
            f"Unit {unit_id}: transient failure on tier '{tier}'; escalating to '{next_tier}'",
            level="warning",
            metadata={"unit_id": unit_id, "from_tier": tier, "to_tier": next_tier},
        )
    return None


@action(
    reads=["outline", "cached_details"],
    writes=["accumulated_details", "abandoned_unit_ids"],
)
async def detail_fan_out(
    state: State,
    *,
    squadron: RefuelSquadron,
    events: asyncio.Queue[ProgressEvent | None],
    pool_size: int,
    cache_dir: str = "",
) -> tuple[dict[str, Any], State]:
    """Fan out per-unit detail requests across the decomposer pool.

    Per-unit retry budget is ``MAX_DETAIL_RETRIES`` at the current
    tier; transient failures escalate via
    :func:`_run_detail_with_escalation`. When ``cache_dir`` is set,
    each successful unit detail is persisted to
    ``<cache_dir>/details/<unit_id>.json`` immediately so a
    partially-successful fan-out is recoverable — and units already
    present in ``cached_details`` are not requested again. Cache reuse
    is per unit, so a run that abandoned half its units re-requests only
    those.
    """
    outline_dict = state["outline"]
    if outline_dict is None:
        raise RuntimeError("detail_fan_out ran without an outline")

    unit_ids = [u["id"] for u in outline_dict.get("work_units", []) if u.get("id")]
    if not unit_ids:
        return {"unit_count": 0}, state

    cached: dict[str, dict[str, Any]] = state.get("cached_details") or {}
    # Only reuse details for units this outline still contains — a
    # regenerated outline may have dropped or renamed a unit, and a
    # detail for a unit that no longer exists must not enter the merge.
    reused = [cached[uid] for uid in unit_ids if uid in cached]
    pending_ids = [uid for uid in unit_ids if uid not in cached]

    if reused:
        await _put_output(
            events,
            "decompose",
            f"Reusing {len(reused)} cached unit details",
            metadata={"reused": len(reused), "pending": len(pending_ids)},
        )
    if not pending_ids:
        return (
            {"completed_count": len(reused), "abandoned_count": 0, "from_cache": True},
            state.update(accumulated_details=list(reused), abandoned_unit_ids=[]),
        )

    await _put_output(events, "decompose", f"Requesting details for {len(pending_ids)} units")
    sem = asyncio.Semaphore(max(1, pool_size))
    accumulated: list[dict[str, Any]] = list(reused)
    abandoned: list[str] = []
    lock = asyncio.Lock()
    details_dir = Path(cache_dir) / "details" if cache_dir else None

    # Set by the first unit to hit a provider limit. Once it is set,
    # every other in-flight and queued unit gives up immediately: the
    # limit is account-wide, so the remaining requests would each burn a
    # round-trip to be told the same thing.
    quota_error: ProviderQuotaError | None = None

    async def _one(unit_id: str) -> None:
        nonlocal quota_error
        if quota_error is not None:
            async with lock:
                abandoned.append(unit_id)
            return
        async with sem:
            if quota_error is not None:
                async with lock:
                    abandoned.append(unit_id)
                return
            try:
                detail = await _run_detail_with_escalation(
                    unit_id=unit_id,
                    squadron=squadron,
                    retries_remaining=MAX_DETAIL_RETRIES,
                    events=events,
                )
            except ProviderQuotaError as exc:
                async with lock:
                    if quota_error is None:
                        quota_error = exc
                    abandoned.append(unit_id)
                return
        async with lock:
            if detail is None:
                abandoned.append(unit_id)
            else:
                accumulated.append(detail)
        if detail is not None and details_dir is not None:
            await _write_cache_json(
                details_dir / f"{unit_id}.json",
                detail,
                kind=CACHE_KIND_DETAIL,
                events=events,
                label=f"detail/{unit_id}",
            )

    await asyncio.gather(*(_one(u) for u in pending_ids))

    if quota_error is not None:
        reset_hint = (
            f" Provider limit resets {quota_error.reset_time}." if quota_error.reset_time else ""
        )
        await _put_output(
            events,
            "decompose",
            (
                f"Provider quota exhausted during detail fan-out; aborting refuel. "
                f"{len(accumulated)} unit details were cached and will be reused on "
                f"re-run.{reset_hint}"
            ),
            level="error",
            metadata={
                "quota_exhausted": True,
                "cached_details": len(accumulated),
                "abandoned": len(abandoned),
                "reset_time": quota_error.reset_time,
            },
        )
        # Abort rather than proceeding to validate/create_beads: a plan
        # decomposed from a truncated fan-out would produce beads that
        # silently omit most of the work. Everything completed so far is
        # already on disk under the refuel cache, so a re-run after the
        # limit resets picks up where this left off.
        raise quota_error

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
    writes=["specs", "validation_passed", "validation_warnings", "untraced_criteria"],
)
async def validate(
    state: State,
    *,
    events: asyncio.Queue[ProgressEvent | None],
    expected_sc_refs: tuple[str, ...] = (),
    sc_count: int = 0,
) -> tuple[dict[str, Any], State]:
    """Run the deterministic decomposition validator."""
    from maverick.library.actions.decompose import validate_decomposition
    from maverick.workflows.refuel_maverick.models import WorkUnitSpec

    outline_dict = state["outline"]
    if outline_dict is None:
        raise RuntimeError("validate ran without an outline")

    from maverick.library.actions.decompose import SCTraceabilityError

    specs = _merge_to_specs(outline_dict, state["accumulated_details"])
    # ``validate_decomposition`` returns a list of soft warnings on
    # success (empty == passed) and *raises* on schema-level issues.
    # Two classes of raise, deliberately handled differently:
    #
    # * ``SCTraceabilityError`` — untraced success criteria. Advisory:
    #   cross-cutting constraints ("total LOC <= 500", "lint passes")
    #   can never be traced to one work unit, so failing on them sends
    #   the fix loop after a gap it cannot close. Recorded and shown,
    #   but does not fail validation.
    # * Everything else (cycles, dangling depends_on, overloaded units)
    #   — genuinely fixable, so it still fails and drives the fix loop.
    gaps: list[str] = []
    advisory: list[str] = []
    try:
        spec_models = [WorkUnitSpec.model_validate(s) for s in specs]
        result = validate_decomposition(
            spec_models,
            success_criteria_count=sc_count,
            expected_sc_refs=list(expected_sc_refs) if expected_sc_refs else None,
        )
        gaps = list(result)
    except SCTraceabilityError as exc:
        advisory = list(exc.gaps)
    except ValueError as exc:
        gaps = [str(exc)]
    passed = not gaps

    if advisory:
        # Name the criteria. The count alone told an operator nothing —
        # and cost two live debugging sessions to work around (#135).
        await _put_output(
            events,
            "decompose",
            (
                f"{len(advisory)} success criterion/criteria not traced to a work unit "
                f"(not blocking — cross-cutting constraints usually can't be): "
                + "; ".join(advisory)
            ),
            level="warning",
            metadata={"untraced_count": len(advisory), "untraced": advisory},
        )

    if passed:
        await _put_output(events, "decompose", "Validation passed", level="success")
    else:
        await _put_output(
            events,
            "decompose",
            f"Validation found {len(gaps)} gap(s): " + "; ".join(gaps),
            level="warning",
            metadata={"gap_count": len(gaps), "gaps": gaps},
        )

    return {"passed": passed, "gap_count": len(gaps)}, state.update(
        specs=specs,
        validation_passed=passed,
        # Kept separate from ``untraced_criteria`` on purpose:
        # ``request_fix`` builds the fixer's prompt from this slot, and
        # advisory gaps must never reach it — that is precisely how the
        # fixer ends up chasing an uncloseable criterion.
        validation_warnings=list(gaps),
        untraced_criteria=list(advisory),
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
    from maverick.workspace import CheckoutPath

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
        cwd=CheckoutPath(Path(cwd)),
    )

    extracted_deps = _extract_deps(specs)
    wire_result = None
    if extracted_deps:
        wire_result = await wire_dependencies(
            work_definitions=work_defs,
            created_map=creation.created_map,
            tasks_content="",
            extracted_deps=json.dumps(extracted_deps),
            cwd=CheckoutPath(Path(cwd)),
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
