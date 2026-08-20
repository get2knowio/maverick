"""Unit tests for the bd-stays-out boundary guard (057-isolated-bead-workspaces,
User Story 4).

Contract C6 (specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md):
`assert_checkout` raises `IsolationBoundaryError` when a candidate path
resolves inside any *live* workspace root — resolved against the session's
actual live workspace roots (a runtime registry), never a path-shape
heuristic. This is layer 2 of research.md R9's three-layer enforcement:
type-level (`CheckoutPath`), this runtime guard, and a repository-wide test
(`test_call_sites.py`, T081).

A real `jj` repository isn't needed to exercise the registry itself — the
`JjClient` is mocked (this is a *unit* test, no subprocess), matching the
`tests/unit/jj/` mocking convention.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.exceptions import IsolationBoundaryError
from maverick.jj.client import JjClient
from maverick.workspace import IsolationPolicy, IsolationSession, UnitOfWork, assert_checkout


def _fixed_now() -> datetime:
    return datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _mock_jj_client(cwd: Path) -> AsyncMock:
    client = AsyncMock(spec=JjClient)
    client.cwd = cwd
    return client


def _make_session(checkout: Path, home: Path, *, run_id: str = "run-1") -> IsolationSession:
    return IsolationSession(
        checkout=checkout,  # type: ignore[arg-type]
        policy=IsolationPolicy(workflow="test-workflow", root=home),
        jj_client=_mock_jj_client(checkout),
        run_id=run_id,
        now=_fixed_now,
        home=home,
    )


class TestAssertCheckoutPassesForTheCheckout:
    def test_checkout_path_itself_passes(self, tmp_path: Path) -> None:
        checkout = tmp_path / "repo"
        checkout.mkdir()
        assert_checkout(checkout)  # must not raise

    def test_a_path_inside_the_checkout_but_outside_any_workspace_passes(
        self, tmp_path: Path
    ) -> None:
        checkout = tmp_path / "repo"
        (checkout / "src").mkdir(parents=True)
        assert_checkout(checkout / "src" / "file.py")  # must not raise

    def test_no_live_workspace_means_nothing_is_ever_rejected(self, tmp_path: Path) -> None:
        # Regression guard for the "path-shape heuristic" alternative the
        # contract explicitly rejects: a path that merely *looks* like it
        # could be a workspace (e.g. lives under a directory named
        # "workspaces") must not be rejected unless a session actually has
        # a *live* lease there.
        suspicious = tmp_path / ".maverick" / "workspaces" / "proj" / "fly" / "bd-1"
        suspicious.mkdir(parents=True)
        assert_checkout(suspicious)  # must not raise -- no live session/lease


class TestLeaseExposesOnlyWorkspacePathToAgents:
    """FR-023: an agent executing under a lease receives only the
    workspace path, never the checkout path.

    `IsolationLease` necessarily carries both (`fold_back`/`undo` need the
    checkout internally), so the guarantee isn't "the checkout is
    inaccessible" — it's that `workspace_path` and `checkout` are
    distinct, unambiguous fields, and the one a caller building an agent's
    working directory must reach for is `workspace_path`. Combined with
    `assert_checkout` rejecting `workspace_path` (above) and `CheckoutPath`
    rejecting a workspace path at the type level (T084), a consumer that
    mixed the two up would fail loudly at authoring time, at runtime, or
    both — never silently.
    """

    @pytest.mark.asyncio
    async def test_workspace_path_and_checkout_are_distinct_values(self, tmp_path: Path) -> None:
        checkout = tmp_path / "repo"
        checkout.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        session = _make_session(checkout, home)

        async with session:
            async with session.lease(UnitOfWork(key="bd-4", label="Agent step")) as lease:
                agent_cwd = lease.workspace_path  # what a real consumer hands the agent
                assert agent_cwd != Path(lease.checkout)
                assert not Path(agent_cwd).is_relative_to(Path(lease.checkout).resolve())


class TestAssertCheckoutRejectsLiveWorkspacePaths:
    @pytest.mark.asyncio
    async def test_rejects_a_path_inside_a_live_lease_workspace(self, tmp_path: Path) -> None:
        checkout = tmp_path / "repo"
        checkout.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        session = _make_session(checkout, home)

        async with session:
            async with session.lease(UnitOfWork(key="bd-1", label="Implement auth")) as lease:
                with pytest.raises(IsolationBoundaryError) as excinfo:
                    assert_checkout(lease.workspace_path)
                assert excinfo.value.path == str(Path(lease.workspace_path).resolve())
                assert excinfo.value.workspace_root == str(Path(lease.workspace_path).resolve())

    @pytest.mark.asyncio
    async def test_rejects_a_path_nested_under_a_live_workspace(self, tmp_path: Path) -> None:
        checkout = tmp_path / "repo"
        checkout.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        session = _make_session(checkout, home)

        async with session:
            async with session.lease(UnitOfWork(key="bd-2", label="Fix bug")) as lease:
                nested = lease.workspace_path / ".beads" / "store.db"
                with pytest.raises(IsolationBoundaryError):
                    assert_checkout(nested)

    @pytest.mark.asyncio
    async def test_allows_the_workspace_path_again_once_the_lease_exits(
        self, tmp_path: Path
    ) -> None:
        checkout = tmp_path / "repo"
        checkout.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        session = _make_session(checkout, home)

        async with session:
            async with session.lease(UnitOfWork(key="bd-3", label="Add tests")) as lease:
                workspace_path = lease.workspace_path
                with pytest.raises(IsolationBoundaryError):
                    assert_checkout(workspace_path)

            # The lease has exited (torn down) -- the path is no longer a
            # live workspace root, so the guard has nothing to reject.
            assert_checkout(workspace_path)  # must not raise

    @pytest.mark.asyncio
    async def test_two_concurrent_sessions_each_reject_their_own_workspace(
        self, tmp_path: Path
    ) -> None:
        """The registry is process-global (not per-session), since bd/
        ledger entry points have no session reference to consult -- a live
        lease from *any* session must be rejected."""
        checkout_a = tmp_path / "repo-a"
        checkout_a.mkdir()
        checkout_b = tmp_path / "repo-b"
        checkout_b.mkdir()
        home = tmp_path / "home"
        home.mkdir()
        session_a = _make_session(checkout_a, home, run_id="run-a")
        session_b = _make_session(checkout_b, home, run_id="run-b")

        async with session_a, session_b:
            async with (
                session_a.lease(UnitOfWork(key="bd-a", label="A")) as lease_a,
                session_b.lease(UnitOfWork(key="bd-b", label="B")) as lease_b,
            ):
                with pytest.raises(IsolationBoundaryError):
                    assert_checkout(lease_a.workspace_path)
                with pytest.raises(IsolationBoundaryError):
                    assert_checkout(lease_b.workspace_path)
                # Each checkout remains valid against the *other* session's
                # boundary guard -- a checkout is never itself a live
                # workspace root.
                assert_checkout(checkout_a)
                assert_checkout(checkout_b)
