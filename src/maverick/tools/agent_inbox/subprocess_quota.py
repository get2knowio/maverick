"""Global cap on live ACP agent subprocesses across an actor pool.

Today every agentic actor (briefing, decomposer, implementer-per-tier,
reviewer, generator, …) owns its own ``claude-agent-acp`` / ``opencode
acp`` / ``copilot --acp`` subprocess for the lifetime of the actor.
With Phase 2a tier routing live, a single fly run can spawn 4
implementer subprocesses (one per defined tier) on top of all the other
agentic actors. On a small host that adds up.

:class:`SubprocessQuota` enforces a single global ceiling
(``parallel.max_agents``) on total live ACP subprocesses across one
workflow run. Each :class:`AcpStepExecutor` calls
:meth:`SubprocessQuota.acquire` immediately before its
:class:`ConnectionPool` spawns a fresh subprocess, and
:meth:`SubprocessQuota.release` from its ``cleanup()``.

When ``acquire()`` would exceed the cap, the quota picks the LRU
*idle* (``busy_count == 0``) lease and invokes its ``evict_cb``. The
evicted actor's executor closes its subprocess pool and clears its
session state; the actor re-spawns lazily next time it needs to
prompt (~200ms ACP handshake). Mid-prompt actors (``busy_count > 0``)
are shielded — they cannot be evicted.

If every lease is mid-prompt, ``acquire()`` blocks on a future until a
release wakes it. This is rare: the typical workflow has many more
between-prompt moments than concurrent prompts.

Eviction tradeoff: any conversation context held in the evicted ACP
session is lost. Maverick's actor protocol already drives correctness
from supervisor-held state (each prompt re-states the failure context,
the bead spec, etc.), so this is a quality-not-correctness cost. Actors
that need ACP-session persistence across many prompts should re-state
context at every turn anyway.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Final

from maverick.logging import get_logger

__all__ = ["SubprocessQuota"]

logger = get_logger(__name__)


EvictCallback = Callable[[], Awaitable[None]]


@dataclass
class _Lease:
    """A live subprocess slot held by one executor."""

    uid: str
    evict_cb: EvictCallback
    last_activity: float
    busy_count: int = 0
    # Set when the quota begins evicting this lease. Concurrent
    # ``acquire`` callers skip leases that are mid-eviction.
    evicting: bool = False


# Sentinel return for ``_pick_victim_locked`` when no idle lease exists.
_NO_VICTIM: Final[None] = None


class SubprocessQuota:
    """Bounded acquire/release with LRU eviction for live ACP subprocesses.

    Instances are pool-scoped: one per :class:`AgentToolGateway` (which is
    one per workflow-run actor pool). Thread-safety is single-event-loop
    only — a single ``asyncio.Lock`` serializes lease-table mutations.

    Args:
        max_subprocesses: Hard cap on simultaneously held leases. Must be
            ``>= 1``.

    Notes:
        ``acquire`` is reentrant per uid: a second ``acquire`` from the
        same uid bumps activity and returns immediately without
        consuming an extra slot. Executors can therefore call
        ``acquire`` defensively before each spawn without bookkeeping.
    """

    def __init__(self, max_subprocesses: int) -> None:
        if max_subprocesses < 1:
            raise ValueError(f"max_subprocesses must be >= 1, got {max_subprocesses!r}")
        self._max = max_subprocesses
        self._lock = asyncio.Lock()
        # Insertion-order dict: append on acquire, move-to-end on activity.
        # Iteration from head gives LRU first.
        self._leases: OrderedDict[str, _Lease] = OrderedDict()
        # Waiters that arrived when every lease was busy. Each future is
        # resolved by the next release / eviction.
        self._waiters: deque[asyncio.Future[None]] = deque()

    @property
    def max_subprocesses(self) -> int:
        return self._max

    def held_uids(self) -> list[str]:
        """Snapshot of currently leased uids (oldest-first)."""
        return list(self._leases)

    async def acquire(self, uid: str, evict_cb: EvictCallback) -> None:
        """Acquire a subprocess slot for ``uid``.

        If ``uid`` already holds a slot, this just bumps activity and
        returns — safe to call defensively.

        If the cap is full, picks the LRU idle (``busy_count == 0``)
        lease and awaits its ``evict_cb``. If every lease is busy,
        blocks on a future until a release wakes it, then retries.
        """
        while True:
            victim: _Lease | None = None
            wait_future: asyncio.Future[None] | None = None
            async with self._lock:
                # Reentrant acquire — already held.
                existing = self._leases.get(uid)
                if existing is not None:
                    existing.last_activity = time.monotonic()
                    self._leases.move_to_end(uid)
                    return
                # Free slot — register and return.
                if len(self._leases) < self._max:
                    self._leases[uid] = _Lease(
                        uid=uid,
                        evict_cb=evict_cb,
                        last_activity=time.monotonic(),
                    )
                    logger.debug(
                        "subprocess_quota.acquired",
                        uid=uid,
                        held=len(self._leases),
                        cap=self._max,
                    )
                    return
                # Full — try to evict an idle lease.
                victim = self._pick_victim_locked()
                if victim is None:
                    # All leases busy — block on a future, retry.
                    wait_future = asyncio.get_running_loop().create_future()
                    self._waiters.append(wait_future)
                else:
                    victim.evicting = True
            if victim is not None:
                await self._do_evict(victim, requested_by=uid)
                continue
            assert wait_future is not None
            logger.debug(
                "subprocess_quota.queued",
                uid=uid,
                held=len(self._leases),
                cap=self._max,
            )
            await wait_future
            # A slot may have freed; loop and re-attempt.

    def _pick_victim_locked(self) -> _Lease | None:
        """Return the LRU idle lease, or ``None`` when every lease is busy.

        Caller MUST hold ``self._lock``. The returned lease has not yet
        been popped — caller flips ``evicting=True`` and pops outside
        the lock.
        """
        for lease in self._leases.values():
            if lease.busy_count == 0 and not lease.evicting:
                return lease
        return _NO_VICTIM

    async def _do_evict(self, lease: _Lease, *, requested_by: str) -> None:
        """Pop ``lease`` and invoke its evict callback."""
        # Pop first so the slot is logically free during the callback.
        # The callback typically calls back into ``release()`` (no-op
        # because the lease is already gone) — that idempotency matters.
        async with self._lock:
            self._leases.pop(lease.uid, None)
            logger.info(
                "subprocess_quota.evicting",
                victim=lease.uid,
                requested_by=requested_by,
                held=len(self._leases),
                cap=self._max,
            )
        try:
            await lease.evict_cb()
        except Exception as exc:  # noqa: BLE001 — eviction must not crash quota
            logger.warning(
                "subprocess_quota.evict_callback_failed",
                victim=lease.uid,
                error=str(exc),
            )
        # Wake at most one waiter — the slot just freed up.
        async with self._lock:
            self._wake_one_waiter_locked()

    def _wake_one_waiter_locked(self) -> None:
        """Pop the head waiter and resolve it. Skips already-cancelled futures."""
        while self._waiters:
            future = self._waiters.popleft()
            if not future.done():
                future.set_result(None)
                return

    async def release(self, uid: str) -> None:
        """Release the slot held by ``uid``. No-op if not held.

        Idempotent: callers that aren't sure whether the lease was
        already evicted can safely call ``release`` anyway.
        """
        async with self._lock:
            if self._leases.pop(uid, None) is None:
                return
            logger.debug(
                "subprocess_quota.released",
                uid=uid,
                held=len(self._leases),
                cap=self._max,
            )
            self._wake_one_waiter_locked()

    async def mark_busy(self, uid: str) -> None:
        """Increment ``uid``'s in-prompt count, shielding it from eviction."""
        async with self._lock:
            lease = self._leases.get(uid)
            if lease is None:
                return
            lease.busy_count += 1
            lease.last_activity = time.monotonic()
            self._leases.move_to_end(uid)

    async def mark_idle(self, uid: str) -> None:
        """Decrement ``uid``'s in-prompt count.

        When it reaches zero, the lease becomes a candidate for
        eviction. Wakes one waiter (if any) so a queued acquire can
        retry — the waiter blocked because every lease was busy, but
        this lease just became evictable.
        """
        async with self._lock:
            lease = self._leases.get(uid)
            if lease is None:
                return
            became_idle = False
            if lease.busy_count > 0:
                lease.busy_count -= 1
                became_idle = lease.busy_count == 0
            lease.last_activity = time.monotonic()
            # Don't move-to-end on idle — staying at the head means a
            # newly idle lease is the next eviction candidate, which is
            # the correct LRU semantic.
            if became_idle:
                self._wake_one_waiter_locked()

    @dataclass(frozen=True)
    class Snapshot:
        """Read-only view of the quota state — handy for tests + logs."""

        max_subprocesses: int
        held: int
        waiters: int
        leases: tuple[tuple[str, int], ...] = field(default_factory=tuple)
        """Tuple of ``(uid, busy_count)`` in LRU order."""

    def snapshot(self) -> SubprocessQuota.Snapshot:
        """Return a frozen view of the quota state for diagnostics."""
        return SubprocessQuota.Snapshot(
            max_subprocesses=self._max,
            held=len(self._leases),
            waiters=len(self._waiters),
            leases=tuple((u, lease.busy_count) for u, lease in self._leases.items()),
        )
