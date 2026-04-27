"""Unit tests for :class:`SubprocessQuota`.

The quota is the heart of FUTURE.md §2.10 Phase 2b: it bounds the total
live ACP subprocesses across an actor pool with LRU eviction of idle
actors. These tests cover the primitives directly with synthetic
``EvictCallback``s; an end-to-end fly run with a forced cap is the
acceptance check (run by hand against the sample project).
"""

from __future__ import annotations

import asyncio

import pytest

from maverick.tools.agent_inbox.subprocess_quota import SubprocessQuota

# ---------------------------------------------------------------------------
# Helpers — record-and-respond eviction callback factory.
# ---------------------------------------------------------------------------


def _evict_recorder(target: list[str], uid: str, quota: SubprocessQuota):
    """Build an evict_cb that records its uid and (typically) calls
    ``quota.release(uid)`` on its own behalf — matching the real
    executor's ``cleanup_for_eviction`` flow.

    By default the quota POPs the lease before invoking the callback,
    so a follow-up release is a no-op (idempotent). We still call it to
    mimic real-world behavior.
    """

    async def _cb() -> None:
        target.append(uid)
        await quota.release(uid)

    return _cb


# ---------------------------------------------------------------------------
# Construction.
# ---------------------------------------------------------------------------


def test_quota_rejects_non_positive_cap() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        SubprocessQuota(0)
    with pytest.raises(ValueError, match=">= 1"):
        SubprocessQuota(-1)


# ---------------------------------------------------------------------------
# Acquire/release basics.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_under_cap_does_not_block_or_evict() -> None:
    quota = SubprocessQuota(max_subprocesses=3)
    evictions: list[str] = []
    await quota.acquire("a", _evict_recorder(evictions, "a", quota))
    await quota.acquire("b", _evict_recorder(evictions, "b", quota))
    assert evictions == []
    snap = quota.snapshot()
    assert snap.held == 2
    assert snap.max_subprocesses == 3
    assert {uid for uid, _ in snap.leases} == {"a", "b"}


@pytest.mark.asyncio
async def test_reentrant_acquire_does_not_consume_extra_slot() -> None:
    quota = SubprocessQuota(max_subprocesses=2)
    evictions: list[str] = []
    await quota.acquire("a", _evict_recorder(evictions, "a", quota))
    # A second acquire by the same uid is idempotent.
    await quota.acquire("a", _evict_recorder(evictions, "a", quota))
    assert quota.snapshot().held == 1


@pytest.mark.asyncio
async def test_release_frees_slot() -> None:
    quota = SubprocessQuota(max_subprocesses=1)
    evictions: list[str] = []
    await quota.acquire("a", _evict_recorder(evictions, "a", quota))
    await quota.release("a")
    assert quota.snapshot().held == 0
    # After release we can acquire again with no eviction.
    await quota.acquire("b", _evict_recorder(evictions, "b", quota))
    assert evictions == []


@pytest.mark.asyncio
async def test_release_unknown_uid_is_noop() -> None:
    quota = SubprocessQuota(max_subprocesses=2)
    await quota.release("never-acquired")  # must not raise
    assert quota.snapshot().held == 0


# ---------------------------------------------------------------------------
# LRU eviction selection.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_when_full_evicts_lru_idle() -> None:
    quota = SubprocessQuota(max_subprocesses=2)
    evictions: list[str] = []
    await quota.acquire("a", _evict_recorder(evictions, "a", quota))
    await quota.acquire("b", _evict_recorder(evictions, "b", quota))
    # Both idle; "a" is LRU (acquired first, no activity since).
    await quota.acquire("c", _evict_recorder(evictions, "c", quota))
    assert evictions == ["a"]
    held = {uid for uid, _ in quota.snapshot().leases}
    assert held == {"b", "c"}


@pytest.mark.asyncio
async def test_mark_busy_shields_from_eviction() -> None:
    """A mid-prompt actor (busy_count > 0) MUST NOT be evicted; the
    quota must walk past it to find an idle victim."""
    quota = SubprocessQuota(max_subprocesses=2)
    evictions: list[str] = []
    await quota.acquire("busy", _evict_recorder(evictions, "busy", quota))
    await quota.acquire("idle", _evict_recorder(evictions, "idle", quota))
    await quota.mark_busy("busy")
    # "busy" is at the head (acquired first) but shielded; "idle" is
    # the only candidate.
    await quota.acquire("c", _evict_recorder(evictions, "c", quota))
    assert evictions == ["idle"]
    held = {uid for uid, _ in quota.snapshot().leases}
    assert held == {"busy", "c"}


