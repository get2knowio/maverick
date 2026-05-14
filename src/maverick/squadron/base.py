"""``Squadron`` base — substrate lifecycle + agent factory."""

from __future__ import annotations

import abc
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from maverick.agents.base import Agent
from maverick.logging import get_logger
from maverick.runtime.opencode import (
    CostSink,
    OpenCodeClient,
    OpenCodeModelNotFoundError,
    OpenCodeServerHandle,
    ProviderModel,
    Tier,
    invalidate_cache,
    resolve_tier,
    spawn_opencode_server,
    validate_model_id,
)

if TYPE_CHECKING:
    from maverick.config import MaverickConfig

logger = get_logger(__name__)


class Squadron(abc.ABC):
    """Base class: owns one OpenCode server + a set of agents.

    Subclasses (one per workflow) declare which agents to build in
    :meth:`_build_agents` and expose them as attributes.

    Path A wiring (current step): the squadron *owns* the server but
    actors still construct their own agents via the pool registry. The
    workflow passes ``squadron.handle`` / ``squadron.tier_overrides`` /
    ``squadron.cost_sink`` into ``actor_pool(...)`` so the existing
    registry lookups (``opencode_handle_for(self.address)`` etc.) keep
    working unchanged.
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
        self._tier_overrides: dict[str, Tier] = self._build_tier_overrides(config)

        # Set in __aenter__.
        self._handle: OpenCodeServerHandle | None = None
        self._owns_handle = False
        self._opened = False

    @property
    def cwd(self) -> Path:
        return self._cwd

    @property
    def config(self) -> MaverickConfig:
        return self._config

    @property
    def handle(self) -> OpenCodeServerHandle:
        if self._handle is None:
            raise RuntimeError(f"{type(self).__name__} not opened — use `async with squadron:`")
        return self._handle

    @property
    def tier_overrides(self) -> dict[str, Tier]:
        return self._tier_overrides

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
        """Spawn OpenCode, validate tier bindings, build agents."""
        if self._opened:
            return
        self._handle = await spawn_opencode_server()
        self._owns_handle = True
        # Drop any cached provider snapshots from previous runs against
        # the same base_url before this run validates its bindings.
        invalidate_cache(self._handle.base_url)
        try:
            await self._validate_tier_bindings()
            await self._build_agents()
        except BaseException:
            await self._teardown_handle()
            raise
        self._opened = True

    async def close(self) -> None:
        """Close all agents, then tear down the server."""
        if not self._opened and self._handle is None:
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
        await self._teardown_handle()
        self._opened = False

    async def _teardown_handle(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is not None and self._owns_handle:
            try:
                await handle.stop()
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                logger.debug(
                    "squadron.opencode_stop_failed",
                    squadron=type(self).__name__,
                    error=str(exc),
                )
        self._owns_handle = False

    # ------------------------------------------------------------------
    # Bead boundary
    # ------------------------------------------------------------------

    async def rotate_for_new_bead(self) -> None:
        """Rotate every agent's OpenCode session.

        Workflows call this between beads; agents that have role-specific
        rotation behaviour (e.g. the reviewer reset its review-round
        counter) handle it inside :meth:`Agent.rotate_session`.
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

    @abc.abstractmethod
    def _declared_bindings(self) -> Iterable[ProviderModel]:
        """Every (provider, model) binding the squadron will exercise.

        Used at startup to pre-validate against the live OpenCode
        server's ``/provider`` endpoint, collapsing the silent
        bad-modelID landmine to one place.
        """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_tier_overrides(self, config: MaverickConfig) -> dict[str, Tier]:
        """Pull tier overrides out of :class:`ProviderTiersConfig`.

        Normalises the on-disk shape (``{tier_name: [ProviderModelEntry, ...]}``)
        to the runtime's ``{tier_name: Tier}`` dict consumed directly by
        :func:`resolve_tier` and the agent cascade.
        """
        provider_tiers = getattr(config, "provider_tiers", None)
        if provider_tiers is None:
            return {}
        tiers = getattr(provider_tiers, "tiers", None)
        if not tiers:
            return {}
        out: dict[str, Tier] = {}
        for tier_name, entries in tiers.items():
            bindings = tuple(ProviderModel(entry.provider, entry.model_id) for entry in entries)
            if bindings:
                out[tier_name] = Tier(name=tier_name, bindings=bindings)
        return out

    async def _validate_tier_bindings(self) -> None:
        """Validate every declared binding against the live server.

        Runs against the just-spawned server so a typo'd model ID in
        ``maverick.yaml`` (the silent bad-modelID landmine) fails fast
        at workflow start instead of mid-run.

        A binding whose **provider** isn't connected on this server is
        not an error — that's a legitimate cascade scenario (e.g.
        ``opencode-go`` configured by default but not authenticated in
        the local dev environment). The cascade will skip it at first
        send. We only raise when the provider IS connected but the
        model ID isn't listed under it.
        """
        if self._handle is None:
            return
        bindings = list(self._declared_bindings())
        if not bindings:
            return
        seen: set[ProviderModel] = set()
        client = OpenCodeClient(
            base_url=self._handle.base_url,
            password=self._handle.password,
        )
        try:
            for binding in bindings:
                if binding in seen:
                    continue
                seen.add(binding)
                try:
                    await validate_model_id(client, binding.provider_id, binding.model_id)
                except OpenCodeModelNotFoundError as exc:
                    body = getattr(exc, "body", None) or {}
                    if "model_id" in body:
                        raise
                    logger.info(
                        "squadron.binding_skipped",
                        provider_id=binding.provider_id,
                        model_id=binding.model_id,
                        reason="provider_not_connected",
                    )
        finally:
            await client.aclose()

    def _resolved_bindings_for(self, agent_cls: type[Agent]) -> tuple[ProviderModel, ...]:
        """Resolve a tier name to the bindings the cascade will try.

        Subclass helper. Honours :attr:`Squadron.tier_overrides` so user
        config is reflected in the validation pass.
        """
        tier_name = getattr(agent_cls, "provider_tier", None)
        if not tier_name:
            return ()
        try:
            tier = resolve_tier(tier_name, override=self._tier_overrides)
        except KeyError:
            return ()
        return tuple(tier.bindings)


__all__ = ["Squadron"]
