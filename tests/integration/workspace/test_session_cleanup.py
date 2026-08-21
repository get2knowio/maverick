"""A run that halts mid-unit must not leave the guard armed or the
workspace behind.

`IsolationSession.lease()` registers and releases in one `finally`, so it
is symmetric by construction. Fly cannot use it: its Burr actions are
independently-invoked functions, and a bead's span runs
`provision_workspace -> ... -> record_outcome` with no shared lexical
scope, so registration and release sit in two different call sites with
nothing bridging them. Any action raising in between means `record_outcome`
never runs.

The session's `__aexit__` is the one place with a real `finally` spanning
the whole run, so that is where the symmetry is restored (finding 1 of the
057 review follow-ups).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.exceptions import IsolationBoundaryError
from maverick.jj.client import JjClient
from maverick.workspace import IsolationPolicy, IsolationSession, UnitOfWork, assert_checkout
from maverick.workspace import lifecycle as workspace_lifecycle


def _now() -> datetime:
    return datetime(2026, 8, 21, 12, 0, 0, tzinfo=UTC)


def _session(checkout: Path, home: Path, *, retain_on_failure: bool = False) -> IsolationSession:
    return IsolationSession(
        checkout=checkout,
        policy=IsolationPolicy(
            workflow="fly", root=home, reuse=False, retain_on_failure=retain_on_failure
        ),
        jj_client=JjClient(cwd=checkout),
        run_id="run-1",
        now=_now,
        home=home,
    )


async def _provision_without_releasing(
    session: IsolationSession, checkout: Path, key: str
) -> Path:
    """Exactly what fly's `provision_workspace` action does, with the
    matching `teardown_workspace` never reached."""
    unit = UnitOfWork(key=key, label=key)
    path = await workspace_lifecycle.provision(
        checkout=checkout,
        policy=session._policy,
        unit=unit,
        jj_client=session._jj_client,
    )
    session.register_unit(unit, path)
    return path


class TestHaltedRunCleansUp:
    @pytest.mark.asyncio
    async def test_workspace_is_torn_down_when_the_run_halts_mid_unit(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        checkout = colocated_repo.cwd
        session = _session(checkout, isolation_home)

        async with session:
            path = await _provision_without_releasing(session, checkout, "bd-halted")
            assert path.exists()

        assert not path.exists()

    @pytest.mark.asyncio
    async def test_guard_disarms_so_a_stale_root_stops_being_rejected(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        checkout = colocated_repo.cwd
        session = _session(checkout, isolation_home)

        async with session:
            path = await _provision_without_releasing(session, checkout, "bd-halted")
            # While live, the guard rejects anything inside it.
            with pytest.raises(IsolationBoundaryError):
                assert_checkout(path / "nested")

        # Once the run is over, the entry is gone from the process-global
        # registry — no stale root outlives the session that made it.
        assert_checkout(path / "nested")

    @pytest.mark.asyncio
    async def test_an_exception_propagates_and_cleanup_still_runs(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """Cleanup must not swallow the failure that caused the halt."""
        checkout = colocated_repo.cwd
        session = _session(checkout, isolation_home)
        path: Path | None = None

        with pytest.raises(RuntimeError, match="bead exploded"):
            async with session:
                path = await _provision_without_releasing(session, checkout, "bd-boom")
                raise RuntimeError("bead exploded")

        assert path is not None
        assert not path.exists()
        assert_checkout(path)

    @pytest.mark.asyncio
    async def test_retain_on_failure_keeps_the_workspace_for_inspection(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """spec-chain's policy — a halted step's workspace is the only copy
        of its partial output, so cleanup must retain rather than delete."""
        checkout = colocated_repo.cwd
        session = _session(checkout, isolation_home, retain_on_failure=True)
        path: Path | None = None

        with pytest.raises(RuntimeError):
            async with session:
                path = await _provision_without_releasing(session, checkout, "bd-retained")
                raise RuntimeError("step failed")

        assert path is not None
        assert path.exists()
        # Still disarmed even though the directory survives.
        assert_checkout(path)

    @pytest.mark.asyncio
    async def test_a_released_unit_is_not_cleaned_up_twice(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """The happy path already tore down in `teardown_workspace`;
        `__aexit__` must find nothing left to do."""
        checkout = colocated_repo.cwd
        session = _session(checkout, isolation_home)

        async with session:
            path = await _provision_without_releasing(session, checkout, "bd-normal")
            session.release_unit(path)
            await workspace_lifecycle.teardown(
                checkout=checkout,
                policy=session._policy,
                unit=UnitOfWork(key="bd-normal", label="bd-normal"),
                jj_client=session._jj_client,
            )

        assert not path.exists()

    @pytest.mark.asyncio
    async def test_lease_leaves_nothing_for_aexit_to_clean(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """The symmetric path stays symmetric — no double teardown."""
        checkout = colocated_repo.cwd
        session = _session(checkout, isolation_home)

        async with session:
            async with session.lease(UnitOfWork(key="bd-leased", label="leased")) as lease:
                (lease.workspace_path / "f.txt").write_text("x\n", encoding="utf-8")
                await session.fold_back(lease)
            assert session._live_units == {}

        assert not lease.workspace_path.exists()
