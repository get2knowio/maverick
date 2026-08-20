"""Burr actions for the ``fly_beads`` workflow.

The ``maverick fly`` bead loop runs through these actions exclusively —
the drain loop is Burr-driven end to end (the earlier xoscar-actor
``FlySupervisor`` is retired). Each stage's shape mirrors that retired
supervisor for behavioural parity: the action layer holds the same
fix-loop budgets (``MAX_GATE_FIX_ATTEMPTS``, ``MAX_REVIEW_ROUNDS``) and
routes through the same ``squadron.coder_for(tier)`` /
``squadron.correctness_reviewer_for(tier)`` agents. Graceful stop, watch
mode, aggregate cross-bead review, human-bead creation on review
exhaustion, reviewer/implementer transient-failure escalation, and the
Rust spec-check rules (``.unwrap()`` / ``.expect()`` /
``std::process::Command`` in async contexts) are all wired up here.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from burr.core import State, action

from maverick.assumptions.suggestions import attach_suggestions
from maverick.events import (
    AgentCompleted,
    AgentStarted,
    ContextFileWriteBlocked,
    ProgressEvent,
    StepOutput,
)
from maverick.payloads import dump_supervisor_payload
from maverick.squadron.tiers import DEFAULT_TIER as _DEFAULT_TIER

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.squadron.fly import FlySquadron
    from maverick.workspace import CheckoutPath


__all__ = [
    "AGGREGATE_REVIEW_THRESHOLD",
    "DEFAULT_TIER",
    "MAX_GATE_FIX_ATTEMPTS",
    "MAX_REVIEW_ROUNDS",
    "MAX_SPEC_FIX_ATTEMPTS",
    "abandon_bead",
    "ac_check",
    "aggregate_review",
    "commit",
    "create_human_bead",
    "gate",
    "implement",
    "init_state",
    "process_bead_start",
    "record_assumptions",
    "record_outcome",
    "reconcile_answers",
    "reconcile_answers_final",
    "review",
    "select_next_bead",
    "spec_check",
]

# Fix budgets — preserved from the pre-Burr supervisor.
MAX_REVIEW_ROUNDS: int = 3
MAX_GATE_FIX_ATTEMPTS: int = 2
MAX_SPEC_FIX_ATTEMPTS: int = 2

# Aggregate review runs once after the bead loop when at least this
# many beads have completed in the current run.
AGGREGATE_REVIEW_THRESHOLD: int = 2

#: Re-exported from the shared tier module so this module's tier keys
#: can't drift from the names the squadron builds bindings for.
DEFAULT_TIER: str = _DEFAULT_TIER

_SOURCE = "fly-burr"


def _payload_assumptions(payload: Any) -> list[dict[str, Any]]:
    """Extract a dumped ``assumptions`` list from a Submit*Payload or its dumped dict."""
    if payload is None:
        return []
    dumped = payload if isinstance(payload, dict) else dump_supervisor_payload(payload)
    return list(dumped.get("assumptions") or [])


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


async def _drain_protection_blocks(
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    state: State,
) -> list[dict[str, Any]]:
    """Drain the squadron's block collector, emit one event per record, and
    return the extended ``protection_blocks`` list to merge into state.

    Safe to call unconditionally — a squadron whose protection setup
    degraded (``block_collector is None``, see
    ``Squadron._build_protection``) is a no-op, matching every agent's own
    zero-behavior-change fallback (056-context-file-protection).
    """
    collector = getattr(squadron, "block_collector", None)
    if collector is None:
        return list(state.get("protection_blocks") or [])
    records = collector.drain()
    dicts = [r.to_dict() for r in records]
    for payload in dicts:
        # ``BlockRecord.to_dict()`` and the event's field set are the
        # same projection by contract (contracts/block-event.md); splat
        # rather than restating nine fields the two must agree on.
        await events.put(ContextFileWriteBlocked(**payload))
    return [*(state.get("protection_blocks") or []), *dicts]


async def _with_protection_drain(
    result_and_state: tuple[dict[str, Any], State],
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Wrap an agent-calling action's ``(result, state)`` return, merging
    ``protection_blocks`` on top of whatever fields the action's own
    logic already wrote. One call site per action — see each action's
    trailing ``return await _with_protection_drain(...)``.
    """
    result, new_state = result_and_state
    blocks = await _drain_protection_blocks(squadron, events, new_state)
    return result, new_state.update(protection_blocks=blocks)


# ---------------------------------------------------------------------------
# Outer-loop actions
# ---------------------------------------------------------------------------


@action(
    reads=[],
    writes=[
        "completed_bead_ids",
        "bead_events",
        "processed_count",
        "succeeded_count",
        "failed_count",
        "skipped_count",
    ],
)
async def init_state(state: State) -> tuple[dict[str, Any], State]:
    """Seed outer-loop counters + per-run accumulators."""
    return {}, state.update(
        completed_bead_ids=list(state.get("completed_bead_ids") or ()),
        bead_events=[],
        processed_count=0,
        succeeded_count=0,
        failed_count=0,
        skipped_count=0,
    )


@action(
    reads=["completed_bead_ids", "processed_count", "idle_polls", "isolation_halt_reason"],
    writes=[
        "current_bead",
        "current_bead_id",
        "loop_done",
        "loop_done_reason",
        "fix_round",
        "bead_aborted",
        "bead_failed",
        "needs_human_review",
        "review_rounds",
        "idle_polls",
    ],
)
async def select_next_bead(
    state: State,
    *,
    epic_id: str,
    cwd: str,
    max_beads: int,
    events: asyncio.Queue[ProgressEvent | None],
    watch: bool = False,
    watch_interval: int = 30,
    max_idle_polls: int = 60,
) -> tuple[dict[str, Any], State]:
    """Pick the next ready bead — or signal end-of-stream.

    Five conditions terminate the loop:

    1. Graceful-stop flag has been set (Ctrl-C between beads).
    2. ``max_beads`` cap reached (``0`` means unlimited).
    3. No ready bead is available AND ``watch`` is false.
    4. No ready bead is available AND ``watch`` is true but the
       ``max_idle_polls`` cap is reached.
    5. Isolated mode (057) hit an undo failure — ``isolation_halt_reason``
       is set. This is the worst state the isolation primitive can
       produce (FR-018); no further bead may start, full stop, never
       cleared once set.

    In watch mode (case 4), when ``bd`` reports no ready bead and the
    idle cap hasn't been hit yet, the action sleeps ``watch_interval``
    seconds, increments ``idle_polls``, and leaves ``current_bead=None``
    so the graph cycles back into ``select_next_bead`` for another try.
    """
    from maverick.library.actions.beads import select_next_bead as bd_select
    from maverick.workflows.fly_beads.graceful_stop import (
        is_graceful_stop_requested,
    )
    from maverick.workspace import CheckoutPath

    if state.get("isolation_halt_reason"):
        return {"loop_done": True, "loop_done_reason": "isolation_halt"}, state.update(
            loop_done=True,
            loop_done_reason="isolation_halt",
            current_bead=None,
            current_bead_id="",
        )

    if is_graceful_stop_requested():
        await _put_output(
            events,
            "fly",
            "Graceful stop requested — exiting bead loop",
            level="warning",
        )
        return {"loop_done": True, "loop_done_reason": "graceful_stop"}, state.update(
            loop_done=True,
            loop_done_reason="graceful_stop",
            current_bead=None,
            current_bead_id="",
        )

    if max_beads and state["processed_count"] >= max_beads:
        return {"loop_done": True, "loop_done_reason": "max_beads"}, state.update(
            loop_done=True,
            loop_done_reason="max_beads",
            current_bead=None,
            current_bead_id="",
        )

    result = await bd_select(epic_id=epic_id, cwd=CheckoutPath(Path(cwd)))
    bead_dict = result.to_dict()
    if not bead_dict.get("found"):
        idle_polls = int(state.get("idle_polls", 0))
        if watch and idle_polls < max_idle_polls:
            idle_polls += 1
            await _put_output(
                events,
                "fly",
                f"No beads ready; waiting ({idle_polls}/{max_idle_polls})",
            )
            await asyncio.sleep(max(0, watch_interval))
            return {"loop_done": False, "idle_poll": idle_polls}, state.update(
                current_bead=None,
                current_bead_id="",
                loop_done=False,
                idle_polls=idle_polls,
            )
        reason = "watch_idle_exhausted" if watch else "no_more_beads"
        return {"loop_done": True, "loop_done_reason": reason}, state.update(
            loop_done=True,
            loop_done_reason=reason,
            current_bead=None,
            current_bead_id="",
        )

    bead_id = bead_dict["bead_id"]
    completed: list[str] = list(state["completed_bead_ids"])
    if bead_id in completed:
        # Already done in a prior run (resumed from checkpoint) — skip.
        return {"loop_done": False, "skipped": bead_id}, state.update(
            current_bead=None,
            current_bead_id="",
            loop_done=False,
            skipped_count=state.get("skipped_count", 0) + 1,
            idle_polls=0,
        )

    return {"loop_done": False, "current_bead_id": bead_id}, state.update(
        current_bead=bead_dict,
        current_bead_id=bead_id,
        loop_done=False,
        fix_round=0,
        bead_aborted=False,
        bead_failed=False,
        needs_human_review=False,
        review_rounds=0,
        idle_polls=0,
        reviewer_escalation_level=0,
        implementer_escalation_level=0,
    )


