"""Shared fixtures for xoscar actor tests.

Provides ``pool_address`` and ``pool`` fixtures that register a
fully-populated :class:`AgentsConfig` on the pool address so the
airframe fallback in each actor's ``_make_agent`` can construct an
:class:`airframe.AgentRuntime` for any role.

Tests that exercise the airframe path inject a stub agent directly
via ``agent=`` and bypass the fallback entirely. Tests that don't
pass ``agent=`` get an agent built via :func:`runtime_for_agent`
against the registered config — :func:`airframe.runtime_for` is
monkey-patched to a no-op stub adapter by the autouse fixture so no
real adapter SDK is touched.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.pool import create_pool
from maverick.config import AgentBindingConfig, AgentsConfig
from maverick.runtime.opencode import (
    invalidate_cache,
    register_agents_config,
    unregister_agents_config,
)


def _agents_config_for_tests() -> AgentsConfig:
    """Build an AgentsConfig with every role bound to a stub provider."""
    stub_binding = AgentBindingConfig(provider="claude", model_id="claude-haiku-4-5")
    return AgentsConfig(
        implement=stub_binding,
        review=stub_binding,
        briefing=stub_binding,
        decompose=stub_binding,
        generate=stub_binding,
    )


class _StubAdapterRuntime:
    """Stand-in for any :class:`airframe.AgentRuntime` adapter class.

    Returned by the monkey-patched :func:`airframe.runtime_for`. Tests
    that pass ``agent=`` bypass this entirely; tests relying on the
    actor's fallback get an agent constructed against this stub.
    """

    label = "stub-adapter"

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def reset(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError(
            "_StubAdapterRuntime cannot execute prompts — tests should pass "
            "agent= with a stub from tests.unit.agents.airframe_stubs instead."
        )


@pytest.fixture(autouse=True)
def _stub_airframe_for_actor_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub :func:`airframe.runtime_for` so the fallback never hits a real SDK."""

    def fake_runtime_for(_provider_id: str) -> type[_StubAdapterRuntime]:
        return _StubAdapterRuntime

    monkeypatch.setattr("airframe.runtime_for", fake_runtime_for)


@pytest.fixture
async def pool_address() -> AsyncIterator[str]:
    """Yield a pool's external address with an :class:`AgentsConfig` registered.

    The pool and agents-config binding are torn down on exit. Tests
    that create actors should ``xo.destroy_actor(ref)`` them explicitly
    so ``__pre_destroy__`` runs before the pool stops.
    """
    invalidate_cache()
    pool, address = await create_pool()
    register_agents_config(address, _agents_config_for_tests())
    try:
        yield address
    finally:
        unregister_agents_config(address)
        await pool.stop()


@pytest.fixture
async def pool() -> AsyncIterator[tuple[xo.Actor, str]]:
    """Yield ``(pool, address)`` with an :class:`AgentsConfig` registered."""

    invalidate_cache()
    pool_obj, address = await create_pool()
    register_agents_config(address, _agents_config_for_tests())
    try:
        yield pool_obj, address
    finally:
        unregister_agents_config(address)
        await pool_obj.stop()
