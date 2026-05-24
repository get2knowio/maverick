"""``Squadron`` base — per-workflow agent lifecycle container.

A Squadron owns one set of airframe-backed agents for a single workflow
run. Subclasses (one per workflow) declare which agents to build in
:meth:`_build_agents`, calling :func:`runtime_for_agent` for each role.
Agents own their own :class:`airframe.AgentRuntime` instances — no
shared subprocess, no port allocation, no auth-password juggling. Each
adapter manages its own credentials at instantiation.

Wiring:

* Construct: ``Squadron(cwd=..., config=..., cost_sink=...)``
* Open: ``async with squadron:`` — builds agents, opens each one.
* Use: ``squadron.coder_for(...)``, ``squadron.build_briefing_agent(...)``
  etc., depending on the subclass.
* Bead boundary: ``with squadron.bead_context(bead_id=..., complexity=...):``
  then ``await squadron.rotate_for_new_bead()``.
* Close: ``__aexit__`` calls ``close()`` on every agent, which in turn
  closes each agent's airframe runtime.

The :func:`maverick.runtime.agent_factory.runtime_for_agent` factory
dispatches via :func:`airframe.runtime_for`, so a missing
``[<extra>]`` install surfaces as ``ImportError`` at squadron open
with the right pip hint, and a typo'd provider as ``ValueError``.
"""

from __future__ import annotations

import abc
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from maverick.agents.base import Agent
from maverick.agents.context import tagged
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.runtime.registry import CostSink

logger = get_logger(__name__)


class Squadron(abc.ABC):
    """Base class: owns a set of airframe-backed agents.

    Subclasses (one per workflow) declare which agents to build in
    :meth:`_build_agents` and expose them as attributes.
    """

    def __init__(
        self,
        *,
        cwd: Path,
        config: MaverickConfig,
        cost_sink: CostSink | None = None,
    ) -> None:
        self._cwd = cwd
        self._config = config
        self._cost_sink = cost_sink
        self._opened = False

    @property
    def cwd(self) -> Path:
        return self._cwd

    @property
    def config(self) -> MaverickConfig:
        return self._config

    @property
    def cost_sink(self) -> CostSink | None:
        return self._cost_sink

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def open(self) -> None:
        """Build the squadron's agents.

        Each agent's airframe runtime is constructed via
        :func:`runtime_for_agent`. A missing ``agents.<role>`` binding
        in :class:`MaverickConfig.agents` surfaces here as
        :class:`ValueError`; a missing adapter SDK surfaces as
        :class:`ImportError` with the right pip-extra hint.
        """
        if self._opened:
            return
        await self._build_agents()
        self._opened = True

    async def close(self) -> None:
        """Close all agents (which in turn closes their airframe runtimes)."""
        if not self._opened:
            return
        agents = list(self._all_agents())
        for agent in agents:
            try:
                await agent.close()
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                logger.debug(
                    "squadron.agent_close_failed",
                    squadron=type(self).__name__,
                    agent=agent.tag,
                    error=str(exc),
                )
        self._opened = False

    # ------------------------------------------------------------------
    # Bead boundary
    # ------------------------------------------------------------------

    @contextmanager
    def bead_context(self, *, bead_id: str, **extra_tags: str) -> Iterator[None]:
        """Canonical entry point for tagging a block of bead-scoped work.

        Wraps :func:`maverick.agents.context.tagged`. Every cost record
        captured by an agent inside the block — including those produced
        by tasks spawned via :func:`asyncio.gather` — is attributed to
        the supplied ``bead_id``. Extra tags (``complexity``,
        ``workflow``, etc.) ride along onto the structured-log row.

        Example:

            with squadron.bead_context(bead_id=bead.id, complexity=bead.complexity):
                await squadron.rotate_for_new_bead()
                payload = await squadron.coder.implement(prompt)
        """
        with tagged(bead_id=bead_id, **extra_tags):
            yield

    async def rotate_for_new_bead(self) -> None:
        """Rotate every agent's session — called between beads.

        Each agent's :meth:`Agent.rotate_session` resets its airframe
        runtime's scope; runtime-wide resources (HTTP clients,
        subprocess pools) survive.
        """
        for agent in self._all_agents():
            try:
                await agent.rotate_session()
            except Exception as exc:  # noqa: BLE001 — rotation is best-effort
                logger.debug(
                    "squadron.agent_rotate_failed",
                    squadron=type(self).__name__,
                    agent=agent.tag,
                    error=str(exc),
                )

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def _build_agents(self) -> None:
        """Construct + open the agents this squadron exposes."""

    @abc.abstractmethod
    def _all_agents(self) -> Iterable[Agent]:
        """Iterate every live agent — used for rotate / teardown."""


__all__ = ["Squadron"]
