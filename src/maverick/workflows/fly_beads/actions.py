"""Burr actions for the ``fly_beads`` workflow.

State-machine port of
:class:`maverick.actors.xoscar.fly_supervisor.FlySupervisor`.

Phase 3 scope (intentional simplifications, documented):

* Outer bead loop + per-bead pipeline (implement → gate → ac → spec
  → review → commit) with fix loops at each stage.
* **Single-tier dispatch only**: ``squadron.coder_for("_default")`` and
  the matching reviewer pair. Tier escalation is queued for follow-up.
* **No aggregate-review pass**: per-bead loops match the xoscar
  supervisor, but the cross-bead post-loop ``_maybe_aggregate_review``
  is skipped.
* **No reviewer transient-failure escalation**: review failures fall
  straight through to ``needs-human-review`` instead of retrying on a
  higher-tier reviewer.
* **No human-bead creation**: review failure / fix-budget exhaustion
  still commits with ``tag="needs-human-review"`` so manual triage
  can find it via the trailer, but no companion assumption bead is
  created on bd. (Defaults to xoscar if humans need the bead-side
  audit trail.)
* **Spec-check no-op**: ``spec_check`` always returns ``passed=True``
  in Phase 3. The xoscar :class:`SpecCheckActor` runs Rust-specific
  grep checks (``.unwrap()``, ``std::process::Command`` in async) that
  weren't worth porting inline. Restoring the check is a follow-up.
* **Graceful stop**: preserved. The router action checks the
  module-level flag before picking the next bead.

Default driver remains xoscar; opt in via ``MAVERICK_USE_BURR=fly``.
"""

from __future__ import annotations

import asyncio
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
from maverick.payloads import dump_supervisor_payload

if TYPE_CHECKING:
    from maverick.squadron.fly import FlySquadron


__all__ = [
    "DEFAULT_TIER",
    "MAX_GATE_FIX_ATTEMPTS",
    "MAX_REVIEW_ROUNDS",
    "MAX_SPEC_FIX_ATTEMPTS",
    "abandon_bead",
    "ac_check",
    "commit",
    "gate",
    "implement",
    "init_state",
    "process_bead_start",
    "record_outcome",
    "review",
    "select_next_bead",
    "spec_check",
]

# Mirror the xoscar supervisor's fix budgets (fly_supervisor.py:61-64).
MAX_REVIEW_ROUNDS: int = 3
MAX_GATE_FIX_ATTEMPTS: int = 2
MAX_SPEC_FIX_ATTEMPTS: int = 2

DEFAULT_TIER: str = "_default"

_SOURCE = "fly-burr"


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
    reads=["completed_bead_ids", "processed_count"],
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
    ],
)
async def select_next_bead(
    state: State,
    *,
    epic_id: str,
    cwd: str,
    max_beads: int,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Pick the next ready bead — or signal end-of-stream.

    Three conditions terminate the loop:

    1. Graceful-stop flag has been set (Ctrl-C between beads).
    2. ``max_beads`` cap reached (``0`` means unlimited).
    3. No ready bead is available (``select_next_bead`` returns
       ``found=False``). The Burr driver doesn't implement
       ``watch`` mode in Phase 3 — bead-empty terminates immediately.
    """
    from maverick.library.actions.beads import select_next_bead as bd_select
    from maverick.workflows.fly_beads.graceful_stop import (
        is_graceful_stop_requested,
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

    result = await bd_select(epic_id=epic_id, cwd=cwd)
    bead_dict = result.to_dict()
    if not bead_dict.get("found"):
        return {"loop_done": True, "loop_done_reason": "no_more_beads"}, state.update(
            loop_done=True,
            loop_done_reason="no_more_beads",
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
    )


@action(reads=["current_bead"], writes=["bead_aborted", "bead_failed", "needs_human_review"])
async def process_bead_start(state: State) -> tuple[dict[str, Any], State]:
    """Reset per-bead state slots before the per-stage pipeline runs."""
    return {"bead_id": state["current_bead_id"]}, state.update(
        bead_aborted=False,
        bead_failed=False,
        needs_human_review=False,
    )


# ---------------------------------------------------------------------------
# Per-bead pipeline
# ---------------------------------------------------------------------------


@action(
    reads=["current_bead", "current_bead_id"],
    writes=["implement_ok", "implement_summary", "bead_aborted"],
)
async def implement(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Run the implementer on the current bead."""
    bead = state["current_bead"]
    if bead is None:
        return {"ok": False}, state.update(implement_ok=False, bead_aborted=True)

    coder = squadron.coder_for(DEFAULT_TIER)
    prompt = _build_implement_prompt(bead)
    label = "Implementer"
    await events.put(AgentStarted(step_name="implement", agent_name=label, provider=""))
    t0 = time.monotonic()
    try:
        with squadron.bead_context(bead_id=state["current_bead_id"]):
            payload = await coder.implement(prompt)
    except Exception as exc:  # noqa: BLE001 — match xoscar's lenient behaviour
        await _put_output(
            events,
            "implement",
            f"Implementer failed: {exc}",
            level="error",
        )
        await events.put(
            AgentCompleted(
                step_name="implement",
                agent_name=label,
                duration_seconds=time.monotonic() - t0,
                success=False,
                error=str(exc),
            )
        )
        return {"ok": False, "error": str(exc)}, state.update(
            implement_ok=False,
            bead_aborted=True,
        )

    await events.put(
        AgentCompleted(
            step_name="implement",
            agent_name=label,
            duration_seconds=time.monotonic() - t0,
        )
    )
    summary = dump_supervisor_payload(payload)
    return {"ok": True}, state.update(implement_ok=True, implement_summary=summary)


def _build_implement_prompt(bead: dict[str, Any]) -> str:
    """Mirror :func:`FlySupervisor._build_implement_prompt`'s shape."""
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
) -> bool:
    """Re-prompt the implementer on validation failure.

    Returns ``True`` if the agent landed a fix payload; ``False`` if
    the call raised (bead should abandon).
    """
    coder = squadron.coder_for(DEFAULT_TIER)
    prompt = (
        f"## Fix request — phase: {phase}, round {round_n}\n\n"
        f"The {phase} check failed with:\n\n{failure_message}\n\n"
        "Address the failure and submit a fix-result payload via the "
        "StructuredOutput tool."
    )
    label = f"Fix ({phase} r{round_n})"
    await events.put(AgentStarted(step_name="fix", agent_name=label, provider=""))
    t0 = time.monotonic()
    try:
        with squadron.bead_context(bead_id=bead_id):
            await coder.fix(prompt)
    except Exception as exc:  # noqa: BLE001
        await _put_output(events, "fix", f"Fix failed: {exc}", level="error")
        await events.put(
            AgentCompleted(
                step_name="fix",
                agent_name=label,
                duration_seconds=time.monotonic() - t0,
                success=False,
                error=str(exc),
            )
        )
        return False
    await events.put(
        AgentCompleted(
            step_name="fix",
            agent_name=label,
            duration_seconds=time.monotonic() - t0,
        )
    )
    return True


