"""Burr ``Application`` factory for the ``fly_beads`` workflow.

Wires the ``@action`` functions in :mod:`actions` into a state machine
that drives one ``maverick fly`` run.

Shape:

    init_state → select_next_bead
        ├─ loop_done → reconcile_answers_final → aggregate_review → done
        └─ has bead → process_bead_start → implement
                ├─ failed → abandon_bead → record_assumptions → record_outcome (cycle)
                └─ ok → gate
                        ├─ failed → abandon_bead → record_assumptions → record_outcome
                        └─ passed → ac_check
                                ├─ failed → abandon_bead → record_assumptions → ...
                                └─ passed → spec_check
                                        ├─ failed → abandon_bead → record_assumptions → ...
                                        └─ passed → review
                                        ├─ needs_human_review → create_human_bead
                                        │       → record_assumptions → commit → ...
                                        └─ approved → record_assumptions → commit → ...

    record_assumptions branches on ``bead_aborted``: aborted beads skip
    commit and go straight to record_outcome; approved/human-review beads
    proceed to commit so the same run stamps the entries with the jj
    change ID.

    record_outcome → reconcile_answers → select_next_bead — every bead
    boundary (success via commit, or abandonment) funnels through
    record_outcome first, so this single edge covers both boundaries the
    mid-flight-reconcile contract names (052-conditional-landing, User
    Story 3): a running fly detects newly-answered assumption-ledger
    entries here and reconciles them in-process without stopping the
    drain loop. ``reconcile_answers_final`` runs once more on the
    loop-exit edge, before ``aggregate_review``, so an answer arriving
    during the last bead is still processed before the run completes
    (FR-009).

The recorder cycles back to ``select_next_bead`` until ``loop_done``
becomes true (no more beads, graceful stop, or max_beads reached).

This graph is the only fly drain loop — the earlier xoscar-actor
``FlySupervisor`` (and its ``MAVERICK_USE_BURR=fly`` opt-in) is retired.
See :mod:`maverick.workflows.fly_beads.actions` for each stage's contract.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from burr.core import ApplicationBuilder, action, expr

from maverick.burr import ProgressEventHook
from maverick.jj.client import JjClient
from maverick.logging import get_logger
from maverick.types import StepType
from maverick.workflows.fly_beads import _isolation as fly_isolation
from maverick.workflows.fly_beads import actions as fly_actions
from maverick.workspace import CheckoutPath

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from maverick.config import MaverickConfig
    from maverick.events import ProgressEvent
    from maverick.squadron.fly import FlySquadron
    from maverick.workspace import IsolationSession


__all__ = ["build_fly_application", "FLY_ACTION_LABELS", "FLY_TERMINAL_ACTIONS"]

logger = get_logger(__name__)


FLY_ACTION_LABELS: dict[str, str] = {
    "init_state": "Init",
    "select_next_bead": "Selecting next bead",
    "process_bead_start": "Bead start",
    "provision_workspace": "Provisioning workspace",
    "implement": "Implementing",
    "gate": "Gate",
    "ac_check": "AC check",
    "spec_check": "Spec check",
    "review": "Reviewing",
    "create_human_bead": "Creating human review bead",
    "fold_back": "Folding back",
    "undo_fold_back": "Undoing fold-back",
    "gate_fix": "Fixing gate failure",
    "record_assumptions": "Recording assumptions",
    "commit": "Committing",
    "abandon_bead": "Abandoning bead",
    "record_outcome": "Recording outcome",
    "reconcile_answers": "Reconciling answers",
    "reconcile_answers_final": "Reconciling answers (final)",
    "aggregate_review": "Aggregate review",
    "done": "Done",
}

FLY_TERMINAL_ACTIONS: tuple[str, ...] = ("done",)


@action(reads=[], writes=[])
async def _done(state: Any) -> tuple[dict[str, Any], Any]:
    """No-op terminal action — provides a natural ``halt_after`` target."""
    return {"final": True}, state


#: Non-isolated transitions — byte-identical to before 057 (FR-035).
_NON_ISOLATED_TRANSITIONS: tuple[tuple[Any, ...], ...] = (
    ("init_state", "select_next_bead"),
    # Loop exit funnels through one final mid-flight reconcile pass
    # (052-conditional-landing FR-009: an answer that arrived during the
    # last bead must still be processed before the run completes) and
    # then the aggregate (cross-bead) review so a finished epic gets a
    # single end-of-run pass.
    ("select_next_bead", "reconcile_answers_final", expr("loop_done")),
    ("reconcile_answers_final", "aggregate_review"),
    ("aggregate_review", "done"),
    # Resumed-from-checkpoint bead → cycle without process
    ("select_next_bead", "select_next_bead", expr("current_bead is None")),
    ("select_next_bead", "process_bead_start"),
    ("process_bead_start", "implement"),
    # Per-stage abort routing — each stage writes its ``*_passed`` flag
    # and ``bead_aborted`` on failure. The transition predicates dispatch
    # accordingly.
    ("implement", "abandon_bead", expr("not implement_ok")),
    ("implement", "gate"),
    ("gate", "abandon_bead", expr("not gate_passed")),
    ("gate", "ac_check"),
    ("ac_check", "abandon_bead", expr("not ac_passed")),
    ("ac_check", "spec_check"),
    ("spec_check", "abandon_bead", expr("not spec_passed")),
    ("spec_check", "review"),
    # Review either approves or escalates to create_human_bead; both
    # routes funnel through record_assumptions so any entries
    # accumulated this bead are created before commit stamps them with
    # the jj change ID. The bead's work still lands in either case
    # (commit applies the needs-human-review trailer when the
    # assumption bead is created).
    ("review", "create_human_bead", expr("needs_human_review")),
    ("review", "record_assumptions"),
    ("create_human_bead", "record_assumptions"),
    # Abort paths also funnel through record_assumptions so assumptions
    # accumulated before the abort (e.g. by the implementer, then a
    # gate/spec failure) still land in the ledger. record_assumptions
    # branches on ``bead_aborted``: aborted beads skip commit and go
    # straight to record_outcome.
    ("abandon_bead", "record_assumptions"),
    ("record_assumptions", "record_outcome", expr("bead_aborted")),
    ("record_assumptions", "commit"),
    ("commit", "record_outcome"),
    # Every bead boundary — success (commit) or abandonment — funnels
    # through record_outcome, so a single mid-flight reconcile splice
    # here covers both boundaries the contract names
    # (052-conditional-landing, User Story 3) before cycling back into
    # the loop.
    ("record_outcome", "reconcile_answers"),
    ("reconcile_answers", "select_next_bead"),
)

#: Isolated-mode transitions (057-isolated-bead-workspaces, US3). The one
#: deliberate ordering difference from non-isolated (research.md R6):
#: every agent step (implement, ac_check, spec_check, review, and any fix
#: round) stays in the workspace and runs *before* the fold-back; gate
#: runs against the checkout *after* it, since it needs the installed
#: toolchain (T074). A gate failure routes through undo_fold_back (restore
#: the checkout, keep the rejected delta in the workspace) → gate_fix (the
#: agent fixes it in the workspace) → fold_back (re-apply) → gate again,
#: bounded by MAX_GATE_FIX_ATTEMPTS (unchanged budget, now enforced by
#: undo_fold_back rather than an internal loop — see contracts/
#: fly-isolated-mode.md's per-bead sequence).
_ISOLATED_TRANSITIONS: tuple[tuple[Any, ...], ...] = (
    ("init_state", "select_next_bead"),
    ("select_next_bead", "reconcile_answers_final", expr("loop_done")),
    ("reconcile_answers_final", "aggregate_review"),
    ("aggregate_review", "done"),
    ("select_next_bead", "select_next_bead", expr("current_bead is None")),
    ("select_next_bead", "process_bead_start"),
    ("process_bead_start", "provision_workspace"),
    # A provisioning failure (the workspace itself couldn't be created)
    # abandons exactly this bead — nothing has been written anywhere yet,
    # so there is nothing to undo and no reason to halt the whole run.
    ("provision_workspace", "abandon_bead", expr("bead_aborted")),
    ("provision_workspace", "implement"),
    ("implement", "abandon_bead", expr("not implement_ok")),
    ("implement", "ac_check"),
    ("ac_check", "abandon_bead", expr("not ac_passed")),
    ("ac_check", "spec_check"),
    ("spec_check", "abandon_bead", expr("not spec_passed")),
    ("spec_check", "review"),
    ("review", "create_human_bead", expr("needs_human_review")),
    ("review", "fold_back"),
    ("create_human_bead", "fold_back"),
    # A fold-back conflict fails exactly this bead (FR-034) — the
    # checkout is already restored by fold_back() itself.
    ("fold_back", "abandon_bead", expr("bead_aborted")),
    ("fold_back", "gate"),
    ("gate", "undo_fold_back", expr("not gate_passed")),
    ("gate", "record_assumptions"),
    ("undo_fold_back", "abandon_bead", expr("bead_aborted")),
    ("undo_fold_back", "gate_fix"),
    ("gate_fix", "abandon_bead", expr("bead_aborted")),
    ("gate_fix", "fold_back"),
    ("abandon_bead", "record_assumptions"),
    ("record_assumptions", "record_outcome", expr("bead_aborted")),
    ("record_assumptions", "commit"),
    ("commit", "record_outcome"),
    ("record_outcome", "reconcile_answers"),
    ("reconcile_answers", "select_next_bead"),
)


def build_fly_application(
    *,
    squadron: FlySquadron,
    event_queue: asyncio.Queue[ProgressEvent | None],
    epic_id: str,
    cwd: str,
    max_beads: int = 0,
    completed_bead_ids: tuple[str, ...] = (),
    validation_commands: dict[str, tuple[str, ...]] | None = None,
    project_type: str = "rust",
    flight_plan_name: str = "",
    watch: bool = False,
    watch_interval: int = 30,
    max_idle_polls: int = 60,
    reconcile_config: MaverickConfig | None = None,
    fly_run_id: str = "",
    isolated: bool = False,
    isolation_session: IsolationSession | None = None,
    isolation_policy: Any = None,
    isolation_now: Callable[[], datetime] | None = None,
) -> Any:
    """Build the ``Application`` for one fly run.

    Args:
        reconcile_config: Full project config, threaded to the
            ``reconcile_answers``/``reconcile_answers_final`` mid-flight
            actions (052-conditional-landing) — named for what it's used
            for at this call site (gating + inheriting the reconcile round
            budgets), not its type (it's the same ``MaverickConfig`` every
            other action already has via its owning workflow).
        fly_run_id: This fly run's own ``run_id``, threaded to the
            mid-flight actions so a triggered ``ReconcileWorkflow`` pass
            can exclude this run from its concurrent-fly guard.
        isolated: 057-isolated-bead-workspaces — opt into isolated mode.
            ``False`` (the default) yields the exact non-isolated graph
            shape and transitions this workflow had before this feature
            (FR-035, SC-011). Required alongside ``isolation_session``/
            ``isolation_policy``/``isolation_now`` when ``True`` — the
            caller (``workflow.py``) owns the session's lock/journal
            lifecycle (``async with isolation_session:`` spans the whole
            driver run, not just this build call).
    """
    hook = ProgressEventHook(
        event_queue,
        terminal_actions=FLY_TERMINAL_ACTIONS,
        action_labels=FLY_ACTION_LABELS,
        step_type=StepType.AGENT,
    )

    actions: dict[str, Any] = {
        "init_state": fly_actions.init_state,
        "select_next_bead": fly_actions.select_next_bead.bind(
            epic_id=epic_id,
            cwd=cwd,
            max_beads=max_beads,
            events=event_queue,
            watch=watch,
            watch_interval=watch_interval,
            max_idle_polls=max_idle_polls,
        ),
        "process_bead_start": fly_actions.process_bead_start,
        "implement": fly_actions.implement.bind(squadron=squadron, events=event_queue),
        "gate": fly_actions.gate.bind(
            squadron=squadron,
            events=event_queue,
            cwd=cwd,
            validation_commands=validation_commands,
        ),
        "ac_check": fly_actions.ac_check.bind(squadron=squadron, events=event_queue, cwd=cwd),
        "spec_check": fly_actions.spec_check.bind(
            squadron=squadron,
            events=event_queue,
            cwd=cwd,
            project_type=project_type,
        ),
        "review": fly_actions.review.bind(squadron=squadron, events=event_queue),
        "create_human_bead": fly_actions.create_human_bead.bind(
            cwd=cwd,
            epic_id=epic_id,
            flight_plan_name=flight_plan_name,
            events=event_queue,
        ),
        "record_assumptions": fly_actions.record_assumptions.bind(
            cwd=cwd,
            epic_id=epic_id,
            events=event_queue,
            config=reconcile_config,
        ),
        "commit": fly_actions.commit.bind(cwd=cwd, events=event_queue),
        "abandon_bead": fly_actions.abandon_bead.bind(events=event_queue),
        "reconcile_answers": fly_actions.reconcile_answers.bind(
            cwd=cwd,
            config=reconcile_config,
            fly_run_id=fly_run_id,
            events=event_queue,
        ),
        "reconcile_answers_final": fly_actions.reconcile_answers_final.bind(
            cwd=cwd,
            config=reconcile_config,
            fly_run_id=fly_run_id,
            events=event_queue,
        ),
        "aggregate_review": fly_actions.aggregate_review.bind(
            squadron=squadron,
            events=event_queue,
            cwd=cwd,
            epic_id=epic_id,
            fly_run_id=fly_run_id,
        ),
        "done": _done,
    }

    if isolated:
        if isolation_session is None or isolation_policy is None or isolation_now is None:
            raise ValueError(
                "build_fly_application(isolated=True) requires isolation_session, "
                "isolation_policy, and isolation_now"
            )
        checkout = CheckoutPath(Path(cwd))
        jj_client = JjClient(cwd=checkout)

        # Environment-level protected-path check for fold_back (belt and
        # braces beyond the narrow fold_exclusions fileset — see
        # fold_back's docstring). Best-effort: a policy-build failure
        # degrades to "no post-fold-back protection check", mirroring
        # every other protection-setup failure mode in this codebase
        # (`Squadron._build_protection`, `retarget_protection_for_isolation`)
        # rather than blocking the run.
        fold_back_protection_policy: Any = None
        if reconcile_config is not None:
            try:
                from maverick.protection.config import lookup_protection_config
                from maverick.protection.policy import ProtectionPolicy

                fold_back_protection_policy = ProtectionPolicy.build(
                    checkout, lookup_protection_config(reconcile_config)
                )
            except Exception as exc:  # noqa: BLE001 — protection setup must not block a run
                logger.warning("fly_fold_back_protection_policy_build_failed", error=str(exc))
                fold_back_protection_policy = None

        actions["record_outcome"] = fly_actions.record_outcome.bind(
            isolation_policy=isolation_policy,
            checkout=checkout,
            jj_client=jj_client,
            squadron=squadron,
        )
        actions["provision_workspace"] = fly_isolation.provision_workspace.bind(
            session=isolation_session,
            policy=isolation_policy,
            checkout=checkout,
            jj_client=jj_client,
            squadron=squadron,
            events=event_queue,
        )
        actions["fold_back"] = fly_isolation.fold_back.bind(
            session=isolation_session,
            checkout=checkout,
            now=isolation_now,
            events=event_queue,
            protection_policy=fold_back_protection_policy,
        )
        actions["undo_fold_back"] = fly_isolation.undo_fold_back.bind(
            session=isolation_session,
            checkout=checkout,
            now=isolation_now,
            events=event_queue,
        )
        actions["gate_fix"] = fly_isolation.gate_fix.bind(squadron=squadron, events=event_queue)
        transitions = _ISOLATED_TRANSITIONS
    else:
        actions["record_outcome"] = fly_actions.record_outcome
        transitions = _NON_ISOLATED_TRANSITIONS

    builder: Any = (
        ApplicationBuilder()
        .with_actions(**actions)
        .with_state(
            # Loop accumulators.
            completed_bead_ids=list(completed_bead_ids),
            bead_events=[],
            processed_count=0,
            succeeded_count=0,
            failed_count=0,
            skipped_count=0,
            # Routing flags.
            loop_done=False,
            loop_done_reason="",
            # Per-bead slots (cleared on each select_next_bead).
            current_bead=None,
            current_bead_id="",
            fix_round=0,
            bead_aborted=False,
            bead_failed=False,
            needs_human_review=False,
            review_rounds=0,
            implement_ok=False,
            implement_summary=None,
            gate_passed=False,
            ac_passed=False,
            spec_passed=False,
            approved=False,
            commit_ok=False,
            last_review_findings=[],
            human_bead_id="",
            # Assumption ledger accumulators — reset per bead in
            # process_bead_start.
            pending_assumptions=[],
            recorded_assumption_ids=[],
            commit_change_id="",
            # Watch mode: count of consecutive empty-poll cycles.
            idle_polls=0,
            # Aggregate (cross-bead) review summary — None until the
            # post-loop ``aggregate_review`` action runs.
            aggregate_review_payload=None,
            # Reviewer / implementer transient-failure escalation:
            # per-bead step counts up the tier ladder. Reset to 0 on
            # each new bead.
            reviewer_escalation_level=0,
            implementer_escalation_level=0,
            # 056-context-file-protection: serialized BlockRecord dicts,
            # drained from the squadron's collector after every
            # agent-calling action and never read by any fix-loop action
            # (Guardrail 10 corollary — a separate slot from every
            # fixer-feeding slot above).
            protection_blocks=[],
            # 057-isolated-bead-workspaces: set once by init_state's
            # caller (this function), never reset. See
            # contracts/fly-isolated-mode.md's "New Burr state slots".
            isolated=isolated,
            workspace_path="",
            fold_back_result=None,
            unverified_in_checkout=False,
            isolation_halt_reason="",
            # Internal to gate's isolated-mode fix loop — the message a
            # gate_fix round re-prompts the implementer with. Reset on
            # every fold_back call, never read outside this module's
            # isolated actions.
            gate_failure_summary="",
        )
        .with_hooks(hook)
        .with_entrypoint("init_state")
        .with_transitions(*transitions)
    )

    return builder.build()
