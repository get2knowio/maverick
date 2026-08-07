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

Context-file protection (056-context-file-protection)
------------------------------------------------------

:meth:`open` builds one :class:`~maverick.protection.policy.ProtectionPolicy`
and one :class:`~maverick.protection.records.BlockCollector` for the whole
run — before :meth:`_build_agents` runs — and every subclass's
``_build_*`` helper threads ``protection_policy``/``block_collector``/
``workflow``/``baseline_manifest`` into each :class:`Agent` it
constructs (research.md R7's single DI seam). Subclasses name themselves
via :attr:`WORKFLOW_NAME` — the ``workflow`` field recorded on every
:class:`~maverick.protection.records.BlockRecord` this run's agents
produce.
"""

from __future__ import annotations

import abc
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Self

from maverick.agents.base import Agent
from maverick.agents.context import tagged
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.protection.policy import ProtectionPolicy
    from maverick.protection.records import BlockCollector
    from maverick.protection.snapshot import SnapshotManifest
    from maverick.runtime.registry import CostSink

logger = get_logger(__name__)


class Squadron(abc.ABC):
    """Base class: owns a set of airframe-backed agents.

    Subclasses (one per workflow) declare which agents to build in
    :meth:`_build_agents` and expose them as attributes.
    """

    #: Recorded as the ``workflow`` field on every
    #: :class:`~maverick.protection.records.BlockRecord` this squadron's
    #: agents produce. Subclasses override.
    WORKFLOW_NAME: ClassVar[str] = ""

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
        self._protection_policy: ProtectionPolicy | None = None
        self._block_collector: BlockCollector | None = None
        self._baseline_manifest: SnapshotManifest | None = None

    @property
    def cwd(self) -> Path:
        return self._cwd

    @property
    def config(self) -> MaverickConfig:
        return self._config

    @property
    def cost_sink(self) -> CostSink | None:
        return self._cost_sink

    @property
    def protection_policy(self) -> ProtectionPolicy | None:
        """The run's :class:`~maverick.protection.policy.ProtectionPolicy`.

        ``None`` until :meth:`open` has run.
        """
        return self._protection_policy

    @property
    def block_collector(self) -> BlockCollector | None:
        """The run's :class:`~maverick.protection.records.BlockCollector`.

        ``None`` until :meth:`open` has run. Workflows drain this at
        their reporting boundaries — see
        ``specs/056-context-file-protection/data-model.md``.
        """
        return self._block_collector

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def open(self) -> None:
        """Build the run's protection policy, then the squadron's agents.

        The :class:`~maverick.protection.policy.ProtectionPolicy` and
        :class:`~maverick.protection.records.BlockCollector` are built
        first (research.md R7) so every ``_build_*`` helper can thread
        them into the agents it constructs. Each agent's airframe
        runtime is constructed via :func:`runtime_for_agent`. A missing
        ``agents.<role>`` binding in :class:`MaverickConfig.agents`
        surfaces here as :class:`ValueError`; a missing adapter SDK
        surfaces as :class:`ImportError` with the right pip-extra hint.
        """
        if self._opened:
            return
        await self._build_protection()
        await self._build_agents()
        self._opened = True

    async def _build_protection(self) -> None:
        """Build this run's :class:`ProtectionPolicy` + collector + baseline.

        Best-effort: a failure here degrades to "protection off for this
        run" (``protection_policy`` stays ``None``, so every agent falls
        back to the pre-056 zero-behavior-change path) with a warning,
        rather than taking the whole squadron open down — an
        unavailable protection subsystem must never block real work.
        """
        from maverick.protection.config import lookup_protection_config
        from maverick.protection.policy import ProtectionPolicy
        from maverick.protection.records import BlockCollector
        from maverick.protection.snapshot import SnapshotManifest

        try:
            config = lookup_protection_config(self._config)
            policy = ProtectionPolicy.build(self._cwd, config)
            self._protection_policy = policy
            self._block_collector = BlockCollector()
            self._baseline_manifest = await SnapshotManifest.capture(policy.root, policy)
        except Exception as exc:  # noqa: BLE001 — protection setup must not block a run
            logger.warning(
                "squadron.protection_setup_failed",
                squadron=type(self).__name__,
                error=str(exc),
            )
            self._protection_policy = None
            self._block_collector = None
            self._baseline_manifest = None

    def _agent_protection_kwargs(self) -> dict[str, Any]:
        """DI bundle to splat into every ``Agent(...)`` this squadron builds.

        ``self._protection_policy`` is ``None`` until :meth:`open` calls
        :meth:`_build_protection` (or if it degraded on failure) — every
        subclass's ``_build_*`` helper runs from inside :meth:`_build_agents`,
        which :meth:`open` only calls afterward, so this is always safe to
        call from there.
        """
        return {
            "protection_policy": self._protection_policy,
            "block_collector": self._block_collector,
            "workflow": self.WORKFLOW_NAME,
            "baseline_manifest": self._baseline_manifest,
        }

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