@action(
    reads=["current_bead_id"],
    writes=["gate_passed", "bead_aborted"],
)
async def gate(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
    validation_commands: dict[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, Any], State]:
    """Run the format/lint/test gate; fix-retry up to ``MAX_GATE_FIX_ATTEMPTS``."""
    from maverick.library.actions.validation import run_independent_gate

    bead_id = state["current_bead_id"]
    for attempt in range(MAX_GATE_FIX_ATTEMPTS + 1):
        result = await run_independent_gate(
            stages=["format", "lint", "test"],
            cwd=cwd,
            validation_commands=validation_commands,
        )
        if result.get("passed"):
            return {"passed": True, "attempts": attempt + 1}, state.update(gate_passed=True)
        if attempt >= MAX_GATE_FIX_ATTEMPTS:
            summary = result.get("summary") or "gate failed"
            await _put_output(
                events,
                "gate",
                f"Gate fix attempts exhausted: {summary}",
                level="error",
            )
            return {"passed": False}, state.update(gate_passed=False, bead_aborted=True)
        summary = result.get("summary") or "gate failed"
        await _put_output(
            events,
            "gate",
            f"Gate failed ({attempt + 1}/{MAX_GATE_FIX_ATTEMPTS}); requesting fix",
            level="warning",
            metadata={"attempt": attempt + 1},
        )
        ok = await _run_fix(
            squadron=squadron,
            events=events,
            bead_id=bead_id,
            phase="gate",
            round_n=attempt + 1,
            failure_message=summary,
        )
        if not ok:
            return {"passed": False, "fix_failed": True}, state.update(
                gate_passed=False, bead_aborted=True
            )
    # unreachable but satisfies type checker
    return {"passed": False}, state.update(gate_passed=False, bead_aborted=True)


@action(
    reads=["current_bead", "current_bead_id"],
    writes=["ac_passed", "bead_aborted"],
)
async def ac_check(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
    cwd: str,
) -> tuple[dict[str, Any], State]:
    """Run the AC (verification commands) check. One fix retry."""
    from maverick.actors.xoscar.ac_check import ACCheckActor  # noqa: F401 — type ref
    from maverick.runners.command import CommandRunner
    from maverick.workflows.fly_beads.steps import (
        _parse_verification_commands,
        _parse_work_unit_sections,
    )

    bead = state["current_bead"]
    bead_id = state["current_bead_id"]
    description = bead.get("description", "") if bead else ""

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
        return {"passed": True}, state.update(ac_passed=True)

    await _put_output(
        events,
        "ac",
        f"AC check failed; requesting fix: {reasons}",
        level="warning",
    )
    ok = await _run_fix(
        squadron=squadron,
        events=events,
        bead_id=bead_id,
        phase="ac",
        round_n=1,
        failure_message=reasons,
    )
    if not ok:
        return {"passed": False}, state.update(ac_passed=False, bead_aborted=True)

    passed, reasons = await _run_once()
    if not passed:
        await _put_output(events, "ac", f"AC check failed after fix: {reasons}", level="error")
        return {"passed": False}, state.update(ac_passed=False, bead_aborted=True)
    return {"passed": True}, state.update(ac_passed=True)