@action(
    reads=["current_bead"],
    writes=[
        "bead_aborted",
        "bead_failed",
        "needs_human_review",
        "pending_assumptions",
        "recorded_assumption_ids",
        "commit_change_id",
    ],
)
async def process_bead_start(state: State) -> tuple[dict[str, Any], State]:
    """Reset per-bead state slots before the per-stage pipeline runs.

    ``pending_assumptions``/``recorded_assumption_ids`` are reset here so a
    bead can never re-record or re-stamp the previous bead's ledger
    entries. ``commit_change_id`` is reset alongside them purely as
    observability — it exposes the landed jj change ID for this bead in the
    final burr state and feeds nothing downstream (stamping uses the local
    change ID captured inside ``commit``).
    """
    return {"bead_id": state["current_bead_id"]}, state.update(
        bead_aborted=False,
        bead_failed=False,
        needs_human_review=False,
        pending_assumptions=[],
        recorded_assumption_ids=[],
        commit_change_id="",
    )


# ---------------------------------------------------------------------------
# Per-bead pipeline
# ---------------------------------------------------------------------------


@action(
    reads=[
        "current_bead",
        "current_bead_id",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
        "isolated",
        "workspace_path",
    ],
    writes=[
        "implement_ok",
        "implement_summary",
        "bead_aborted",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
    ],
)
async def implement(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Run the implementer on the current bead, escalating on transient failures.

    Isolated mode (057): the entire call is scoped to the bead's workspace
    (FR-032) — delegation only, see `_isolation.agent_step_scope`.
    """
    from maverick.workflows.fly_beads._isolation import agent_step_scope

    async with agent_step_scope(state):
        return await _with_protection_drain(
            await _implement_impl(state, squadron=squadron, events=events),
            squadron=squadron,
            events=events,
        )


async def _implement_impl(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    bead = state["current_bead"]
    if bead is None:
        return {"ok": False}, state.update(implement_ok=False, bead_aborted=True)

    prompt = _build_implement_prompt(bead)
    initial_level = int(state.get("implementer_escalation_level") or 0)
    payload, new_level, exhausted_err = await _call_implementer_with_escalation(
        squadron=squadron,
        events=events,
        bead_id=state["current_bead_id"],
        prompt=prompt,
        op="implement",
        label="Implementer",
        initial_level=initial_level,
    )
    if payload is None:
        # Exhausted escalation (transient) or hit a non-transient
        # error — both already logged inside the helper.
        return {"ok": False, "error": exhausted_err or "implement_failed"}, state.update(
            implement_ok=False,
            bead_aborted=True,
            implementer_escalation_level=new_level,
        )

    summary = dump_supervisor_payload(payload)
    pending = [*(state.get("pending_assumptions") or ()), *_payload_assumptions(summary)]
    return {"ok": True}, state.update(
        implement_ok=True,
        implement_summary=summary,
        implementer_escalation_level=new_level,
        pending_assumptions=pending,
    )


def _build_implement_prompt(bead: dict[str, Any]) -> str:
    """Mirror the retired xoscar-era ``FlySupervisor._build_implement_prompt``'s shape."""
    title = bead.get("title", "")
    description = bead.get("description", "")
    return (
        f"## Bead: {bead.get('bead_id', '?')}\n\n"
        f"### {title}\n\n"
        f"{description}\n\n"
        "Implement this work unit. Submit your implementation summary "
        "via the StructuredOutput tool when done."
    )


async def _run_fix(
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    bead_id: str,
    phase: str,
    round_n: int,
    failure_message: str,
    initial_level: int = 0,
) -> tuple[bool, int, list[dict[str, Any]]]:
    """Re-prompt the implementer on validation failure.

    Returns ``(ok, new_level, assumptions)`` where ``ok`` is true when the
    agent landed a fix payload, ``new_level`` is the implementer escalation
    level the caller should persist on state, and ``assumptions`` is the
    dumped ``assumptions`` list from the fix-result payload (empty on
    failure). Transient failures bump the tier and retry; non-transient
    failures (or exhausted escalation) return ``(False, current_level, [])``.
    """
    prompt = (
        f"## Fix request — phase: {phase}, round {round_n}\n\n"
        f"The {phase} check failed with:\n\n{failure_message}\n\n"
        "Address the failure and submit a fix-result payload via the "
        "StructuredOutput tool."
    )
    label = f"Fix ({phase} r{round_n})"
    payload, new_level, _ = await _call_implementer_with_escalation(
        squadron=squadron,
        events=events,
        bead_id=bead_id,
        prompt=prompt,
        op="fix",
        label=label,
        initial_level=initial_level,
    )
    return payload is not None, new_level, _payload_assumptions(payload)


@action(
    reads=[
        "current_bead_id",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
        "isolated",
    ],
    writes=[
        "gate_passed",
        "bead_aborted",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
        "gate_failure_summary",
        "unverified_in_checkout",
    ],
)
async def gate(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
    validation_commands: dict[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, Any], State]:
    """Run the format/lint/test gate.

    Non-isolated: fix-retry up to ``MAX_GATE_FIX_ATTEMPTS`` internally
    (unchanged, FR-035 — byte-identical to before this feature).

    Isolated mode (057): **always** bound to the checkout, never the
    workspace (T074 — needs the installed toolchain, which is gitignored
    and does not travel into a workspace). Single-shot: retries are
    graph-level (``fold_back -> gate -> undo_fold_back -> gate_fix ->
    fold_back -> gate ...``, see ``burr_graph.py`` and ``_isolation.py``),
    not an internal loop here, because a retry needs the checkout undone
    and the fix applied in the workspace before the gate can run again.
    """
    if state.get("isolated"):
        return await _with_protection_drain(
            await _gate_impl_isolated(state, cwd=cwd, validation_commands=validation_commands),
            squadron=squadron,
            events=events,
        )
    return await _with_protection_drain(
        await _gate_impl(
            state,
            squadron=squadron,
            events=events,
            cwd=cwd,
            validation_commands=validation_commands,
        ),
        squadron=squadron,
        events=events,
    )


async def _gate_impl_isolated(
    state: State,
    *,
    cwd: str,
    validation_commands: dict[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, Any], State]:
    """Isolated mode's single-shot gate check — see ``gate``'s docstring
    for why retries live in the graph instead of here."""
    from maverick.library.actions.validation import run_independent_gate

    result = await run_independent_gate(
        stages=["format", "lint", "test"],
        cwd=cwd,
        validation_commands=validation_commands,
    )
    if result.get("passed"):
        # The checkout's folded-back delta just passed the gate — reset
        # unverified_in_checkout here (not only in undo_fold_back's
        # success path), so it doesn't stay stuck True through the rest
        # of this bead and into the next one on the common happy path
        # (fold_back -> gate passes first try, no undo round).
        return {"passed": True}, state.update(
            gate_passed=True, gate_failure_summary="", unverified_in_checkout=False
        )

    summary = result.get("summary") or "gate failed"
    return {"passed": False}, state.update(gate_passed=False, gate_failure_summary=summary)


async def _gate_impl(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
    validation_commands: dict[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, Any], State]:
    from maverick.library.actions.validation import run_independent_gate

    bead_id = state["current_bead_id"]
    escalation_level = int(state.get("implementer_escalation_level") or 0)
    pending = list(state.get("pending_assumptions") or ())
    for attempt in range(MAX_GATE_FIX_ATTEMPTS + 1):
        result = await run_independent_gate(
            stages=["format", "lint", "test"],
            cwd=cwd,
            validation_commands=validation_commands,
        )
        if result.get("passed"):
            return {"passed": True, "attempts": attempt + 1}, state.update(
                gate_passed=True,
                implementer_escalation_level=escalation_level,
                pending_assumptions=pending,
            )
        if attempt >= MAX_GATE_FIX_ATTEMPTS:
            summary = result.get("summary") or "gate failed"
            await _put_output(
                events,
                "gate",
                f"Gate fix attempts exhausted: {summary}",
                level="error",
            )
            return {"passed": False}, state.update(
                gate_passed=False,
                bead_aborted=True,
                implementer_escalation_level=escalation_level,
                pending_assumptions=pending,
            )
        summary = result.get("summary") or "gate failed"
        await _put_output(
            events,
            "gate",
            f"Gate failed ({attempt + 1}/{MAX_GATE_FIX_ATTEMPTS}); requesting fix",
            level="warning",
            metadata={"attempt": attempt + 1},
        )
        ok, escalation_level, fix_assumptions = await _run_fix(
            squadron=squadron,
            events=events,
            bead_id=bead_id,
            phase="gate",
            round_n=attempt + 1,
            failure_message=summary,
            initial_level=escalation_level,
        )
        pending.extend(fix_assumptions)
        if not ok:
            return {"passed": False, "fix_failed": True}, state.update(
                gate_passed=False,
                bead_aborted=True,
                implementer_escalation_level=escalation_level,
                pending_assumptions=pending,
            )
    # unreachable but satisfies type checker
    return {"passed": False}, state.update(
        gate_passed=False,
        bead_aborted=True,
        implementer_escalation_level=escalation_level,
        pending_assumptions=pending,
    )


@action(
    reads=[
        "current_bead",
        "current_bead_id",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
        "isolated",
        "workspace_path",
    ],
    writes=[
        "ac_passed",
        "bead_aborted",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
    ],
)
async def ac_check(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
) -> tuple[dict[str, Any], State]:
    """Run the AC (verification commands) check. One fix retry.

    Isolated mode (057): artifact-level — runs against the bead's
    workspace, not the checkout (research.md R6) — and any fix round
    stays there too (FR-032). Delegation only, see
    ``_isolation.effective_check_cwd``/``agent_step_scope``.
    """
    from maverick.workflows.fly_beads._isolation import agent_step_scope, effective_check_cwd

    effective_cwd = effective_check_cwd(state, cwd)
    async with agent_step_scope(state):
        return await _with_protection_drain(
            await _ac_check_impl(state, squadron=squadron, events=events, cwd=effective_cwd),
            squadron=squadron,
            events=events,
        )


async def _ac_check_impl(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
) -> tuple[dict[str, Any], State]:
    from maverick.runners.command import CommandRunner
    from maverick.workflows.fly_beads.steps import (
        _parse_verification_commands,
        _parse_work_unit_sections,
    )

    bead = state["current_bead"]
    bead_id = state["current_bead_id"]
    description = bead.get("description", "") if bead else ""
    escalation_level = int(state.get("implementer_escalation_level") or 0)
    pending = list(state.get("pending_assumptions") or ())

    async def _run_once() -> tuple[bool, str]:
        sections = _parse_work_unit_sections(description)
        verification_text = sections.get("verification", "")
        if not verification_text:
            return True, ""
        runner = CommandRunner(cwd=Path(cwd))
        reasons: list[str] = []
        for cmd_str in _parse_verification_commands(verification_text):
            first_word = cmd_str.split()[0] if cmd_str.split() else ""
            if first_word not in ("rg", "grep", "cargo", "make"):
                continue
            try:
                result = await runner.run(["sh", "-c", cmd_str])
                if result.returncode != 0:
                    reasons.append(f"Verification failed: `{cmd_str}`")
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"Verification error: `{cmd_str}`: {exc}")
        return (not reasons), "; ".join(reasons)

    passed, reasons = await _run_once()
    if passed:
        return {"passed": True}, state.update(
            ac_passed=True,
            implementer_escalation_level=escalation_level,
            pending_assumptions=pending,
        )

    await _put_output(
        events,
        "ac",
        f"AC check failed; requesting fix: {reasons}",
        level="warning",
    )
    ok, escalation_level, fix_assumptions = await _run_fix(
        squadron=squadron,
        events=events,
        bead_id=bead_id,
        phase="ac",
        round_n=1,
        failure_message=reasons,
        initial_level=escalation_level,
    )
    pending.extend(fix_assumptions)
    if not ok:
        return {"passed": False}, state.update(
            ac_passed=False,
            bead_aborted=True,
            implementer_escalation_level=escalation_level,
            pending_assumptions=pending,
        )

    passed, reasons = await _run_once()
    if not passed:
        await _put_output(events, "ac", f"AC check failed after fix: {reasons}", level="error")
        return {"passed": False}, state.update(
            ac_passed=False,
            bead_aborted=True,
            implementer_escalation_level=escalation_level,
            pending_assumptions=pending,
        )
    return {"passed": True}, state.update(
        ac_passed=True,
        implementer_escalation_level=escalation_level,
        pending_assumptions=pending,
    )