@pytest.mark.asyncio
async def test_acquire_blocks_when_all_leases_busy() -> None:
    """When every lease is mid-prompt, acquire blocks until a release
    or mark_idle frees a slot. This is the rare-but-real path."""
    quota = SubprocessQuota(max_subprocesses=1)
    evictions: list[str] = []
    await quota.acquire("a", _evict_recorder(evictions, "a", quota))
    await quota.mark_busy("a")
    # Kick off an acquire that should block.
    acquire_task = asyncio.create_task(quota.acquire("b", _evict_recorder(evictions, "b", quota)))
    # Give the task a chance to enter the wait queue.
    await asyncio.sleep(0.05)
    assert not acquire_task.done()
    # Now release "a" — that wakes "b".
    await quota.release("a")
    await asyncio.wait_for(acquire_task, timeout=1.0)
    held = {uid for uid, _ in quota.snapshot().leases}
    assert held == {"b"}
    assert evictions == []


@pytest.mark.asyncio
async def test_eviction_invokes_callback_for_correct_victim() -> None:
    quota = SubprocessQuota(max_subprocesses=1)
    evictions: list[str] = []

    async def slow_evict_a() -> None:
        await asyncio.sleep(0.01)
        evictions.append("a")
        await quota.release("a")

    await quota.acquire("a", slow_evict_a)
    # "a" is idle; acquiring "b" forces eviction of "a".
    await quota.acquire("b", _evict_recorder(evictions, "b", quota))
    assert evictions == ["a"]
    held = {uid for uid, _ in quota.snapshot().leases}
    assert held == {"b"}


# ---------------------------------------------------------------------------
# mark_busy / mark_idle accounting.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_busy_idle_counts_balanced() -> None:
    """mark_busy/mark_idle nest correctly across multiple prompts."""
    quota = SubprocessQuota(max_subprocesses=1)
    evictions: list[str] = []
    await quota.acquire("a", _evict_recorder(evictions, "a", quota))
    await quota.mark_busy("a")
    await quota.mark_busy("a")
    await quota.mark_idle("a")
    # Still has 1 busy count — should still shield from eviction.
    acquire_task = asyncio.create_task(quota.acquire("b", _evict_recorder(evictions, "b", quota)))
    await asyncio.sleep(0.05)
    assert not acquire_task.done()
    await quota.mark_idle("a")
    # Now "a" is idle; "b" should evict it.
    await asyncio.wait_for(acquire_task, timeout=1.0)
    assert evictions == ["a"]


@pytest.mark.asyncio
async def test_mark_idle_below_zero_is_noop() -> None:
    """Spurious mark_idle calls (release/evict raced ahead) shouldn't crash."""
    quota = SubprocessQuota(max_subprocesses=2)
    evictions: list[str] = []
    await quota.acquire("a", _evict_recorder(evictions, "a", quota))
    await quota.mark_idle("a")  # already idle
    await quota.mark_idle("a")
    assert quota.snapshot().held == 1


@pytest.mark.asyncio
async def test_mark_busy_unknown_uid_is_noop() -> None:
    quota = SubprocessQuota(max_subprocesses=2)
    await quota.mark_busy("never-acquired")  # no error
    await quota.mark_idle("never-acquired")
    assert quota.snapshot().held == 0


# ---------------------------------------------------------------------------
# Concurrency stress: many parallel acquires under a tight cap.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_many_parallel_acquires_under_tight_cap() -> None:
    """Fan out 10 acquires over a cap of 2; eventually all should
    complete via a mix of eviction and queueing."""
    quota = SubprocessQuota(max_subprocesses=2)
    evictions: list[str] = []
    held_at_some_point: set[str] = set()

    async def hold_briefly(uid: str) -> None:
        await quota.acquire(uid, _evict_recorder(evictions, uid, quota))
        held_at_some_point.add(uid)
        # Don't hold busy — leave open to eviction so others can acquire.
        await asyncio.sleep(0.01)

    await asyncio.gather(*(hold_briefly(f"a{i}") for i in range(10)))
    assert held_at_some_point == {f"a{i}" for i in range(10)}
    # Every uid that wasn't the last to enter should have been evicted
    # at some point (or released voluntarily — either is fine).
    assert quota.snapshot().held <= 2


@pytest.mark.asyncio
async def test_snapshot_exposes_lru_order() -> None:
    quota = SubprocessQuota(max_subprocesses=3)
    for uid in ("a", "b", "c"):
        await quota.acquire(uid, _evict_recorder([], uid, quota))
    # Acquire-order is preserved.
    assert [uid for uid, _ in quota.snapshot().leases] == ["a", "b", "c"]
    # mark_busy bumps to end (most-recently-used).
    await quota.mark_busy("a")
    assert [uid for uid, _ in quota.snapshot().leases] == ["b", "c", "a"]
