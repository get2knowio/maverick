"""Burr ``Application`` factory for the ``generate_flight_plan`` workflow.

Wires the ``@action`` functions in :mod:`actions` into a state machine
that mirrors the legacy ``PlanSupervisor`` shape:

    init_state
      → parallel_briefings (3 in parallel: scopist/analyst/criteria)
      → contrarian_briefing
      → synthesize_briefing
      → generate_plan
      → validate_plan
      → write_plan
      → done

When ``skip_briefing=True`` the briefing actions are routed around:
``init_state → generate_plan``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from burr.core import ApplicationBuilder, action

from maverick.burr import ProgressEventHook
from maverick.types import StepType
from maverick.workflows.generate_flight_plan import actions as plan_actions

if TYPE_CHECKING:
    from maverick.events import ProgressEvent
    from maverick.squadron.plan import PlanSquadron


__all__ = ["build_plan_application", "PLAN_ACTION_LABELS", "PLAN_TERMINAL_ACTIONS"]


PLAN_ACTION_LABELS: dict[str, str] = {
    "init_state": "Init",
    "parallel_briefings": "Briefing (parallel)",
    "contrarian_briefing": "Contrarian briefing",
    "synthesize_briefing": "Synthesizing briefing",
    "generate_plan": "Generating flight plan",
    "validate_plan": "Validating",
    "write_plan": "Writing flight plan",
    "done": "Done",
}

PLAN_TERMINAL_ACTIONS: tuple[str, ...] = ("done",)


@action(reads=[], writes=[])
async def _done(state: Any) -> tuple[dict[str, Any], Any]:
    """No-op terminal action — provides a natural ``halt_after`` target."""
    return {"final": True}, state


def build_plan_application(
    *,
    squadron: PlanSquadron,
    event_queue: asyncio.Queue[ProgressEvent | None],
    prd_content: str,
    plan_name: str,
    output_dir: str,
    skip_briefing: bool,
    provider_labels: dict[str, str] | None = None,
    max_briefing_agents: int = 3,
) -> Any:
    """Build the ``Application`` for one plan-generation run.

    Args:
        squadron: Open :class:`PlanSquadron` — owns the agents the
            actions invoke via ``squadron.generator`` /
            ``squadron.build_briefing_agent``.
        event_queue: Shared queue the actions + hook push
            :class:`ProgressEvent` instances into. The
            :class:`~maverick.burr.BurrWorkflowDriver` drains this.
        prd_content / plan_name / output_dir: Workflow inputs, seeded
            into ``State`` so actions can read them.
        skip_briefing: When ``True``, skip the four briefing actions
            and jump straight to ``generate_plan``.
        provider_labels: Optional ``label → "provider/model"`` map for
            emitted ``AgentStarted`` events. Defaults to empty.
        max_briefing_agents: Concurrency cap inside
            ``parallel_briefings``. Default 3 matches the legacy
            ``parallel.max_briefing_agents`` setting.

    Returns:
        A built :class:`burr.core.Application`. Caller passes it (plus
        the same ``event_queue``) to
        :class:`maverick.burr.BurrWorkflowDriver` to drive the run.
    """
    hook = ProgressEventHook(
        event_queue,
        terminal_actions=PLAN_TERMINAL_ACTIONS,
        action_labels=PLAN_ACTION_LABELS,
        step_type=StepType.AGENT,
    )

    builder: Any = (
        ApplicationBuilder()
        .with_actions(
            init_state=plan_actions.init_state,
            parallel_briefings=plan_actions.parallel_briefings.bind(
                squadron=squadron,
                events=event_queue,
                max_concurrent=max_briefing_agents,
            ),
            contrarian_briefing=plan_actions.contrarian_briefing.bind(
                squadron=squadron,
                events=event_queue,
            ),
            synthesize_briefing=plan_actions.synthesize_briefing,
            generate_plan=plan_actions.generate_plan.bind(
                squadron=squadron,
                events=event_queue,
            ),
            validate_plan=plan_actions.validate_plan.bind(events=event_queue),
            write_plan=plan_actions.write_plan.bind(
                output_dir=output_dir,
                events=event_queue,
            ),
            done=_done,
        )
        .with_state(
            prd_content=prd_content,
            plan_name=plan_name,
            provider_labels=dict(provider_labels or {}),
            briefs={},
            briefing_markdown="",
            flight_plan=None,
            flight_plan_path=None,
            briefing_path=None,
            validation_passed=True,
            skip_briefing=skip_briefing,
        )
        .with_hooks(hook)
        .with_entrypoint("init_state")
    )

    if skip_briefing:
        builder = builder.with_transitions(
            ("init_state", "generate_plan"),
            ("generate_plan", "validate_plan"),
            ("validate_plan", "write_plan"),
            ("write_plan", "done"),
        )
    else:
        builder = builder.with_transitions(
            ("init_state", "parallel_briefings"),
            ("parallel_briefings", "contrarian_briefing"),
            ("contrarian_briefing", "synthesize_briefing"),
            ("synthesize_briefing", "generate_plan"),
            ("generate_plan", "validate_plan"),
            ("validate_plan", "write_plan"),
            ("write_plan", "done"),
        )

    return builder.build()