@action(
    reads=[
        "current_bead_id",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
        "isolated",
        "workspace_path",
    ],
    writes=[
        "spec_passed",
        "bead_aborted",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
    ],
)
async def spec_check(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
    project_type: str = "rust",
) -> tuple[dict[str, Any], State]:
    """Run the grep-based spec-compliance checks.

    Rust-specific rules: ``.unwrap()`` / ``.expect()`` in runtime code,
    ``std::process::Command`` in async paths. Other project types are
    a no-op pass.

    Mirrors the legacy ``SpecCheckActor`` fix-loop: on findings, ask
    the implementer to fix them and re-run, up to
    ``MAX_SPEC_FIX_ATTEMPTS`` rounds. Abandon the bead on exhaustion.

    Isolated mode (057): artifact-level — runs against the bead's
    workspace, not the checkout (research.md R6) — and any fix round
    stays there too (FR-032). Delegation only.
    """
    from maverick.workflows.fly_beads._isolation import agent_step_scope, effective_check_cwd

    effective_cwd = effective_check_cwd(state, cwd)
    async with agent_step_scope(state):
        return await _with_protection_drain(
            await _spec_check_impl(
                state,
                squadron=squadron,
                events=events,
                cwd=effective_cwd,
                project_type=project_type,
            ),
            squadron=squadron,
            events=events,
        )


