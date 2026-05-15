"""Tests for :class:`maverick.squadron.plan.PlanSquadron`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from maverick.config import MaverickConfig
from maverick.squadron.plan import PlanSquadron
from tests.unit.agents.conftest import FakeClient, fake_handle, payload_send_result


class _StubBriefingPayload(BaseModel):
    summary: str = ""


@pytest.fixture
def fake_squadron_handle(monkeypatch: Any) -> Any:
    handle = fake_handle()

    async def _fake_spawn(*_args: Any, **_kwargs: Any) -> Any:
        return handle

    async def _fake_validate(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("maverick.squadron.base.spawn_opencode_server", _fake_spawn)
    monkeypatch.setattr("maverick.squadron.base.validate_model_id", _fake_validate)
    return handle


@pytest.fixture
def fake_agent_clients(monkeypatch: Any) -> dict[str, FakeClient]:
    clients: dict[str, FakeClient] = {}

    def _build_client(self: Any) -> Any:
        c = FakeClient(send_result=payload_send_result({"summary": "x"}))
        clients[self.tag] = c
        return c

    monkeypatch.setattr("maverick.agents.base.Agent._build_client", _build_client)
    return clients


async def test_plan_squadron_builds_generator(
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    config = MaverickConfig()
    async with PlanSquadron(cwd=tmp_path, config=config) as squadron:
        assert squadron.generator is not None


async def test_plan_squadron_build_briefing_agent_returns_unopened(
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    config = MaverickConfig()
    async with PlanSquadron(cwd=tmp_path, config=config) as squadron:
        ba = squadron.build_briefing_agent(agent_name="scopist", result_model=_StubBriefingPayload)
    # Briefing built (not yet opened — caller opens it).
    assert ba.agent_name == "scopist"
