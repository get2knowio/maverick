"""Tests for :class:`maverick.squadron.plan.PlanSquadron`.

Pattern D path: airframe runtimes constructed via
:func:`runtime_for_agent`. The shared :func:`stub_airframe_runtime`
fixture in ``conftest.py`` patches :func:`airframe.runtime_for` so
no real adapter SDK is touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from maverick.config import MaverickConfig
from maverick.squadron.plan import PlanSquadron


class _StubBriefingPayload(BaseModel):
    summary: str = ""


async def test_plan_squadron_builds_generator(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with PlanSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        assert squadron.generator is not None
    # Exactly one runtime built (the generator).
    assert len(stub_airframe_runtime["constructed"]) == 1


async def test_plan_squadron_build_briefing_agent_returns_unopened(
    stub_airframe_runtime: dict[str, Any],
    config_with_agents: MaverickConfig,
    tmp_path: Path,
) -> None:
    async with PlanSquadron(cwd=tmp_path, config=config_with_agents) as squadron:
        ba = squadron.build_briefing_agent(agent_name="scopist", result_model=_StubBriefingPayload)
    # Briefing built (and tracked so close() shuts it down even if caller forgets).
    assert ba.agent_name == "scopist"
    # Two runtimes total: one for the generator, one for the briefing.
    assert len(stub_airframe_runtime["constructed"]) == 2


async def test_plan_squadron_requires_agents_config(tmp_path: Path) -> None:
    """An empty ``agents:`` block surfaces as ValueError at open."""
    config = MaverickConfig()
    with pytest.raises(ValueError, match="agents.generate"):
        async with PlanSquadron(cwd=tmp_path, config=config):
            pass
