"""Tests for the xoscar ``BeadCreatorActor``."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import xoscar as xo

from maverick.actors.xoscar.bead_creator import BeadCreatorActor
from maverick.actors.xoscar.messages import BeadsCreatedResult, CreateBeadsRequest


def _spec(sid: str, task: str, instructions: str = "") -> SimpleNamespace:
    return SimpleNamespace(id=sid, task=task, instructions=instructions)


@pytest.mark.asyncio
async def test_bead_creator_happy_path(pool_address: str) -> None:
    creation_result = SimpleNamespace(
        epic={"bd_id": "epic-42"},
        work_beads=["w1", "w2", "w3"],
        created_map={"wu-1": "task-1", "wu-2": "task-2", "wu-3": "task-3"},
    )

    ref = await xo.create_actor(
        BeadCreatorActor,
        plan_name="do-things",
        plan_objective="Do the things",
        cwd=Path("/tmp"),
        address=pool_address,
        uid="bead-creator",
    )
    try:
        with patch(
            "maverick.library.actions.beads.create_beads",
            new=AsyncMock(return_value=creation_result),
        ) as mock_create:
            result = await ref.create_beads(
                CreateBeadsRequest(
                    specs=(_spec("wu-1", "Task 1"), _spec("wu-2", "Task 2")),
                )
            )

        assert isinstance(result, BeadsCreatedResult)
        assert result.success is True
        assert result.epic_id == "epic-42"
        assert result.bead_count == 3
        assert result.deps_wired == 0
        mock_create.assert_awaited_once()
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_bead_creator_wires_dependencies(pool_address: str) -> None:
    creation_result = SimpleNamespace(
        epic={"bd_id": "epic-9"},
        work_beads=["w1"],
        created_map={"wu-1": "task-1"},
    )
    dep_result = SimpleNamespace(wired_count=2)

    ref = await xo.create_actor(
        BeadCreatorActor,
        plan_name="plan",
        plan_objective="Objective",
        cwd=Path("/tmp"),
        address=pool_address,
        uid="bead-creator",
    )
    try:
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=creation_result),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=dep_result),
            ) as mock_wire,
        ):
            result = await ref.create_beads(
                CreateBeadsRequest(
                    specs=(_spec("wu-1", "Task"),),
                    deps=({"from": "wu-1", "to": "wu-2"},),
                )
            )

        assert result.success is True
        assert result.deps_wired == 2
        mock_wire.assert_awaited_once()
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_bead_creator_reports_failure(pool_address: str) -> None:
    ref = await xo.create_actor(
        BeadCreatorActor,
        plan_name="plan",
        plan_objective="Objective",
        cwd=Path("/tmp"),
        address=pool_address,
        uid="bead-creator",
    )
    try:
        with patch(
            "maverick.library.actions.beads.create_beads",
            new=AsyncMock(side_effect=RuntimeError("bd not available")),
        ):
            result = await ref.create_beads(CreateBeadsRequest(specs=(_spec("wu-1", "Task"),)))

        assert result.success is False
        assert "bd not available" in result.error
    finally:
        await xo.destroy_actor(ref)
