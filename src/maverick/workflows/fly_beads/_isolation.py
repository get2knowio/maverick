"""Per-bead isolation-lease handling and fold-back/undo action bodies for
`maverick fly --isolated` (057-isolated-bead-workspaces, User Story 3).

Deliberately **not** in `actions.py`: that module is 1,887 lines, past
Principle XI's 1,000-line hard stop, which forbids adding features to it
without first carving out a submodule — this is that carve-out. Every
change this feature makes to `actions.py` is delegation only.

Burr's actions are independently-invoked async functions with no shared
lexical scope spanning a bead's provision -> fold-back -> commit sequence,
so this module drives the primitive's lower-level lifecycle/foldback calls
directly (`lifecycle.provision`/`teardown`/`retain`,
`session.register_unit`/`release_unit`) rather than
`IsolationSession.lease()`'s `async with`-scoped convenience wrapper, which
assumes a single Python scope. Registration goes through the *session*
rather than the free `register_live_workspace`/`unregister_live_workspace`
pair precisely because there is no `finally` here to guarantee the second
call ever runs: the session's `__aexit__` is the backstop that cleans up a
unit whose run halted mid-bead. `session.fold_back()`/`session.undo()` still
handle the fold-back/undo mechanics themselves — each just needs a
freshly-reconstructed `IsolationLease` per call (cheap, since it's a plain
dataclass), rebuilt from the `workspace_path`/`current_bead_id` state slots
each new action call carries.

The lock (contract C1) and stale-journal refusal (contract C2) are
session-level, not per-bead — held for the whole isolated run via
`async with session:` around the entire bead loop in `workflow.py`, exactly
once, not by this module.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from burr.core import State, action

from maverick.exceptions import IsolationProvisioningError, IsolationUndoFailedError
from maverick.workflows.fly_beads.actions import (
    MAX_GATE_FIX_ATTEMPTS,
    _put_output,
    _run_fix,
    _with_protection_drain,
)
from maverick.workspace import (
    CheckoutPath,
    FoldBackOutcome,
    FoldBackResult,
    IsolationLease,
    IsolationPolicy,
    IsolationSession,
    UnitOfWork,
)
from maverick.workspace import lifecycle as workspace_lifecycle
from maverick.workspace.cwd_scope import chdir_scope

if TYPE_CHECKING:
    import asyncio

    from maverick.events import ProgressEvent
    from maverick.squadron.fly import FlySquadron

__all__ = [
    "agent_step_scope",
    "build_isolation_policy",
    "effective_check_cwd",
    "fold_back",
    "gate_fix",
    "provision_workspace",
    "teardown_workspace",
    "undo_fold_back",
]

#: Path segment naming fly's workspaces (research.md R7's `<workflow>`
#: segment) — `~/.maverick/workspaces/<project>/fly/<bead-id>/`.
FLY_WORKFLOW_NAME = "fly"


def build_isolation_policy(
    *, root: Path, fold_exclusions: tuple[str, ...] = ()
) -> IsolationPolicy:
    """The fly-flavored `IsolationPolicy` (research.md R7's table): one
    workspace per bead, never reused, never retained on failure — the
    bead is simply retried from the checkout on the next `maverick fly`
    invocation, unlike the spec chain's `reuse=True`/`retain_on_failure=True`.

    Args:
        root: `workspace.root` from config (`~/.maverick/workspaces` by
            default).
        fold_exclusions: Additional exclusions beyond the primitive's
            always-applied `~.maverick` — the protected set (T076,
            research.md R11's second layer).
    """
    return IsolationPolicy(
        workflow=FLY_WORKFLOW_NAME,
        root=root,
        reuse=False,
        retain_on_failure=False,
        fold_scope=(),
        fold_exclusions=fold_exclusions,
    )


def agent_step_scope(state: State) -> contextlib.AbstractAsyncContextManager[None]:
    """The context manager an agent-calling action wraps its body in.

    Chdirs into the bead's workspace when isolated (FR-032 — every agent
    step, including fix rounds, stays in the workspace); a no-op otherwise,
    so non-isolated behavior is byte-identical (FR-035).
    """
    if state.get("isolated") and state.get("workspace_path"):
        return chdir_scope(state["workspace_path"])
    return contextlib.nullcontext()


def effective_check_cwd(state: State, cwd: str) -> str:
    """The cwd an artifact-level check (`ac_check`/`spec_check`) should
    use: the bead's workspace when isolated, the checkout otherwise
    (research.md R6 — these checks read produced files and the
    working-copy diff, needing no toolchain, so they run in the
    workspace; `gate` is the opposite case and stays on the checkout,
    T074)."""
    if state.get("isolated") and state.get("workspace_path"):
        return state["workspace_path"]
    return cwd


def _unit_for(state: State) -> UnitOfWork:
    bead_id = state["current_bead_id"]
    return UnitOfWork(key=bead_id, label=bead_id)


def _reconstruct_lease(state: State, checkout: CheckoutPath, now: Any) -> IsolationLease:
    """Rebuild the `IsolationLease` a `fold_back`/`undo_fold_back` call
    needs from state alone — cheap (a plain dataclass), and the only way
    to bridge Burr's per-action calls back to the primitive's lease shape
    (see module docstring)."""
    workspace_path = Path(state["workspace_path"])
    return IsolationLease(
        unit=_unit_for(state),
        workspace_path=workspace_path,
        workspace_name=workspace_path.name,
        checkout=checkout,
        created_at=now(),
    )


def _fold_back_result_from_dict(data: dict[str, Any]) -> FoldBackResult:
    return FoldBackResult(
        outcome=FoldBackOutcome(data["outcome"]),
        applied_paths=tuple(data["applied_paths"]),
        conflicting_paths=tuple(data["conflicting_paths"]),
        restore_operation_id=data["restore_operation_id"],
        diagnostic=data["diagnostic"],
        duration_seconds=data["duration_seconds"],
    )


@action(
    reads=["current_bead_id", "isolated"],
    writes=["workspace_path", "bead_aborted"],
)
async def provision_workspace(
    state: State,
    *,
    session: IsolationSession,
    policy: IsolationPolicy,
    checkout: CheckoutPath,
    jj_client: Any,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Provision this bead's workspace (contract C3) and re-root the
    squadron's context-file protection at it (T075, research.md R11).

    A no-op — `workspace_path` stays `""` — when not isolated, so this
    action is always in the graph but only ever does real work on the
    isolated path (kept out of the non-isolated transition list entirely,
    see `burr_graph.py`, but written defensively regardless).

    A provisioning failure (`IsolationProvisioningError` — the workspace
    couldn't be created, not that the bead's work failed) abandons exactly
    this bead rather than propagating: an uncaught exception here would be
    deferred and re-raised by the Burr driver, halting the entire run for
    an environment-level hiccup (a stale jj registration, a full disk) that
    the checkout itself is untouched by — unlike a fold-back conflict or an
    undo failure, nothing has been written anywhere yet, so there is
    nothing to undo and no reason a single bad bead should stop the queue.
    """
    if not state.get("isolated"):
        return {"skipped": True}, state

    unit = _unit_for(state)
    try:
        workspace_path = await workspace_lifecycle.provision(
            checkout=checkout, policy=policy, unit=unit, jj_client=jj_client
        )
    except IsolationProvisioningError as exc:
        await _put_output(
            events,
            "provision_workspace",
            f"Could not isolate bead {unit.key}: {exc}",
            level="error",
        )
        return {"provisioned": False, "error": str(exc)}, state.update(bead_aborted=True)

    # Session-scoped, not the free `register_live_workspace`: this action
    # and `teardown_workspace` are independently-invoked Burr actions with
    # no `finally` bridging them, so if the run halts in between, the
    # session's own `__aexit__` is what unregisters and tears this down.
    session.register_unit(unit, workspace_path)
    await squadron.retarget_protection_for_isolation(workspace_path)
    return {"workspace_path": str(workspace_path)}, state.update(
        workspace_path=str(workspace_path)
    )


@action(
    reads=["current_bead_id", "workspace_path", "isolated"],
    writes=["fold_back_result", "unverified_in_checkout", "bead_aborted", "gate_failure_summary"],
)
async def fold_back(
    state: State,
    *,
    session: IsolationSession,
    checkout: CheckoutPath,
    now: Any,
    events: asyncio.Queue[ProgressEvent | None],
    protection_policy: Any = None,
) -> tuple[dict[str, Any], State]:
    """Fold the bead's workspace delta into the checkout (contract C4).

    `CONFLICT` fails exactly this bead (FR-034) — the checkout is
    restored by `fold_back()` itself before returning, so no undo is
    needed here. `APPLIED`/`EMPTY` are both a pass-through to `gate`,
    unless the environment-level protected-path check below rejects it
    first.

    `protection_policy` (a full `ProtectionPolicy` rooted at the
    checkout, not the narrow literal `fold_exclusions` fileset — that
    fileset only ever excludes an exact top-level path; it cannot
    replicate `ProtectionPolicy`'s recursive, case-insensitive, allowlist-
    aware matching) is this fold-back's environment-level check (T074-
    style split, `IsolationSession.mark_rejected`'s intended use): if any
    `applied_paths` entry the squash actually wrote is protected, the
    fold-back is undone and rejected here rather than trusting the
    fileset exclusion alone — the same "artifact-level checks run inside
    the lease, environment-level checks are the caller's job after"
    split the gate/undo_fold_back cycle already uses for the format/lint/
    test gate.
    """
    lease = _reconstruct_lease(state, checkout, now)
    result = await session.fold_back(lease)

    if result.outcome is FoldBackOutcome.CONFLICT:
        await _put_output(
            events,
            "fold_back",
            f"Fold-back conflict; abandoning this bead: {result.diagnostic}",
            level="error",
        )
        return {"outcome": result.outcome.value}, state.update(
            fold_back_result=result.to_dict(),
            unverified_in_checkout=False,
            bead_aborted=True,
            gate_failure_summary="",
        )

    if protection_policy is not None:
        blocked_paths = [
            path for path in result.applied_paths if protection_policy.protects_relpath(path)[0]
        ]
        if blocked_paths:
            await session.undo(lease, result)
            result = session.mark_rejected(
                result,
                diagnostic=f"protected path(s) folded back: {', '.join(blocked_paths)}",
            )
            await _put_output(
                events,
                "fold_back",
                f"Fold-back rejected — protected path(s) written: "
                f"{', '.join(blocked_paths)}; abandoning this bead",
                level="error",
            )
            return {"outcome": result.outcome.value}, state.update(
                fold_back_result=result.to_dict(),
                unverified_in_checkout=False,
                bead_aborted=True,
                gate_failure_summary="",
            )

    await _put_output(
        events,
        "fold_back",
        f"Folded back {len(result.applied_paths)} path(s) ({result.outcome.value})",
        level="info",
        metadata={"applied_paths": list(result.applied_paths)},
    )
    return {"outcome": result.outcome.value}, state.update(
        fold_back_result=result.to_dict(),
        unverified_in_checkout=True,
        gate_failure_summary="",
    )


@action(
    reads=["current_bead_id", "workspace_path", "fold_back_result", "fix_round"],
    writes=[
        "fold_back_result",
        "unverified_in_checkout",
        "bead_aborted",
        "fix_round",
        "isolation_halt_reason",
    ],
)
async def undo_fold_back(
    state: State,
    *,
    session: IsolationSession,
    checkout: CheckoutPath,
    now: Any,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Undo a rejected fold-back after `gate` fails (contract C5).

    On success: the checkout is restored and the rejected delta is back
    in the workspace for a fix round (FR-017). `fix_round` increments;
    exhausting `MAX_GATE_FIX_ATTEMPTS` abandons the bead (unchanged budget
    from the non-isolated path, contract F5).

    On `IsolationUndoFailedError`: the worst state this feature can
    produce (unverified work possibly stranded in the checkout) — sets
    `isolation_halt_reason`, which `select_next_bead` reads to end the
    run without starting another bead (FR-018, contract F10). Never
    swallowed, never silently retried.
    """
    lease = _reconstruct_lease(state, checkout, now)
    result = _fold_back_result_from_dict(state["fold_back_result"])

    try:
        await session.undo(lease, result)
    except IsolationUndoFailedError as exc:
        await _put_output(
            events,
            "undo_fold_back",
            f"Undo failed — halting the run: {exc}",
            level="error",
        )
        return {"halted": True}, state.update(
            fold_back_result=session.mark_rejected(result, diagnostic=str(exc)).to_dict(),
            unverified_in_checkout=True,
            bead_aborted=True,
            isolation_halt_reason=str(exc),
        )

    new_fix_round = int(state.get("fix_round") or 0) + 1
    exhausted = new_fix_round > MAX_GATE_FIX_ATTEMPTS
    if exhausted:
        await _put_output(
            events,
            "undo_fold_back",
            "Gate fix attempts exhausted; abandoning this bead",
            level="error",
        )
    else:
        # Verification rejection (FR-019): the gate rejected an
        # otherwise-successful fold-back. Distinguishable in the event
        # stream from both CONFLICT (above) and an agent DISCARDED
        # failure — undo restored the checkout and this bead gets
        # another fix round.
        await _put_output(
            events,
            "undo_fold_back",
            f"Gate rejected the fold-back (round {new_fix_round}/{MAX_GATE_FIX_ATTEMPTS}); "
            "undone, retrying in the workspace",
            level="warning",
            metadata={"fix_round": new_fix_round},
        )
    return {"exhausted": exhausted}, state.update(
        fold_back_result=session.mark_rejected(result).to_dict(),
        unverified_in_checkout=False,
        bead_aborted=exhausted,
        fix_round=new_fix_round,
    )


@action(
    reads=[
        "current_bead_id",
        "implementer_escalation_level",
        "pending_assumptions",
        "fix_round",
        "gate_failure_summary",
        "isolated",
        "workspace_path",
    ],
    writes=[
        "implementer_escalation_level",
        "pending_assumptions",
        "bead_aborted",
        "protection_blocks",
    ],
)
async def gate_fix(
    state: State,
    *,
    squadron: FlySquadron,
    events: asyncio.Queue[ProgressEvent | None],
) -> tuple[dict[str, Any], State]:
    """Re-prompt the implementer on a gate failure, in the workspace.

    Isolated mode's graph-level counterpart to the non-isolated `gate`
    action's internal fix loop — the same `_run_fix` helper, the same
    budget (`MAX_GATE_FIX_ATTEMPTS`, enforced by `undo_fold_back`), just
    scoped to the workspace (FR-032) since the checkout has already been
    undone by the time this runs.
    """
    bead_id = state["current_bead_id"]
    escalation_level = int(state.get("implementer_escalation_level") or 0)
    pending = list(state.get("pending_assumptions") or ())
    round_n = int(state.get("fix_round") or 1)
    failure_message = state.get("gate_failure_summary") or "gate failed"

    async with agent_step_scope(state):
        ok, new_level, fix_assumptions = await _run_fix(
            squadron=squadron,
            events=events,
            bead_id=bead_id,
            phase="gate",
            round_n=round_n,
            failure_message=failure_message,
            initial_level=escalation_level,
        )
    pending.extend(fix_assumptions)
    result, new_state = await _with_protection_drain(
        (
            {"ok": ok},
            state.update(
                implementer_escalation_level=new_level,
                pending_assumptions=pending,
                bead_aborted=not ok,
            ),
        ),
        squadron=squadron,
        events=events,
    )
    return result, new_state


async def teardown_workspace(
    state: State,
    *,
    session: IsolationSession,
    checkout: CheckoutPath,
    policy: IsolationPolicy,
    jj_client: Any,
    squadron: FlySquadron,
) -> tuple[dict[str, Any], State]:
    """Tear down (or retain) this bead's workspace — the universal
    per-bead boundary, called on every path (success or abandonment),
    exactly once (contract C7).

    Not a `@action` — called directly from `record_outcome`'s isolated-mode
    branch in `actions.py` rather than as its own graph node, since
    `record_outcome` is already the existing universal per-bead funnel
    point and adding a parallel one would only invite them to drift.
    Re-roots the squadron's protection back to the checkout (`root=None`)
    so the next bead's agents never inherit a stale workspace-rooted
    policy from this one, regardless of whether the next bead is isolated.

    Always retains on an `isolation_halt_reason` (an `undo_fold_back`
    failure — the worst state this feature can produce), regardless of
    `policy.retain_on_failure`: the halt message (workflow.py, README's
    "Recovering from a stale journal") tells the user to inspect this
    exact workspace by hand, so tearing it down here — fly's ordinary
    `retain_on_failure=False` is about a routine retry on the next `fly`
    invocation, not this manual-recovery path — would delete the one
    thing the recovery instructions point at.
    """
    if not state.get("isolated") or not state.get("workspace_path"):
        return {"skipped": True}, state

    workspace_path = Path(state["workspace_path"])
    session.release_unit(workspace_path)
    await squadron.retarget_protection_for_isolation(None)

    unit = _unit_for(state)
    retain = state.get("bead_aborted") and (
        policy.retain_on_failure or state.get("isolation_halt_reason")
    )
    if retain:
        await workspace_lifecycle.retain(checkout=checkout, policy=policy, unit=unit)
    else:
        await workspace_lifecycle.teardown(
            checkout=checkout, policy=policy, unit=unit, jj_client=jj_client
        )
    return {"torn_down": True}, state.update(workspace_path="")
