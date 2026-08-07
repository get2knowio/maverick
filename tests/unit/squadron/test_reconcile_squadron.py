"""Tests for :class:`maverick.squadron.reconcile.ReconcileSquadron`.

Pattern D path: airframe runtimes constructed via
:func:`runtime_for_agent`. The shared :func:`stub_airframe_runtime`
fixture in ``conftest.py`` patches :func:`airframe.runtime_for` so no
real adapter SDK is touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maverick.agents.reconciler import ReconcilerAgent
from maverick.agents.semantic_reviewer import SemanticDependentsAgent
from maverick.config import MaverickConfig
from maverick.squadron.reconcile import ReconcileSquadron


async def test_build_agents_builds_and_opens_both(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with ReconcileSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        assert isinstance(squadron.reconciler, ReconcilerAgent)
        assert isinstance(squadron.semantic, SemanticDependentsAgent)
    # Exactly two runtimes built (reconciler + semantic).
    assert len(stub_airframe_runtime["constructed"]) == 2


async def test_build_agents_uses_correct_provider_tier_roles(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """Reconciler binds the 'implement' role; semantic binds 'review'."""
    async with ReconcileSquadron(cwd=tmp_path, config=config_with_agents):
        pass
    providers = [r.provider_id for r in stub_airframe_runtime["constructed"]]
    models = [r.model for r in stub_airframe_runtime["constructed"]]
    implement_binding = config_with_agents.agents.implement
    review_binding = config_with_agents.agents.review
    assert implement_binding is not None
    assert review_binding is not None
    assert implement_binding.provider in providers
    assert review_binding.provider in providers
    assert implement_binding.model_id in models
    assert review_binding.model_id in models


async def test_reconciler_agent_has_implement_tier(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with ReconcileSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        assert squadron.reconciler.provider_tier == "implement"
        assert squadron.semantic.provider_tier == "review"


async def test_all_agents_yields_both(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with ReconcileSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        agents = list(squadron._all_agents())
        assert len(agents) == 2
        assert squadron.reconciler in agents
        assert squadron.semantic in agents


async def test_close_tears_down_both_runtimes(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with ReconcileSquadron(cwd=tmp_path, config=config_with_agents):
        pass
    close_counts = [r.close_calls for r in stub_airframe_runtime["constructed"]]
    assert len(close_counts) == 2
    assert all(c >= 1 for c in close_counts)


async def test_rotate_for_new_bead_resets_both_runtimes(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    """Every squadron now builds a real ``ProtectionPolicy`` at open time
    (056-context-file-protection), so ``Agent.rotate_session`` is a
    close-and-reopen of the airframe session rather than
    ``runtime.reset()`` (research.md R4).
    """
    async with ReconcileSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        await squadron.rotate_for_new_bead()
        constructed = stub_airframe_runtime["constructed"]
        assert len(constructed) == 2
        for runtime in constructed:
            assert len(runtime.sessions) == 2, runtime.sessions
            assert runtime.sessions[0].close_calls == 1
            assert runtime.sessions[1].close_calls == 0
    assert all(r.reset_calls == 0 for r in stub_airframe_runtime["constructed"])


async def test_requires_agents_config(tmp_path: Path) -> None:
    """An empty ``agents:`` block surfaces as ValueError at open."""
    config = MaverickConfig()
    with pytest.raises(ValueError, match="agents.implement"):
        async with ReconcileSquadron(cwd=tmp_path, config=config):
            pass
