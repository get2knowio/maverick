"""Burr ``Application`` factory for the ``fly_beads`` workflow.

Wires the ``@action`` functions in :mod:`actions` into a state machine
that drives one ``maverick fly`` run.

Shape:

    init_state → select_next_bead
        ├─ loop_done → done
        └─ has bead → process_bead_start → implement
                ├─ failed → abandon_bead → record_outcome → select_next_bead (cycle)
                └─ ok → gate
                        ├─ failed → abandon_bead → record_outcome → select_next_bead
                        └─ passed → ac_check
                                ├─ failed → abandon_bead → record_outcome → ...
                                └─ passed → spec_check
                                        ├─ failed → abandon_bead → record_outcome → ...
                                        └─ passed → review → commit → record_outcome → ...

The recorder cycles back to ``select_next_bead`` until ``loop_done``
becomes true (no more beads, graceful stop, or max_beads reached).

Phase 3 simplifications (see :mod:`actions` docstring) — default
driver remains xoscar; opt in via ``MAVERICK_USE_BURR=fly``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from burr.core import ApplicationBuilder, action, expr

from maverick.burr import ProgressEventHook
from maverick.types import StepType
from maverick.workflows.fly_beads import actions as fly_actions

if TYPE_CHECKING:
    from maverick.events import ProgressEvent
    from maverick.squadron.fly import FlySquadron


__all__ = ["build_fly_application", "FLY_ACTION_LABELS", "FLY_TERMINAL_ACTIONS"]


FLY_ACTION_LABELS: dict[str, str] = {
    "init_state": "Init",
    "select_next_bead": "Selecting next bead",
    "process_bead_start": "Bead start",
    "implement": "Implementing",
    "gate": "Gate",
    "ac_check": "AC check",
    "spec_check": "Spec check",
    "review": "Reviewing",
    "create_human_bead": "Creating human review bead",
    "commit": "Committing",
    "abandon_bead": "Abandoning bead",
    "record_outcome": "Recording outcome",
    "done": "Done",
}

FLY_TERMINAL_ACTIONS: tuple[str, ...] = ("done",)


@action(reads=[], writes=[])
async def _done(state: Any) -> tuple[dict[str, Any], Any]:
    """No-op terminal action — provides a natural ``halt_after`` target."""
    return {"final": True}, state


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
) -> Any:
    """Build the ``Application`` for one fly run."""
    hook = ProgressEventHook(
        event_queue,
        terminal_actions=FLY_TERMINAL_ACTIONS,
        action_labels=FLY_ACTION_LABELS,
        step_type=StepType.AGENT,
    )

    builder: Any = (
        ApplicationBuilder()
        .with_actions(
            init_state=fly_actions.init_state,
            select_next_bead=fly_actions.select_next_bead.bind(
                epic_id=epic_id,
                cwd=cwd,
                max_beads=max_beads,
                events=event_queue,
                watch=watch,
                watch_interval=watch_interval,
                max_idle_polls=max_idle_polls,
            ),
            process_bead_start=fly_actions.process_bead_start,
            implement=fly_actions.implement.bind(squadron=squadron, events=event_queue),
            gate=fly_actions.gate.bind(
                squadron=squadron,
                events=event_queue,
                cwd=cwd,
                validation_commands=validation_commands,
            ),
            ac_check=fly_actions.ac_check.bind(squadron=squadron, events=event_queue, cwd=cwd),
            spec_check=fly_actions.spec_check.bind(
                squadron=squadron,
                events=event_queue,
                cwd=cwd,
                project_type=project_type,
            ),
            review=fly_actions.review.bind(squadron=squadron, events=event_queue),
            create_human_bead=fly_actions.create_human_bead.bind(
                cwd=cwd,
                epic_id=epic_id,
                flight_plan_name=flight_plan_name,
                events=event_queue,
            ),
            commit=fly_actions.commit.bind(cwd=cwd, events=event_queue),
            abandon_bead=fly_actions.abandon_bead.bind(events=event_queue),
            record_outcome=fly_actions.record_outcome,
            done=_done,
        )
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
            # Watch mode: count of consecutive empty-poll cycles.
            idle_polls=0,
        )
        .with_hooks(hook)
        .with_entrypoint("init_state")
        .with_transitions(
            ("init_state", "select_next_bead"),
            # Loop exit
            ("select_next_bead", "done", expr("loop_done")),
            # Resumed-from-checkpoint bead → cycle without process
            ("select_next_bead", "select_next_bead", expr("current_bead is None")),
            ("select_next_bead", "process_bead_start"),
            ("process_bead_start", "implement"),
            # Per-stage abort routing — each stage writes its
            # ``*_passed`` flag and ``bead_aborted`` on failure. The
            # transition predicates dispatch accordingly.
            ("implement", "abandon_bead", expr("not implement_ok")),
            ("implement", "gate"),
            ("gate", "abandon_bead", expr("not gate_passed")),
            ("gate", "ac_check"),
            ("ac_check", "abandon_bead", expr("not ac_passed")),
            ("ac_check", "spec_check"),
            ("spec_check", "abandon_bead", expr("not spec_passed")),
            ("spec_check", "review"),
            # Review either approves → commit, or escalates to
            # create_human_bead → commit. The bead's work still lands
            # in either case (commit applies the needs-human-review
            # trailer when the assumption bead is created).
            ("review", "create_human_bead", expr("needs_human_review")),
            ("review", "commit"),
            ("create_human_bead", "commit"),
            ("commit", "record_outcome"),
            ("abandon_bead", "record_outcome"),
            # Cycle back into the loop.
            ("record_outcome", "select_next_bead"),
        )
    )

    return builder.build()
