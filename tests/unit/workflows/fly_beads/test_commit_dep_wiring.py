"""Regression tests for the discovered-from dependency wiring in _commit.py.

Locks in the migration from raw ``bd dep add`` CommandRunner calls to
``BeadClient.add_dependency`` (research R11 / task T008).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.beads.models import BeadDependency, DependencyType
from maverick.workflows.fly_beads._commit import (
    _create_followup_bead,
    _escalate_to_replan,
)
from maverick.workflows.fly_beads.models import BeadContext


def _make_ctx(**overrides: object) -> BeadContext:
    defaults: dict[str, object] = {
        "bead_id": "bead-1",
        "title": "Do the thing",
        "description": "desc",
        "epic_id": "epic-1",
        "cwd": Path("/tmp/repo"),
        "discovered_from_chain": [],
    }
    defaults.update(overrides)
    return BeadContext(**defaults)  # type: ignore[arg-type]


class _FakeRunnerResult:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout


class TestCreateFollowupBeadDepWiring:
    @pytest.mark.asyncio
    async def test_wires_discovered_from_via_bead_client(self) -> None:
        ctx = _make_ctx()
        wf = AsyncMock()

        with (
            patch(
                "maverick.runners.command.CommandRunner.run",
                new=AsyncMock(return_value=_FakeRunnerResult('{"id": "followup-1"}')),
            ),
            patch(
                "maverick.beads.client.BeadClient.add_dependency",
                new=AsyncMock(),
            ) as mock_add_dep,
        ):
            await _create_followup_bead(wf, ctx, ["review failed"])

        mock_add_dep.assert_awaited_once()
        dep = mock_add_dep.await_args.args[0]
        assert isinstance(dep, BeadDependency)
        assert dep.blocker_id == "bead-1"
        assert dep.blocked_id == "followup-1"
        assert dep.dep_type == DependencyType.DISCOVERED_FROM


class TestEscalateToReplanDepWiring:
    @pytest.mark.asyncio
    async def test_wires_discovered_from_for_each_chain_member(self) -> None:
        ctx = _make_ctx(discovered_from_chain=["root-1", "mid-1"])
        wf = AsyncMock()

        async def _fake_run(cmd: list[str], *_a: object, **_kw: object) -> _FakeRunnerResult:
            if cmd[:2] == ["bd", "create"]:
                return _FakeRunnerResult('{"id": "replan-1"}')
            return _FakeRunnerResult("")

        with (
            patch(
                "maverick.runners.command.CommandRunner.run",
                new=AsyncMock(side_effect=_fake_run),
            ),
            patch(
                "maverick.beads.client.BeadClient.add_dependency",
                new=AsyncMock(),
            ) as mock_add_dep,
            patch(
                "maverick.workflows.fly_beads._commit._defer_dependent_beads",
                new=AsyncMock(),
            ),
        ):
            await _escalate_to_replan(wf, ctx, ["review failed"])

        assert mock_add_dep.await_count == 3  # root-1, mid-1, bead-1
        wired = {
            (call.args[0].blocker_id, call.args[0].blocked_id, call.args[0].dep_type)
            for call in mock_add_dep.await_args_list
        }
        assert wired == {
            ("root-1", "replan-1", DependencyType.DISCOVERED_FROM),
            ("mid-1", "replan-1", DependencyType.DISCOVERED_FROM),
            ("bead-1", "replan-1", DependencyType.DISCOVERED_FROM),
        }