async def _spec_check_impl(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
    project_type: str = "rust",
) -> tuple[dict[str, Any], State]:
    from maverick.workflows.fly_beads._spec_check import run_spec_check

    bead_id = state["current_bead_id"]
    escalation_level = int(state.get("implementer_escalation_level") or 0)
    pending = list(state.get("pending_assumptions") or ())

    for attempt in range(MAX_SPEC_FIX_ATTEMPTS + 1):
        result = run_spec_check(cwd=cwd, project_type=project_type)
        if result.passed:
            if attempt > 0 or result.findings:
                await _put_output(
                    events,
                    "spec",
                    f"Spec check passed: {result.details}",
                    level="success",
                )
            return {"passed": True, "attempts": attempt + 1}, state.update(
                spec_passed=True,
                implementer_escalation_level=escalation_level,
                pending_assumptions=pending,
            )

        summary = "; ".join(result.findings) or result.details
        if attempt >= MAX_SPEC_FIX_ATTEMPTS:
            await _put_output(
                events,
                "spec",
                f"Spec fix attempts exhausted: {summary}",
                level="error",
                metadata={"findings_count": len(result.findings)},
            )
            return {"passed": False}, state.update(
                spec_passed=False,
                bead_aborted=True,
                implementer_escalation_level=escalation_level,
                pending_assumptions=pending,
            )

        await _put_output(
            events,
            "spec",
            f"Spec failed ({attempt + 1}/{MAX_SPEC_FIX_ATTEMPTS}); requesting fix",
            level="warning",
            metadata={"findings_count": len(result.findings)},
        )
        ok, escalation_level, fix_assumptions = await _run_fix(
            squadron=squadron,
            events=events,
            bead_id=bead_id,
            phase="spec",
            round_n=attempt + 1,
            failure_message=summary,
            initial_level=escalation_level,
        )
        pending.extend(fix_assumptions)
        if not ok:
            return {"passed": False, "fix_failed": True}, state.update(
                spec_passed=False,
                bead_aborted=True,
                implementer_escalation_level=escalation_level,
                pending_assumptions=pending,
            )
    return {"passed": False}, state.update(
        spec_passed=False,
        bead_aborted=True,
        implementer_escalation_level=escalation_level,
        pending_assumptions=pending,
    )


