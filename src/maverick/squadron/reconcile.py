"""``ReconcileSquadron`` — agents the ``reconcile`` workflow exercises.

* ``ReconcilerAgent`` (``implement`` role) — corrects code for a changed
  answer and resolves conflicts arising from the fold.
* ``SemanticDependentsAgent`` (``review`` role) — judges whether
  descendant changes still depend on a now-superseded assumption.

Both agents are fixed (no per-tier fan-out) and built eagerly at
``open()`` time — see ``specs/051-reconcile-changed-answers/research.md``
R11. ``Squadron.rotate_for_new_bead()`` (inherited, unchanged) rotates
both agents' sessions between answers.
"""

from __future__ import annotations

from collections.abc import Iterable

from maverick.agents.base import Agent
from maverick.agents.reconciler import ReconcilerAgent
from maverick.agents.semantic_reviewer import SemanticDependentsAgent
from maverick.runtime.agent_factory import runtime_for_agent
from maverick.squadron.base import Squadron


class ReconcileSquadron(Squadron):
    """Squadron for the reconcile workflow: reconciler + semantic-dependents agents."""

    WORKFLOW_NAME = "reconcile"

    reconciler: ReconcilerAgent
    semantic: SemanticDependentsAgent

    async def _build_agents(self) -> None:
        reconciler_runtime, _ = runtime_for_agent("implement", agents_config=self._config.agents)
        self.reconciler = ReconcilerAgent(
            runtime=reconciler_runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
            **self._agent_protection_kwargs(),
        )
        await self.reconciler.open()

        semantic_runtime, _ = runtime_for_agent("review", agents_config=self._config.agents)
        self.semantic = SemanticDependentsAgent(
            runtime=semantic_runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
            **self._agent_protection_kwargs(),
        )
        await self.semantic.open()

    def _all_agents(self) -> Iterable[Agent]:
        yield self.reconciler
        yield self.semantic


__all__ = ["ReconcileSquadron"]