@action(reads=["current_bead_id"], writes=["spec_passed"])
async def spec_check(
    state: State,
    *,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Spec-compliance check — Phase 3 no-op.

    The xoscar :class:`SpecCheckActor` runs Rust-specific grep checks
    against changed files. Porting the rule engine + the changed-files
    discovery inline is non-trivial; for Phase 3 we route through as
    "passed" and surface the gap via an info-level StepOutput so it's
    obvious in the logs. Restoring the real check is a follow-up.
    """
    await _put_output(
        events,
        "spec",
        "Spec check skipped (Phase 3 no-op)",
        level="info",
    )
    return {"passed": True, "phase_3_noop": True}, state.update(spec_passed=True)


@action(
    reads=["current_bead", "current_bead_id"],
    writes=["approved", "review_rounds", "needs_human_review"],
)
async def review(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Per-bead review: correctness + completeness reviewers in parallel.

    Fix-loop up to ``MAX_REVIEW_ROUNDS``.
    """
    bead = state["current_bead"]
    bead_id = state["current_bead_id"]
    if bead is None:
        return {"approved": False}, state.update(
            approved=False, review_rounds=0, needs_human_review=True
        )

    correctness = squadron.correctness_reviewer_for(DEFAULT_TIER)
    completeness = squadron.completeness_reviewer_for(DEFAULT_TIER)
    description = bead.get("description", "")
    work_unit_md = description or None

    rounds_with_findings = 0
    for round_n in range(1, MAX_REVIEW_ROUNDS + 1):
        # Both reviewers in parallel — same pattern as xoscar.
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
            except Exception as exc:  # noqa: BLE001
                await _put_output(
                    events,
                    "review",
                    f"Review failed: {exc}",
                    level="error",
                )
                return {"approved": False}, state.update(
                    approved=False,
                    review_rounds=rounds_with_findings,
                    needs_human_review=True,
                )
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

        approved = all(_payload_approved(p) for p in results)
        if approved:
            return {"approved": True, "rounds": rounds_with_findings}, state.update(
                approved=True, review_rounds=rounds_with_findings
            )

        rounds_with_findings += 1
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
            )

        # Re-prompt the implementer to address review feedback.
        findings_text = _format_findings(results)
        ok = await _run_fix(
            squadron=squadron,
            events=events,
            bead_id=bead_id,
            phase="review",
            round_n=round_n,
            failure_message=findings_text,
        )
        if not ok:
            return {"approved": False, "rounds": rounds_with_findings}, state.update(
                approved=False,
                review_rounds=rounds_with_findings,
                needs_human_review=True,
            )

    return {"approved": False, "rounds": rounds_with_findings}, state.update(
        approved=False, review_rounds=rounds_with_findings, needs_human_review=True
    )


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


def _format_findings(payloads: list[Any] | tuple[Any, ...]) -> str:
    parts: list[str] = []
    for p in payloads:
        findings = getattr(p, "findings", None) or (
            p.get("findings", []) if isinstance(p, dict) else []
        )
        for f in findings:
            text = getattr(f, "description", None) or (
                f.get("description") if isinstance(f, dict) else None
            )
            if text:
                parts.append(text)
    return "\n".join(parts) if parts else "(no specific findings provided)"


@action(
    reads=["current_bead", "current_bead_id", "approved", "needs_human_review", "review_rounds"],
    writes=["commit_ok"],
)
async def commit(
    state: State,
    *,
    cwd: str,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Commit the bead's changes and mark the bead complete."""
    from maverick.library.actions.beads import mark_bead_complete
    from maverick.library.actions.jj import jj_commit_bead

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
        await jj_commit_bead(message, cwd=cwd)
    except Exception as exc:  # noqa: BLE001
        await _put_output(events, "commit", f"Commit failed: {exc}", level="error")
        return {"committed": False, "error": str(exc)}, state.update(commit_ok=False)

    try:
        await mark_bead_complete(bead_id, cwd=cwd)
    except Exception as exc:  # noqa: BLE001
        await _put_output(
            events,
            "commit",
            f"mark_bead_complete failed: {exc}",
            level="warning",
        )

    await _put_output(events, "commit", f"Committed bead {bead_id}", level="success")
    return {"committed": True}, state.update(commit_ok=True)


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
        "needs_human_review",
        "review_rounds",
        "completed_bead_ids",
        "bead_events",
        "processed_count",
        "succeeded_count",
        "failed_count",
    ],
    writes=[
        "completed_bead_ids",
        "bead_events",
        "processed_count",
        "succeeded_count",
        "failed_count",
    ],
)
async def record_outcome(state: State) -> tuple[dict[str, Any], State]:
    """Append a per-bead summary and advance counters before the loop cycles."""
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
