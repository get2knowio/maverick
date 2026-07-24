"""Tests for reconcile run-state persistence and lockfile helpers.

Covers data-model.md §3 (``ReconcileRunState``/``AnswerState`` persistence)
and research.md R9/R14 (resumable discovery + pid-stamped lockfile).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from maverick.workflows.reconcile.models import ReconcileStage
from maverick.workflows.reconcile.state import (
    AnswerState,
    ReconcileRunState,
    acquire_lock,
    discover_resumable,
    load_run_state,
    release_lock,
    save_run_state,
)


def _make_state(run_id: str, status: str, updated_at: str) -> ReconcileRunState:
    return ReconcileRunState(
        run_id=run_id,
        status=status,  # type: ignore[arg-type]
        updated_at=updated_at,
        answers=[
            AnswerState(
                entry_id="bd-1",
                target_change_id="abc123",
                restore_op_id="op-1",
                stage=ReconcileStage.SNAPSHOTTED,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_save_and_load_round_trip(tmp_path: Path) -> None:
    state = _make_state("run-1", "running", "2026-07-24T00:00:00Z")

    await save_run_state(state, tmp_path)
    loaded = await load_run_state("run-1", tmp_path)

    assert loaded is not None
    assert loaded.run_id == "run-1"
    assert loaded.status == "running"
    assert loaded.schema_version == 1
    assert len(loaded.answers) == 1
    answer = loaded.answers[0]
    assert answer.entry_id == "bd-1"
    assert answer.target_change_id == "abc123"
    assert answer.restore_op_id == "op-1"
    assert answer.stage == ReconcileStage.SNAPSHOTTED
    assert answer.terminal_status is None
    assert answer.reason == ""

    state_path = tmp_path / ".maverick" / "runs" / "run-1" / "reconcile.json"
    assert state_path.is_file()


@pytest.mark.asyncio
async def test_load_run_state_missing_returns_none(tmp_path: Path) -> None:
    result = await load_run_state("does-not-exist", tmp_path)
    assert result is None


@pytest.mark.asyncio
async def test_answer_state_defaults(tmp_path: Path) -> None:
    answer = AnswerState(
        entry_id="bd-2",
        target_change_id=None,
        restore_op_id=None,
        stage=ReconcileStage.PENDING,
    )
    assert answer.terminal_status is None
    assert answer.reason == ""


@pytest.mark.asyncio
async def test_discover_resumable_finds_newest_running(tmp_path: Path) -> None:
    older_running = _make_state("run-old", "running", "2026-07-20T00:00:00Z")
    newer_running = _make_state("run-new", "running", "2026-07-24T00:00:00Z")
    completed = _make_state("run-done", "completed", "2026-07-25T00:00:00Z")
    failed = _make_state("run-failed", "failed", "2026-07-26T00:00:00Z")

    for state in (older_running, newer_running, completed, failed):
        await save_run_state(state, tmp_path)

    resumable = await discover_resumable(tmp_path)

    assert resumable is not None
    assert resumable.run_id == "run-new"


@pytest.mark.asyncio
async def test_discover_resumable_returns_none_when_no_running(tmp_path: Path) -> None:
    completed = _make_state("run-done", "completed", "2026-07-25T00:00:00Z")
    await save_run_state(completed, tmp_path)

    resumable = await discover_resumable(tmp_path)

    assert resumable is None


@pytest.mark.asyncio
async def test_discover_resumable_skips_corrupt_files(tmp_path: Path) -> None:
    good = _make_state("run-good", "running", "2026-07-24T00:00:00Z")
    await save_run_state(good, tmp_path)

    corrupt_dir = tmp_path / ".maverick" / "runs" / "run-corrupt"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "reconcile.json").write_text("{not valid json", encoding="utf-8")

    resumable = await discover_resumable(tmp_path)

    assert resumable is not None
    assert resumable.run_id == "run-good"


@pytest.mark.asyncio
async def test_discover_resumable_no_runs_dir(tmp_path: Path) -> None:
    resumable = await discover_resumable(tmp_path)
    assert resumable is None


@pytest.mark.asyncio
async def test_acquire_and_release_lock_happy_path(tmp_path: Path) -> None:
    acquired = await acquire_lock(tmp_path)
    assert acquired is True

    lock_path = tmp_path / ".maverick" / "runs" / "reconcile.lock"
    assert lock_path.is_file()
    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())

    await release_lock(tmp_path)
    assert not lock_path.is_file()


@pytest.mark.asyncio
async def test_release_lock_missing_is_best_effort(tmp_path: Path) -> None:
    # Should not raise even though no lock was ever acquired.
    await release_lock(tmp_path)


@pytest.mark.asyncio
async def test_acquire_lock_reclaims_stale_lock(tmp_path: Path) -> None:
    lock_dir = tmp_path / ".maverick" / "runs"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "reconcile.lock"

    # Fork a genuinely short-lived subprocess and wait for it to exit so its
    # pid is guaranteed dead, then stamp the lockfile with that dead pid.
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = proc.pid
    proc.wait(timeout=5)

    lock_path.write_text(str(dead_pid), encoding="utf-8")

    acquired = await acquire_lock(tmp_path)

    assert acquired is True
    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


@pytest.mark.asyncio
async def test_acquire_lock_refuses_when_live_pid_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_dir = tmp_path / ".maverick" / "runs"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "reconcile.lock"
    lock_path.write_text("999999999", encoding="utf-8")

    def _fake_kill(pid: int, sig: int) -> None:
        # Simulate a live process: os.kill succeeds without raising.
        return None

    monkeypatch.setattr(os, "kill", _fake_kill)

    acquired = await acquire_lock(tmp_path)

    assert acquired is False
    # The lockfile must be untouched (still the "other" pid).
    assert lock_path.read_text(encoding="utf-8").strip() == "999999999"


@pytest.mark.asyncio
async def test_acquire_lock_treats_malformed_lockfile_as_stale(tmp_path: Path) -> None:
    lock_dir = tmp_path / ".maverick" / "runs"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "reconcile.lock"
    lock_path.write_text("not-a-pid", encoding="utf-8")

    acquired = await acquire_lock(tmp_path)

    assert acquired is True
    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())
