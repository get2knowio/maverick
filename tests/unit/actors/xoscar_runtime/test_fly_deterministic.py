"""Tests for xoscar deterministic fly actors: gate, ac_check, spec_check, committer.

Each actor takes a typed request and returns a typed result via ordinary
in-pool RPC — no MCP inbox, no ``supervisor_ref`` dependency.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import xoscar as xo

from maverick.actors.xoscar.ac_check import ACCheckActor
from maverick.actors.xoscar.committer import CommitterActor
from maverick.actors.xoscar.gate import GateActor
from maverick.actors.xoscar.messages import (
    ACRequest,
    ACResult,
    CommitRequest,
    CommitResult,
    GateRequest,
    GateResult,
    SpecRequest,
    SpecResult,
)
from maverick.actors.xoscar.spec_check import SpecCheckActor


@pytest.mark.asyncio
async def test_gate_happy_path(pool_address: str) -> None:
    ref = await xo.create_actor(GateActor, address=pool_address, uid="gate")
    try:
        with patch(
            "maverick.library.actions.validation.run_independent_gate",
            new=AsyncMock(return_value={"passed": True, "summary": "ok", "stages": []}),
        ):
            result = await ref.gate(GateRequest(cwd="/tmp"))
        assert isinstance(result, GateResult)
        assert result.passed is True
        assert result.summary == "ok"
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_gate_catches_exception(pool_address: str) -> None:
    ref = await xo.create_actor(GateActor, address=pool_address, uid="gate-err")
    try:
        with patch(
            "maverick.library.actions.validation.run_independent_gate",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await ref.gate(GateRequest(cwd="/tmp"))
        assert result.passed is False
        assert "boom" in result.summary
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_ac_check_no_verification_passes(pool_address: str) -> None:
    ref = await xo.create_actor(ACCheckActor, address=pool_address, uid="ac")
    try:
        # Description with no "Verification" section → immediate pass.
        result = await ref.ac_check(ACRequest(description="some task", cwd="/tmp"))
        assert isinstance(result, ACResult)
        assert result.passed is True
        assert result.reasons == ()
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_spec_check_no_changed_files_passes(pool_address: str) -> None:
    ref = await xo.create_actor(
        SpecCheckActor, project_type="rust", address=pool_address, uid="spec"
    )
    try:
        with patch.object(SpecCheckActor, "_get_changed_files", return_value=[]):
            result = await ref.spec_check(SpecRequest(cwd="/tmp"))
        assert isinstance(result, SpecResult)
        assert result.passed is True
        assert "no changed files" in result.details
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_spec_check_skip_for_non_rust(pool_address: str) -> None:
    ref = await xo.create_actor(
        SpecCheckActor, project_type="python", address=pool_address, uid="spec-py"
    )
    try:
        with patch.object(SpecCheckActor, "_get_changed_files", return_value=["src/foo.py"]):
            result = await ref.spec_check(SpecRequest(cwd="/tmp"))
        assert result.passed is True
        assert "python" in result.details
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_committer_happy_path(pool_address: str) -> None:
    ref = await xo.create_actor(CommitterActor, address=pool_address, uid="committer")
    try:
        with (
            patch(
                "maverick.library.actions.jj.commit_bead_changes",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "message": "bead(bead-1) [round-1]: do stuff\n\nBead: bead-1",
                        "change_id": "abc123",
                        "error": None,
                    }
                ),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await ref.commit(
                CommitRequest(bead_id="bead-1", title="do stuff", cwd="/tmp", tag="round-1")
            )
        assert isinstance(result, CommitResult)
        assert result.success is True
        assert result.commit_sha == "abc123"
        assert result.tag == "round-1"
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_committer_reports_error(pool_address: str) -> None:
    ref = await xo.create_actor(CommitterActor, address=pool_address, uid="committer-err")
    try:
        with patch(
            "maverick.library.actions.jj.commit_bead_changes",
            new=AsyncMock(side_effect=RuntimeError("jj missing")),
        ):
            result = await ref.commit(CommitRequest(bead_id="bead-1", title="nope", cwd="/tmp"))
        assert result.success is False
        assert "jj missing" in result.error
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_committer_does_not_mark_complete_when_commit_fails(
    pool_address: str,
) -> None:
    """Regression: a failed commit must NOT close the bead in bd.

    The 2026-05-03 cross-provider e2e on sample-maverick-project hit
    this: ``CommitterActor.commit`` called ``mark_bead_complete``
    unconditionally after the underlying commit, so a plain-git
    "Commit failed" still silently closed the bead. The next fly
    couldn't re-process it and the only indication of trouble was a
    log line. Now: ``mark_bead_complete`` runs only when
    ``commit_bead_changes`` reports ``success=True``.
    """
    ref = await xo.create_actor(
        CommitterActor, address=pool_address, uid="committer-no-close-on-fail"
    )
    mark_complete = AsyncMock(return_value=None)
    try:
        with (
            patch(
                "maverick.library.actions.jj.commit_bead_changes",
                new=AsyncMock(
                    return_value={
                        "success": False,
                        "message": "irrelevant",
                        "change_id": None,
                        "error": "git commit failed: nothing to commit",
                    }
                ),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=mark_complete,
            ),
        ):
            result = await ref.commit(
                CommitRequest(bead_id="bead-X", title="t", cwd="/tmp", tag=None)
            )
        assert result.success is False
        assert "nothing to commit" in result.error
        mark_complete.assert_not_awaited()
    finally:
        await xo.destroy_actor(ref)


@pytest.mark.asyncio
async def test_committer_includes_bead_trailer(pool_address: str) -> None:
    """Regression: the per-bead commit message must carry the
    ``Bead: <id>`` git trailer (see ``build_bead_commit_message``
    in ``workflows.fly_beads._commit``). Mirrors the same trailer the
    legacy in-process commit path emits."""
    ref = await xo.create_actor(CommitterActor, address=pool_address, uid="committer-trailer")
    captured: dict[str, str] = {}

    async def _capture(message: str = "", cwd: object = None) -> dict[str, object]:
        captured["message"] = message
        return {"success": True, "message": message, "change_id": "x", "error": None}

    try:
        with (
            patch(
                "maverick.library.actions.jj.commit_bead_changes",
                new=AsyncMock(side_effect=_capture),
            ),
            patch(
                "maverick.library.actions.beads.mark_bead_complete",
                new=AsyncMock(return_value=None),
            ),
        ):
            await ref.commit(CommitRequest(bead_id="B-7", title="do thing", cwd="/tmp", tag=None))
        assert captured["message"] == "bead(B-7): do thing\n\nBead: B-7"
    finally:
        await xo.destroy_actor(ref)