@action(
    reads=[
        "current_bead",
        "current_bead_id",
        "reviewer_escalation_level",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
        "isolated",
        "workspace_path",
    ],
    writes=[
        "approved",
        "review_rounds",
        "needs_human_review",
        "last_review_findings",
        "reviewer_escalation_level",
        "implementer_escalation_level",
        "pending_assumptions",
        "protection_blocks",
    ],
)
async def review(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Per-bead review: correctness + completeness reviewers in parallel.

    Fix-loop up to ``MAX_REVIEW_ROUNDS``. Persists the last cycle's
    findings into ``state["last_review_findings"]`` so the downstream
    ``create_human_bead`` action can include them in the assumption
    bead's description.

    On reviewer transient failures (airframe's ``RuntimeTransientError``
    — 5xx, rate limits, network blips, runtime hangs), the action
    escalates to the next configured tier and retries the same round.
    The escalated tier sticks for the rest of the bead so we don't drop
    back to a reviewer we just learned is unreliable. If every tier has
    been tried and the failure persists, the action sets
    ``needs_human_review=True`` and exits.

    Isolated mode (057): the entire call, including every fix round, is
    scoped to the bead's workspace (FR-032) — delegation only, see
    ``_isolation.agent_step_scope``.
    """
    from maverick.workflows.fly_beads._isolation import agent_step_scope

    async with agent_step_scope(state):
        return await _with_protection_drain(
            await _review_impl(state, squadron=squadron, events=events),
            squadron=squadron,
            events=events,
        )


async def _review_impl(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    bead = state["current_bead"]
    bead_id = state["current_bead_id"]
    pending = list(state.get("pending_assumptions") or ())
    if bead is None:
        return {"approved": False}, state.update(
            approved=False,
            review_rounds=0,
            needs_human_review=True,
            last_review_findings=[],
            pending_assumptions=pending,
        )

    description = bead.get("description", "")
    work_unit_md = description or None

    rounds_with_findings = 0
    escalation_level = int(state.get("reviewer_escalation_level") or 0)
    implementer_level = int(state.get("implementer_escalation_level") or 0)
    for round_n in range(1, MAX_REVIEW_ROUNDS + 1):
        # Run both reviewers in parallel (correctness + completeness),
        # bumping the reviewer tier on transient failures until either
        # a result lands or every tier has been tried.
        results, escalation_level, transient_exhausted = await _review_round_with_escalation(
            squadron=squadron,
            events=events,
            bead_id=bead_id,
            description=description,
            work_unit_md=work_unit_md,
            initial_level=escalation_level,
        )
        if transient_exhausted:
            return {"approved": False}, state.update(
                approved=False,
                review_rounds=rounds_with_findings,
                needs_human_review=True,
                last_review_findings=[
                    f"Reviewer transient failure exhausted escalation: {transient_exhausted}"
                ],
                reviewer_escalation_level=escalation_level,
                implementer_escalation_level=implementer_level,
                pending_assumptions=pending,
            )
        if results is None:
            # Non-transient reviewer failure — already logged inside
            # the helper.
            return {"approved": False}, state.update(
                approved=False,
                review_rounds=rounds_with_findings,
                needs_human_review=True,
                last_review_findings=["Review crashed (non-transient)"],
                reviewer_escalation_level=escalation_level,
                implementer_escalation_level=implementer_level,
                pending_assumptions=pending,
            )

        for p in results:
            pending.extend(_payload_assumptions(p))

        approved = all(_payload_approved(p) for p in results)
        if approved:
            return {"approved": True, "rounds": rounds_with_findings}, state.update(
                approved=True,
                review_rounds=rounds_with_findings,
                last_review_findings=[],
                reviewer_escalation_level=escalation_level,
                implementer_escalation_level=implementer_level,
                pending_assumptions=pending,
            )

        rounds_with_findings += 1
        round_findings = _findings_list(results)
        if round_n >= MAX_REVIEW_ROUNDS:
            await _put_output(
                events,
                "review",
                f"Review rounds exhausted after {round_n}; flagging needs-human-review",
                level="warning",
            )
            return {"approved": False, "rounds": rounds_with_findings}, state.update(
                approved=False,
                review_rounds=rounds_with_findings,
                needs_human_review=True,
                last_review_findings=round_findings,
                reviewer_escalation_level=escalation_level,
                implementer_escalation_level=implementer_level,
                pending_assumptions=pending,
            )

        # Re-prompt the implementer to address review feedback.
        ok, implementer_level, fix_assumptions = await _run_fix(
            squadron=squadron,
            events=events,
            bead_id=bead_id,
            phase="review",
            round_n=round_n,
            failure_message="\n".join(round_findings) or "(no specific findings)",
            initial_level=implementer_level,
        )
        pending.extend(fix_assumptions)
        if not ok:
            return {"approved": False, "rounds": rounds_with_findings}, state.update(
                approved=False,
                review_rounds=rounds_with_findings,
                needs_human_review=True,
                last_review_findings=round_findings,
                reviewer_escalation_level=escalation_level,
                implementer_escalation_level=implementer_level,
                pending_assumptions=pending,
            )

    return {"approved": False, "rounds": rounds_with_findings}, state.update(
        approved=False,
        review_rounds=rounds_with_findings,
        needs_human_review=True,
        last_review_findings=[],
        reviewer_escalation_level=escalation_level,
        implementer_escalation_level=implementer_level,
        pending_assumptions=pending,
    )


def _ladder(squadron: FlySquadron, which: str) -> tuple[str, ...]:
    """The escalation ladder ``squadron`` actually has distinct agents for.

    Sourced from the squadron rather than hardcoded so a rung can never
    name a tier whose binding the squadron wouldn't vary. A squadron with
    no ``tiers:`` config yields ``(DEFAULT_TIER,)`` — escalating to an
    identical binding is a retry in disguise (#135).

    Falls back to the base-binding-only ladder for stub squadrons in
    tests that don't model tiering.
    """
    getter = getattr(squadron, f"{which}_escalation_ladder", None)
    if getter is None:
        return (DEFAULT_TIER,)
    return getter() or (DEFAULT_TIER,)


def _tier_at(ladder: tuple[str, ...], level: int) -> str:
    """Clamp ``level`` onto ``ladder`` and return that rung's tier name."""
    if level <= 0:
        return ladder[0]
    if level >= len(ladder):
        return ladder[-1]
    return ladder[level]


async def _call_implementer_with_escalation(
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    bead_id: str,
    prompt: str,
    op: Literal["implement", "fix"],
    label: str,
    initial_level: int,
) -> tuple[Any | None, int, str]:
    """Run ``coder.implement`` or ``coder.fix`` with tier escalation.

    Returns ``(payload, new_level, exhausted_msg)`` — ``payload`` is
    the returned ``Submit*Payload`` on success or ``None`` on
    non-transient failure or exhausted escalation. ``exhausted_msg``
    is non-empty only when escalation walked the full ladder and
    transients still won.
    """
    from airframe.errors import RuntimeTransientError

    step_name = op
    level = max(0, initial_level)
    ladder = _ladder(squadron, "implementer")
    max_level = len(ladder) - 1
    last_transient = ""
    while True:
        tier_name = _tier_at(ladder, level)
        coder = squadron.coder_for(tier_name)
        await events.put(AgentStarted(step_name=step_name, agent_name=label, provider=""))
        t0 = time.monotonic()
        try:
            with squadron.bead_context(bead_id=bead_id):
                method = coder.implement if op == "implement" else coder.fix
                payload = await method(prompt)
        except RuntimeTransientError as exc:
            last_transient = str(exc)
            await events.put(
                AgentCompleted(
                    step_name=step_name,
                    agent_name=label,
                    duration_seconds=time.monotonic() - t0,
                    success=False,
                    error=last_transient,
                )
            )
            if level >= max_level:
                await _put_output(
                    events,
                    step_name,
                    (
                        f"Implementer transient failure exhausted escalation "
                        f"at tier '{tier_name}': {last_transient}"
                    ),
                    level="error",
                    metadata={"tier": tier_name, "transient": True, "exhausted": True},
                )
                return None, level, last_transient
            next_level = level + 1
            next_tier = _tier_at(ladder, next_level)
            await _put_output(
                events,
                step_name,
                (
                    f"Implementer transient failure on tier '{tier_name}'; "
                    f"escalating to '{next_tier}': {last_transient}"
                ),
                level="warning",
                metadata={
                    "from_tier": tier_name,
                    "to_tier": next_tier,
                    "transient": True,
                },
            )
            level = next_level
            continue
        except Exception as exc:  # noqa: BLE001 — non-transient → caller aborts the bead
            await _put_output(
                events,
                step_name,
                f"Implementer failed: {exc}" if op == "implement" else f"Fix failed: {exc}",
                level="error",
            )
            await events.put(
                AgentCompleted(
                    step_name=step_name,
                    agent_name=label,
                    duration_seconds=time.monotonic() - t0,
                    success=False,
                    error=str(exc),
                )
            )
            return None, level, ""
        await events.put(
            AgentCompleted(
                step_name=step_name,
                agent_name=label,
                duration_seconds=time.monotonic() - t0,
            )
        )
        return payload, level, ""


async def _review_round_with_escalation(
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    bead_id: str,
    description: str,
    work_unit_md: str | None,
    initial_level: int,
) -> tuple[tuple[Any, Any] | None, int, str]:
    """Send the correctness+completeness pair, escalating on transient failure.

    Returns ``(results, new_level, transient_exhausted_msg)`` where:

    * ``results`` is the ``(correctness, completeness)`` payload tuple
      on success, or ``None`` on a non-transient crash.
    * ``new_level`` is the escalation level the caller should persist
      for the rest of the bead.
    * ``transient_exhausted_msg`` is the empty string on success or a
      non-transient crash, and the carried transient-error message
      when every reviewer tier has been exhausted.
    """
    from airframe.errors import RuntimeTransientError

    level = max(0, initial_level)
    last_transient_error = ""
    ladder = _ladder(squadron, "reviewer")
    max_level = len(ladder) - 1
    while True:
        tier_name = _tier_at(ladder, level)
        correctness = squadron.correctness_reviewer_for(tier_name)
        completeness = squadron.completeness_reviewer_for(tier_name)

        with squadron.bead_context(bead_id=bead_id):
            t0 = time.monotonic()
            await events.put(
                AgentStarted(step_name="review", agent_name="Correctness", provider="")
            )
            await events.put(
                AgentStarted(step_name="review", agent_name="Completeness", provider="")
            )
            try:
                results = await asyncio.gather(
                    correctness.review(
                        bead_description=description,
                        work_unit_md=work_unit_md,
                        briefing_context=None,
                    ),
                    completeness.review(
                        bead_description=description,
                        work_unit_md=work_unit_md,
                        briefing_context=None,
                    ),
                )
            except RuntimeTransientError as exc:
                last_transient_error = str(exc)
                duration = time.monotonic() - t0
                await events.put(
                    AgentCompleted(
                        step_name="review",
                        agent_name="Correctness",
                        duration_seconds=duration,
                        success=False,
                        error=last_transient_error,
                    )
                )
                await events.put(
                    AgentCompleted(
                        step_name="review",
                        agent_name="Completeness",
                        duration_seconds=duration,
                        success=False,
                        error=last_transient_error,
                    )
                )
                if level >= max_level:
                    await _put_output(
                        events,
                        "review",
                        (
                            f"Reviewer transient failure exhausted escalation at "
                            f"tier '{tier_name}': {last_transient_error}"
                        ),
                        level="error",
                        metadata={"tier": tier_name, "transient": True, "exhausted": True},
                    )
                    return None, level, last_transient_error
                next_level = level + 1
                next_tier = _tier_at(ladder, next_level)
                await _put_output(
                    events,
                    "review",
                    (
                        f"Reviewer transient failure on tier '{tier_name}'; "
                        f"escalating to '{next_tier}': {last_transient_error}"
                    ),
                    level="warning",
                    metadata={
                        "from_tier": tier_name,
                        "to_tier": next_tier,
                        "transient": True,
                    },
                )
                level = next_level
                continue
            except Exception as exc:  # noqa: BLE001 — non-transient → bail to needs-human-review
                duration = time.monotonic() - t0
                await events.put(
                    AgentCompleted(
                        step_name="review",
                        agent_name="Correctness",
                        duration_seconds=duration,
                        success=False,
                        error=str(exc),
                    )
                )
                await events.put(
                    AgentCompleted(
                        step_name="review",
                        agent_name="Completeness",
                        duration_seconds=duration,
                        success=False,
                        error=str(exc),
                    )
                )
                await _put_output(
                    events,
                    "review",
                    f"Review failed: {exc}",
                    level="error",
                )
                return None, level, ""
            duration = time.monotonic() - t0
        await events.put(
            AgentCompleted(
                step_name="review",
                agent_name="Correctness",
                duration_seconds=duration,
            )
        )
        await events.put(
            AgentCompleted(
                step_name="review",
                agent_name="Completeness",
                duration_seconds=duration,
            )
        )
        return results, level, ""


def _payload_approved(payload: Any) -> bool:
    """A review is approved when ``payload.approved`` is True.

    Prefers the explicit ``approved`` field (current ``SubmitReviewPayload``
    schema); falls back to "no findings" for stubs that don't set it.
    """
    explicit = getattr(payload, "approved", None)
    if explicit is None and isinstance(payload, dict):
        explicit = payload.get("approved")
    if explicit is not None:
        return bool(explicit)
    findings = getattr(payload, "findings", None)
    if findings is None and isinstance(payload, dict):
        findings = payload.get("findings", [])
    return not findings


def _findings_list(payloads: list[Any] | tuple[Any, ...]) -> list[str]:
    """Flatten reviewer findings into ``"<severity>: <issue>"`` lines.

    The current ``ReviewFindingPayload`` schema uses ``issue`` (not the
    legacy ``description``); both are checked for forward/back-compat
    with stubs that still ship the older shape.
    """
    parts: list[str] = []
    for p in payloads:
        findings = getattr(p, "findings", None) or (
            p.get("findings", []) if isinstance(p, dict) else []
        )
        for f in findings:
            severity = getattr(f, "severity", None) or (
                f.get("severity") if isinstance(f, dict) else None
            )
            issue = (
                getattr(f, "issue", None)
                or getattr(f, "description", None)
                or (f.get("issue") if isinstance(f, dict) else None)
                or (f.get("description") if isinstance(f, dict) else None)
            )
            if not issue:
                continue
            parts.append(f"{severity}: {issue}" if severity else issue)
    return parts


@action(
    reads=["current_bead", "current_bead_id", "review_rounds", "last_review_findings"],
    writes=["human_bead_id"],
)
async def create_human_bead(
    state: State,
    *,
    cwd: str,
    epic_id: str,
    flight_plan_name: str,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Create an assumption-review bead on ``bd`` for human triage.

    Runs when ``needs_human_review`` is true (review rounds exhausted
    or a fix request failed). Mirrors the retired xoscar-era
    ``FlySupervisor._create_human_bead``: ``TASK``/``REVIEW``
    bead assigned to ``human`` with labels
    ``["assumption-review", "needs-human-review"]`` and a metadata
    state payload tying it back to the source bead. Failure here is
    non-fatal — we emit a warning and continue to commit so the
    commit's ``Tag: needs-human-review`` trailer still lands.
    """
    from maverick.beads.client import BeadClient
    from maverick.beads.models import BeadCategory, BeadDefinition, BeadType

    bead = state["current_bead"] or {}
    bead_id = state["current_bead_id"]
    bead_title = bead.get("title", bead_id) or bead_id
    findings: list[str] = list(state.get("last_review_findings") or ())
    findings_text = "\n".join(f"- {f}" for f in findings) if findings else "None"
    reason = (
        f"Review rounds exhausted ({state.get('review_rounds', 0)} of "
        f"{MAX_REVIEW_ROUNDS}) without approval."
    )

    review_def = BeadDefinition(
        title=f"Review: {bead_title[:150]}",
        bead_type=BeadType.TASK,
        priority=1,
        category=BeadCategory.REVIEW,
        description=f"## Escalation Reason\n\n{reason}\n\n## Findings\n\n{findings_text}",
        assignee="human",
        labels=["assumption-review", "needs-human-review"],
    )

    client = BeadClient(cwd=Path(cwd))
    try:
        created = await client.create_bead(
            review_def,
            parent_id=epic_id or None,
        )
    except Exception as exc:  # noqa: BLE001 — non-fatal; commit still tags the trailer
        await _put_output(
            events,
            "fly",
            f"Failed to create assumption bead for {bead_id}: {exc}",
            level="warning",
        )
        return {"created": False, "error": str(exc)}, state.update(human_bead_id="")

    try:
        await client.set_state(
            created.bd_id,
            {
                "source_bead": bead_id,
                "escalation_type": "fix_exhaustion",
                "flight_plan": flight_plan_name,
            },
            reason=f"Escalated from {bead_id}",
        )
    except Exception as exc:  # noqa: BLE001 — non-fatal
        await _put_output(
            events,
            "fly",
            f"Failed to set state on assumption bead {created.bd_id}: {exc}",
            level="warning",
        )

    await _put_output(
        events,
        "fly",
        f"Created human review bead {created.bd_id} for {bead_id}",
        level="warning",
        metadata={"human_bead_id": created.bd_id, "source_bead": bead_id},
    )
    return {"created": True, "human_bead_id": created.bd_id}, state.update(
        human_bead_id=created.bd_id
    )


@action(
    reads=["current_bead_id", "pending_assumptions"],
    writes=["recorded_assumption_ids"],
)
async def record_assumptions(
    state: State,
    *,
    cwd: str,
    epic_id: str,
    events: asyncio.Queue[ProgressEvent | None],
    config: MaverickConfig | None = None,
) -> tuple[dict[str, Any], State]:
    """Create ledger entries for assumptions accumulated during this bead.

    Non-fatal — mirrors :func:`create_human_bead`'s warn-and-continue
    pattern (FR-012 / research R4): a ledger write failure never blocks
    commit. Runs between review/create_human_bead and commit so the
    same bead's commit can stamp the entries moments later.

    After recording, hands the newly recorded entries to
    ``assumptions.suggestions.attach_suggestions`` so a matching prior
    resolution can be surfaced later (055-learned-assumption-resolution
    T019, research R5) — also non-fatal, and skipped entirely when
    nothing was recorded or no runway store is initialized. ``config``
    (bound from the workflow's ``MaverickConfig``, same threading as
    ``reconcile_answers``) supplies the optional
    ``assumptions.resolution.auto_resolve_low`` policy so a matching
    resolution can be auto-applied (055 T033).
    """
    from maverick.assumptions.errors import AssumptionLedgerError
    from maverick.assumptions.ledger import record_assumption
    from maverick.assumptions.models import AssumptionRecord, report_entry_from_record
    from maverick.beads.client import BeadClient
    from maverick.payloads import AssumptionPayload
    from maverick.runway.store import resolve_runway_store

    bead_id = state["current_bead_id"]
    pending: list[dict[str, Any]] = list(state.get("pending_assumptions") or ())
    if not pending:
        return {"recorded": 0}, state.update(recorded_assumption_ids=[])

    client = BeadClient(cwd=Path(cwd))
    recorded_ids: list[str] = []
    recorded_records: list[AssumptionRecord] = []
    for raw in pending:
        try:
            payload = AssumptionPayload.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 — malformed accumulated entry, skip
            await _put_output(
                events,
                "fly",
                f"Skipping malformed assumption payload: {exc}",
                level="warning",
            )
            continue
        try:
            record = await record_assumption(
                client, payload=payload, source_bead_id=bead_id, epic_id=epic_id
            )
        except AssumptionLedgerError as exc:
            await _put_output(
                events,
                "fly",
                f"Failed to record assumption for {bead_id}: {exc}",
                level="warning",
            )
            continue
        if record is not None:
            recorded_ids.append(record.bead_id)
            recorded_records.append(record)

    if recorded_ids:
        await _put_output(
            events,
            "fly",
            f"Recorded {len(recorded_ids)} assumption(s) for {bead_id}",
            metadata={"recorded_assumption_ids": recorded_ids},
        )

        store = resolve_runway_store(cwd)
        if store is not None:
            # No bd re-read here: `record_assumption` already returned the
            # full `AssumptionRecord` for each entry, and that carries
            # everything suggestion matching reads (bead_id, question,
            # adopted_answer, severity, owner_spec). The remaining
            # `AssumptionReportEntry` fields are answer/waiver/reconcile
            # state a just-created entry cannot have yet, which is exactly
            # what `report_entry_from_record` fills in.
            entries = [report_entry_from_record(record) for record in recorded_records]

            if entries:
                resolution_config = config.assumptions.resolution if config else None
                auto_resolve = resolution_config.auto_resolve_low if resolution_config else None
                try:
                    await attach_suggestions(
                        client,
                        store,
                        entries,
                        auto_resolve=auto_resolve,
                    )
                except Exception as exc:  # noqa: BLE001 — non-fatal (research R5)
                    await _put_output(
                        events,
                        "fly",
                        f"Failed to attach suggestions for {bead_id}: {exc}",
                        level="warning",
                    )

    return {"recorded": len(recorded_ids)}, state.update(recorded_assumption_ids=recorded_ids)


@action(
    reads=[
        "current_bead",
        "current_bead_id",
        "approved",
        "needs_human_review",
        "review_rounds",
        "recorded_assumption_ids",
    ],
    writes=["commit_ok", "commit_change_id"],
)
async def commit(
    state: State,
    *,
    cwd: str,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Commit the bead's changes, mark it complete, and stamp any ledger entries."""
    from maverick.library.actions.beads import mark_bead_complete
    from maverick.library.actions.jj import jj_commit_bead
    from maverick.workspace import CheckoutPath

    bead = state["current_bead"]
    if bead is None:
        return {"committed": False}, state.update(commit_ok=False)

    bead_id = state["current_bead_id"]
    title = bead.get("title", "")
    tag = "needs-human-review" if state.get("needs_human_review") else ""
    message_parts = [f"bead({bead_id}): {title}"]
    if tag:
        message_parts.append(f"\nTag: {tag}")
    message_parts.append(f"\nBead: {bead_id}")
    message = "\n".join(message_parts)

    try:
        commit_result = await jj_commit_bead(message, cwd=CheckoutPath(Path(cwd)))
    except Exception as exc:  # noqa: BLE001
        await _put_output(events, "commit", f"Commit failed: {exc}", level="error")
        return {"committed": False, "error": str(exc)}, state.update(commit_ok=False)

    change_id = commit_result.get("change_id") or ""

    try:
        await mark_bead_complete(bead_id, cwd=CheckoutPath(Path(cwd)))
    except Exception as exc:  # noqa: BLE001
        await _put_output(
            events,
            "commit",
            f"mark_bead_complete failed: {exc}",
            level="warning",
        )

    recorded_ids = list(state.get("recorded_assumption_ids") or ())
    if recorded_ids and change_id:
        from maverick.assumptions.ledger import stamp_change_id
        from maverick.beads.client import BeadClient

        stamp_result = await stamp_change_id(
            BeadClient(cwd=Path(cwd)), entry_ids=recorded_ids, change_id=change_id
        )
        if stamp_result.failed:
            await _put_output(
                events,
                "commit",
                f"Failed to stamp {len(stamp_result.failed)} assumption entry(s): "
                f"{stamp_result.failed}",
                level="warning",
            )

    await _put_output(events, "commit", f"Committed bead {bead_id}", level="success")
    return {"committed": True}, state.update(commit_ok=True, commit_change_id=change_id)


@action(reads=["current_bead_id"], writes=["bead_aborted", "bead_failed"])
async def abandon_bead(
    state: State,
    *,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Mark a bead as failed without committing.

    Reached when implement/gate/ac/spec failed irrecoverably. The
    record_outcome action that follows accounts the bead as failed.
    """
    bead_id = state["current_bead_id"]
    await _put_output(
        events,
        "fly",
        f"Bead {bead_id} abandoned (validation exhausted)",
        level="error",
    )
    return {"abandoned": True}, state.update(bead_aborted=True, bead_failed=True)


@action(
    reads=[
        "current_bead",
        "current_bead_id",
        "commit_ok",
        "bead_failed",
        "bead_aborted",
        "needs_human_review",
        "review_rounds",
        "completed_bead_ids",
        "bead_events",
        "processed_count",
        "succeeded_count",
        "failed_count",
        "isolated",
        "workspace_path",
        "isolation_halt_reason",
    ],
    writes=[
        "completed_bead_ids",
        "bead_events",
        "processed_count",
        "succeeded_count",
        "failed_count",
        "workspace_path",
    ],
)
async def record_outcome(
    state: State,
    *,
    isolation_policy: Any = None,
    checkout: CheckoutPath | None = None,
    jj_client: Any = None,
    squadron: Any = None,
) -> tuple[dict[str, Any], State]:
    """Append a per-bead summary and advance counters before the loop cycles.

    Isolated mode (057): also the universal per-bead boundary for tearing
    down (or retaining) this bead's workspace — every path (commit or
    abandonment) funnels through here exactly once, before
    ``reconcile_answers`` (contract C7). Delegation only, see
    ``_isolation.teardown_workspace``.
    """
    if state.get("isolated"):
        from maverick.workflows.fly_beads._isolation import teardown_workspace

        assert checkout is not None, "record_outcome(isolated=True) requires checkout"
        _, state = await teardown_workspace(
            state,
            checkout=checkout,
            policy=isolation_policy,
            jj_client=jj_client,
            squadron=squadron,
        )

    bead = state["current_bead"] or {}
    bead_id = state["current_bead_id"]
    succeeded = bool(state.get("commit_ok")) and not state.get("bead_failed")

    completed = list(state["completed_bead_ids"])
    if succeeded and bead_id not in completed:
        completed.append(bead_id)

    events_acc = list(state["bead_events"])
    event_entry: dict[str, Any] = {
        "bead_id": bead_id,
        "title": bead.get("title", ""),
        "success": succeeded,
        "review_rounds": state.get("review_rounds", 0),
    }
    if state.get("needs_human_review"):
        event_entry["tag"] = "needs-human-review"
    events_acc.append(event_entry)

    return {"recorded": True}, state.update(
        completed_bead_ids=completed,
        bead_events=events_acc,
        processed_count=state["processed_count"] + 1,
        succeeded_count=state["succeeded_count"] + (1 if succeeded else 0),
        failed_count=state["failed_count"] + (0 if succeeded else 1),
    )


# ---------------------------------------------------------------------------
# Mid-flight reconcile (052-conditional-landing, User Story 3)
# ---------------------------------------------------------------------------


async def _run_reconcile_answers(
    state: State,
    *,
    cwd: str,
    config: MaverickConfig | None,
    fly_run_id: str,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Shared body for both mid-flight reconcile action nodes.

    Thin delegation only — every precondition check, detection query, and
    the ``ReconcileWorkflow`` invocation itself live in
    :func:`maverick.workflows.fly_beads.mid_flight.run_mid_flight_pass`.
    Never raises: the mid-flight contract requires the pass to never
    interrupt the Burr drain loop (FR-013), and ``run_mid_flight_pass``
    already catches everything it can fail on.
    """
    from maverick.workflows.fly_beads.mid_flight import run_mid_flight_pass

    outcome = await run_mid_flight_pass(
        cwd=Path(cwd),
        config=config,
        fly_run_id=fly_run_id,
        event_sink=events,
    )
    return {
        "detected": outcome.detected,
        "processed": outcome.processed,
        "escalated": outcome.escalated,
        "skipped_reason": outcome.skipped_reason,
        "error": outcome.error,
    }, state


@action(reads=[], writes=[])
async def reconcile_answers(
    state: State,
    *,
    cwd: str,
    config: MaverickConfig | None,
    fly_run_id: str,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Bead-boundary mid-flight reconcile pass.

    Spliced onto ``record_outcome -> reconcile_answers -> select_next_bead``
    (contract: covers both the commit success path and the abandon path,
    since ``abandon_bead`` already funnels through ``record_outcome``
    before reaching this action — see ``burr_graph.py``'s module
    docstring). A pass never blocks bead selection: it either finds
    nothing to do, reconciles in-process, or fails safely — either way
    the graph proceeds to ``select_next_bead`` immediately after.
    """
    return await _run_reconcile_answers(
        state, cwd=cwd, config=config, fly_run_id=fly_run_id, events=events
    )


@action(reads=[], writes=[])
async def reconcile_answers_final(
    state: State,
    *,
    cwd: str,
    config: MaverickConfig | None,
    fly_run_id: str,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Loop-exit mid-flight reconcile pass.

    Spliced onto ``select_next_bead -> reconcile_answers_final ->
    aggregate_review`` (only on the ``loop_done`` branch) so an answer
    that arrived during the last bead is still processed before the run
    is declared complete (FR-009). Identical body to
    :func:`reconcile_answers` — kept as a distinct action so it occupies
    its own graph node (and progress-label slot) rather than reusing a
    state flag to distinguish the two call sites.
    """
    return await _run_reconcile_answers(
        state, cwd=cwd, config=config, fly_run_id=fly_run_id, events=events
    )


# ---------------------------------------------------------------------------
# Aggregate (cross-bead) review
# ---------------------------------------------------------------------------


@action(
    reads=["completed_bead_ids", "bead_events", "succeeded_count", "protection_blocks"],
    writes=["aggregate_review_payload", "protection_blocks"],
)
async def aggregate_review(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
    epic_id: str,
    fly_run_id: str = "",
) -> tuple[dict[str, Any], State]:
    """Run the epic-level cross-bead review after the bead loop ends.

    Mirrors the retired xoscar-era ``FlySupervisor._maybe_aggregate_review``:
    gated on ``AGGREGATE_REVIEW_THRESHOLD`` successful beads, this asks
    the correctness reviewer to look across the entire epic for
    cross-bead consistency issues. The findings surface as a single
    warning row when the aggregate review is not approved; they don't
    block the run.

    Also the fly graph's natural loop-exit point (the last action before
    ``done``) — after draining any final protection blocks, emits one
    end-of-run ``StepOutput(level="warning", metadata={"block_count": n})``
    summarizing the whole run's context-file-protection activity
    (056-context-file-protection); a clean run emits nothing (FR-006).
    ``fly_run_id`` is only used to name the artifact path in that warning
    — the workflow, not this action, writes it.
    """
    result, new_state = await _with_protection_drain(
        await _aggregate_review_impl(
            state, squadron=squadron, events=events, cwd=cwd, epic_id=epic_id
        ),
        squadron=squadron,
        events=events,
    )
    block_count = len(new_state.get("protection_blocks") or ())
    if block_count > 0:
        artifact = (
            f".maverick/runs/{fly_run_id}/protection-blocks.json"
            if fly_run_id
            else "protection-blocks.json"
        )
        await events.put(
            StepOutput(
                step_name="aggregate_review",
                message=(
                    f"{block_count} context-file protection event(s) this run — see {artifact}"
                ),
                display_label="",
                level="warning",
                source=_SOURCE,
                metadata={"block_count": block_count},
            )
        )
    return result, new_state


async def _aggregate_review_impl(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
    epic_id: str,
) -> tuple[dict[str, Any], State]:
    completed_ids: list[str] = list(state.get("completed_bead_ids") or ())
    if len(completed_ids) < AGGREGATE_REVIEW_THRESHOLD:
        return {"ran": False, "reason": "below_threshold"}, state.update(
            aggregate_review_payload=None,
        )

    # Build "<id>: <title>" lines from the per-bead event ledger so the
    # prompt intentionally omits titles (they are not on the
    # completed_bead_ids list itself).
    bead_events: list[dict[str, Any]] = list(state.get("bead_events") or ())
    title_by_id: dict[str, str] = {e["bead_id"]: e.get("title", "") for e in bead_events}
    bead_list = "\n".join(f"- {bid}: {title_by_id.get(bid, '')}" for bid in completed_ids)

    diff_stat = await _safe_diff_stat(cwd)

    reviewer = squadron.correctness_reviewer_for(DEFAULT_TIER)
    label = "Aggregate review"
    await events.put(AgentStarted(step_name="aggregate_review", agent_name=label, provider=""))
    t0 = time.monotonic()
    try:
        payload = await reviewer.aggregate(
            objective=epic_id or "epic",
            bead_list=bead_list,
            diff_stat=diff_stat,
        )
    except Exception as exc:  # noqa: BLE001 — non-fatal advisory step
        await _put_output(
            events,
            "fly",
            f"Aggregate review failed: {exc}",
            level="warning",
        )
        await events.put(
            AgentCompleted(
                step_name="aggregate_review",
                agent_name=label,
                duration_seconds=time.monotonic() - t0,
                success=False,
                error=str(exc),
            )
        )
        return {"ran": False, "error": str(exc)}, state.update(
            aggregate_review_payload=None,
        )

    await events.put(
        AgentCompleted(
            step_name="aggregate_review",
            agent_name=label,
            duration_seconds=time.monotonic() - t0,
        )
    )

    summary = dump_supervisor_payload(payload)
    if not payload.approved:
        finding_count = len(payload.findings)
        await _put_output(
            events,
            "fly",
            f"Aggregate review flagged {finding_count} cross-bead issue(s)",
            level="warning",
            metadata={"finding_count": finding_count},
        )

    return {"ran": True, "approved": payload.approved}, state.update(
        aggregate_review_payload=summary,
    )


async def _safe_diff_stat(cwd: str) -> str:
    """Return ``git diff --stat HEAD~1..HEAD`` or empty on any failure."""
    from maverick.runners.command import CommandRunner

    try:
        runner = CommandRunner(cwd=Path(cwd))
        result = await runner.run(["git", "diff", "--stat", "HEAD~1..HEAD"])
        return result.stdout if result.returncode == 0 else ""
    except Exception:  # noqa: BLE001 — advisory; empty diff stat is fine
        return ""
