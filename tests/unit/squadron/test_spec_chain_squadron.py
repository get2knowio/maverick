"""Tests for :class:`maverick.squadron.spec_chain.SpecChainSquadron`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.config import MaverickConfig
from maverick.squadron.spec_chain import SpecChainSquadron


async def test_spec_chain_squadron_builds_chain_agent(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with SpecChainSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        assert squadron.chain_agent is not None
    # Exactly one runtime built (the chain agent, bound to the "generate" role).
    assert len(stub_airframe_runtime["constructed"]) == 1


async def test_spec_chain_squadron_close_closes_chain_agent_runtime(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with SpecChainSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        runtime = squadron.chain_agent._runtime
    assert runtime.close_calls == 1
