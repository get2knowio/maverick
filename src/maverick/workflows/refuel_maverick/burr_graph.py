"""Burr ``Application`` factory for the ``refuel_maverick`` workflow.

Wires the ``@action`` functions in :mod:`actions` into a state machine
that mirrors the legacy ``RefuelSupervisor`` shape:

    init_state
      → parallel_briefings (3 in parallel: navigator/structuralist/recon)
      → contrarian_briefing
      → synthesize_briefing
      → outline
      → detail_fan_out
      → validate
      → check_validation
          ├─ (passed OR fix_rounds >= 3) → create_beads → done
          └─ otherwise → request_fix → validate → check_validation (cycle)

When ``skip_briefing=True`` the briefing actions are skipped and the
graph routes ``init_state → outline``.

``init_state`` also seeds briefs / outline / per-unit details from
``<cache_dir>/`` when an earlier run left one, and every producing
action short-circuits on an already-populated slot — so a re-run after
a mid-flight failure resumes rather than re-pays.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from burr.core import ApplicationBuilder, action, expr

from maverick.burr import ProgressEventHook
from maverick.types import StepType
from maverick.workflows.refuel_maverick import actions as refuel_actions

if TYPE_CHECKING:
    from maverick.events import ProgressEvent
    from maverick.squadron.refuel import RefuelSquadron


__all__ = ["build_refuel_application", "REFUEL_ACTION_LABELS", "REFUEL_TERMINAL_ACTIONS"]


REFUEL_ACTION_LABELS: dict[str, str] = {
    "init_state": "Init",
    "parallel_briefings": "Briefing (parallel)",
    "contrarian_briefing": "Contrarian briefing",
    "synthesize_briefing": "Synthesizing briefing",
    "outline": "Outline",
    "detail_fan_out": "Details (fan-out)",
    "validate": "Validating",
    "check_validation": "Validation gate",
    "request_fix": "Requesting fix",
    "create_beads": "Creating beads",
    "done": "Done",
}

REFUEL_TERMINAL_ACTIONS: tuple[str, ...] = ("done",)


@action(reads=[], writes=[])
async def _done(state: Any) -> tuple[dict[str, Any], Any]:
    """No-op terminal action — provides a natural ``halt_after`` target."""
    return {"final": True}, state


def build_refuel_application(
    *,
    squadron: RefuelSquadron,
    event_queue: asyncio.Queue[ProgressEvent | None],
    raw_content: str,
    briefing_prompt: str,
    codebase_context: Any,
    open_bead_context: Any | None,
    runway_context_text: str | None,
    plan_name: str,
    plan_objective: str,
    cwd: str,
    skip_briefing: bool,
    provider_labels: dict[str, str] | None = None,
    max_briefing_agents: int = 3,
    decomposer_pool_size: int = 3,
    success_criteria_count: int = 0,
    expected_sc_refs: tuple[str, ...] = (),
    cache_dir: str = "",
) -> Any:
    """Build the ``Application`` for one refuel run.

    See :mod:`actions` for the documented Phase 2 simplifications.
    """
    hook = ProgressEventHook(
        event_queue,
        terminal_actions=REFUEL_TERMINAL_ACTIONS,
        action_labels=REFUEL_ACTION_LABELS,
        step_type=StepType.AGENT,
    )

    builder: Any = (
        ApplicationBuilder()
        .with_actions(
            init_state=refuel_actions.init_state.bind(
                cache_dir=cache_dir,
                events=event_queue,
            ),
            parallel_briefings=refuel_actions.parallel_briefings.bind(
                squadron=squadron,
                events=event_queue,
                max_concurrent=max_briefing_agents,
                cache_dir=cache_dir,
            ),
            contrarian_briefing=refuel_actions.contrarian_briefing.bind(
                squadron=squadron,
                events=event_queue,
                cache_dir=cache_dir,
            ),
            synthesize_briefing=refuel_actions.synthesize_briefing.bind(
                cache_dir=cache_dir,
                events=event_queue,
            ),
            outline=refuel_actions.outline.bind(
                squadron=squadron,
                events=event_queue,
                cache_dir=cache_dir,
            ),
            detail_fan_out=refuel_actions.detail_fan_out.bind(
                squadron=squadron,
                events=event_queue,
                pool_size=decomposer_pool_size,
                cache_dir=cache_dir,
            ),
            validate=refuel_actions.validate.bind(
                events=event_queue,
                expected_sc_refs=expected_sc_refs,
                sc_count=success_criteria_count,
            ),
            request_fix=refuel_actions.request_fix.bind(
                squadron=squadron,
                events=event_queue,
            ),
            check_validation=refuel_actions.check_validation,
            create_beads=refuel_actions.create_beads.bind(
                cwd=cwd,
                plan_name=plan_name,
                plan_objective=plan_objective,
                events=event_queue,
            ),
            done=_done,
        )
        .with_state(
            raw_content=raw_content,
            briefing_prompt=briefing_prompt,
            codebase_context=codebase_context,
            open_bead_context=open_bead_context,
            runway_context_text=runway_context_text,
            plan_name=plan_name,
            plan_objective=plan_objective,
            provider_labels=dict(provider_labels or {}),
            briefs={},
            briefing_markdown="",
            outline=None,
            accumulated_details=[],
            cached_details={},
            specs=[],
            fix_rounds=0,
            validation_passed=False,
            validation_warnings=[],
            untraced_criteria=[],
            validation_complete=False,
            epic_id="",
            epic=None,
            work_beads=[],
            created_map={},
            dependencies=[],
            deps_wired=0,
            abandoned_unit_ids=[],
            skip_briefing=skip_briefing,
        )
        .with_hooks(hook)
        .with_entrypoint("init_state")
    )

    transitions: list[tuple[str, ...]] = []
    if skip_briefing:
        transitions.append(("init_state", "outline"))
    else:
        transitions.extend(
            [
                ("init_state", "parallel_briefings"),
                ("parallel_briefings", "contrarian_briefing"),
                ("contrarian_briefing", "synthesize_briefing"),
                ("synthesize_briefing", "outline"),
            ]
        )
    transitions.extend(
        [
            ("outline", "detail_fan_out"),
            ("detail_fan_out", "validate"),
            ("validate", "check_validation"),
        ]
    )

    builder = builder.with_transitions(
        *transitions,
        # Validation gate: passed or out-of-budget → create_beads;
        # otherwise re-enter the fix loop.
        ("check_validation", "create_beads", expr("validation_complete")),
        ("check_validation", "request_fix"),
        ("request_fix", "validate"),
        ("create_beads", "done"),
    )

    return builder.build()
