"""Integration tests for workspace teardown and sweep against a real,
throwaway jj-colocated checkout.

Contract: specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md
C7, and the contract-test table T16/T17. Covers tasks.md T085-T089
(User Story 5 — isolation never accumulates garbage).

Verified by hand against real jj 0.44 before writing these assertions:
`jj workspace forget <name>` removes that workspace's fresh empty
working-copy commit from `jj log -r 'all()'` entirely; skipping it before
`rmtree` leaves that commit as a permanent anonymous head forever, visible
in `jj log` even though its directory is long gone (research.md R7/T16).
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.jj.client import JjClient
from maverick.workspace import IsolationPolicy, IsolationSession, UnitOfWork
from maverick.workspace import lifecycle as workspace_lifecycle


def _fixed_now() -> datetime:
    return datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _policy(*, root: Path, workflow: str = "fly") -> IsolationPolicy:
    return IsolationPolicy(workflow=workflow, root=root, reuse=False, retain_on_failure=False)


def _make_session(checkout: Path, home: Path, *, run_id: str = "run-1") -> IsolationSession:
    return IsolationSession(
        checkout=checkout,
        policy=_policy(root=home),
        jj_client=JjClient(cwd=checkout),
        run_id=run_id,
        now=_fixed_now,
        home=home,
    )


def _unit(key: str, label: str) -> UnitOfWork:
    return UnitOfWork(key=key, label=label)


def _workspace_names(checkout: Path) -> set[str]:
    result = subprocess.run(
        ["jj", "workspace", "list"], cwd=checkout, check=True, capture_output=True, text=True
    )
    names = set()
    for line in result.stdout.splitlines():
        if ":" in line:
            names.add(line.split(":", 1)[0].strip())
    return names


def _change_count(checkout: Path) -> int:
    result = subprocess.run(
        ["jj", "log", "-r", "all()", "--no-graph", "-T", 'change_id ++ "\\n"'],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _run(cmd: list[str], *, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _build_repo(path: Path) -> Path:
    """A second, independently-named colocated repo (for T088's
    cross-checkout isolation test — the shared `colocated_repo` fixture is
    always named "repo", so a second checkout under the same isolation
    root needs its own distinct name to avoid a path collision)."""
    path.mkdir()
    _run(["git", "init", "-q"], cwd=path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=path)
    _run(["git", "config", "user.name", "Test"], cwd=path)
    _run(["jj", "git", "init", "--colocate"], cwd=path)
    (path / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _run(["jj", "commit", "-m", "initial checkout"], cwd=path)
    return path


class TestSuccessfulTeardown:
    @pytest.mark.asyncio
    async def test_successful_units_workspace_is_torn_down_and_unregistered(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """T085/FR-024: a successful unit's workspace is torn down and no
        longer jj-registered."""
        checkout = colocated_repo.cwd
        session = _make_session(checkout, isolation_home)

        async with session:
            async with session.lease(_unit("bd-1", "T085 unit")) as lease:
                (lease.workspace_path / "new.txt").write_text("hello\n", encoding="utf-8")
                result = await session.fold_back(lease)
                workspace_path = lease.workspace_path
            assert not workspace_path.exists()

        assert _workspace_names(checkout) == {"default"}
        assert result.applied_paths  # sanity: the fold-back actually happened

    @pytest.mark.asyncio
    async def test_forget_precedes_removal_no_stray_head_in_jj_log(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """T086/contract T16/FR-029: `workspace_forget` precedes `rmtree`,
        so no stray anonymous head is left in the user's `jj log`."""
        checkout = colocated_repo.cwd
        baseline_count = _change_count(checkout)

        session = _make_session(checkout, isolation_home)
        async with session:
            async with session.lease(_unit("bd-2", "T086 unit")) as lease:
                (lease.workspace_path / "new.txt").write_text("hello\n", encoding="utf-8")
                await session.fold_back(lease)

        # If `workspace_forget` were skipped (or run after `rmtree`), the
        # workspace's abandoned empty working-copy commit would remain as
        # a permanent extra change here.
        assert _change_count(checkout) == baseline_count


class TestSweepCollectsAbandonedWorkspaces:
    @pytest.mark.asyncio
    async def test_sweep_preserves_keep_and_removes_the_rest(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """T087/contract T17/FR-025,026: sweep collects abandoned
        workspaces, preserving `keep` entries."""
        checkout = colocated_repo.cwd
        policy = _policy(root=isolation_home)
        jj_client = JjClient(cwd=checkout)

        # Simulate three units abandoned by interrupted prior runs: they
        # were provisioned but never torn down (no fold_back, no lease
        # exit) -- exactly what a Ctrl-C mid-bead leaves behind.
        abandoned_paths = {}
        for key in ("bd-abandon-1", "bd-abandon-2", "bd-keep"):
            path = await workspace_lifecycle.provision(
                checkout=checkout, policy=policy, unit=_unit(key, key), jj_client=jj_client
            )
            abandoned_paths[key] = path
            assert path.exists()

        session = _make_session(checkout, isolation_home)
        async with session:
            await session.sweep(keep={"bd-keep"})

        assert not abandoned_paths["bd-abandon-1"].exists()
        assert not abandoned_paths["bd-abandon-2"].exists()
        assert abandoned_paths["bd-keep"].exists()
        assert _workspace_names(checkout) == {"default", "bd-keep"}

    @pytest.mark.asyncio
    async def test_one_undeletable_entry_does_not_strand_the_others(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """T087/contract T17/FR-027: one undeletable workspace must not
        strand every later one -- sweep is per-entry isolated."""
        checkout = colocated_repo.cwd
        policy = _policy(root=isolation_home)
        real_client = JjClient(cwd=checkout)

        class _FlakyForgetClient:
            """Delegates everything to the real client except
            `workspace_forget`, which fails for one specific name --
            simulating a workspace jj genuinely cannot forget (e.g. a
            concurrent jj operation holding a lock)."""

            def __init__(self, inner: JjClient, *, fails_for: str) -> None:
                self._inner = inner
                self._fails_for = fails_for

            async def workspace_forget(self, name: str) -> None:
                if name == self._fails_for:
                    from maverick.exceptions import JjError

                    raise JjError(f"simulated: cannot forget {name}")
                await self._inner.workspace_forget(name)

            def __getattr__(self, item: str) -> object:
                return getattr(self._inner, item)

        flaky_client = _FlakyForgetClient(real_client, fails_for="bd-stuck")

        paths = {}
        for key in ("bd-before", "bd-stuck", "bd-after"):
            path = await workspace_lifecycle.provision(
                checkout=checkout, policy=policy, unit=_unit(key, key), jj_client=real_client
            )
            paths[key] = path

        session = IsolationSession(
            checkout=checkout,
            policy=policy,
            jj_client=flaky_client,  # type: ignore[arg-type]
            run_id="run-flaky",
            now=_fixed_now,
            home=isolation_home,
        )
        async with session:
            await session.sweep(keep=set())  # must not raise despite the stuck entry

        # workspace_forget fails for bd-stuck, so teardown's own guard
        # (best-effort, never sinks a completed unit) leaves its directory
        # on disk -- but the *other two* must still be fully collected.
        assert not paths["bd-before"].exists()
        assert not paths["bd-after"].exists()


class TestSweepIsScopedToThisCheckout:
    @pytest.mark.asyncio
    async def test_sweep_never_touches_another_checkouts_workspace(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """T088/FR-026: sweep is scoped to this checkout's own workspace
        root -- another checkout's workspaces are not ours to collect."""
        checkout_a = colocated_repo.cwd
        checkout_b = _build_repo(checkout_a.parent / "repo-other")
        policy = _policy(root=isolation_home)

        path_a = await workspace_lifecycle.provision(
            checkout=checkout_a,
            policy=policy,
            unit=_unit("bd-a", "A"),
            jj_client=JjClient(cwd=checkout_a),
        )
        path_b = await workspace_lifecycle.provision(
            checkout=checkout_b,
            policy=policy,
            unit=_unit("bd-b", "B"),
            jj_client=JjClient(cwd=checkout_b),
        )
        assert path_a != path_b

        session_a = _make_session(checkout_a, isolation_home, run_id="run-a")
        async with session_a:
            await session_a.sweep(keep=set())  # sweeps checkout_a's root only

        assert not path_a.exists()
        assert path_b.exists()  # untouched -- belongs to a different checkout


class TestNoOrphansAcrossInterruptedRuns:
    @pytest.mark.asyncio
    async def test_repeated_interrupted_runs_leave_no_orphans(
        self, colocated_repo: JjClient, isolation_home: Path
    ) -> None:
        """T089/FR-028/SC-007: correctness must not depend on any
        workspace surviving -- even with every workspace externally
        deleted between runs, the next run still behaves correctly, and a
        sequence of interrupted runs leaves no orphans once swept."""
        checkout = colocated_repo.cwd
        policy = _policy(root=isolation_home)
        jj_client = JjClient(cwd=checkout)
        baseline_count = _change_count(checkout)

        # Three "interrupted runs": provision, then the user clears
        # ~/.maverick/workspaces by hand (directory gone, jj-side name
        # still registered) before the next run starts.
        for i in range(3):
            path = await workspace_lifecycle.provision(
                checkout=checkout,
                policy=policy,
                unit=_unit(f"bd-run-{i}", f"run {i}"),
                jj_client=jj_client,
            )
            assert path.exists()
            import shutil

            shutil.rmtree(path)  # simulate the user clearing the directory by hand

        # The jj-side registrations for all three still exist (only the
        # directories were cleared) -- the next run must still work.
        session = _make_session(checkout, isolation_home)
        async with session:
            await session.sweep(keep=set())

        assert _workspace_names(checkout) == {"default"}
        assert _change_count(checkout) == baseline_count

        # And a fresh unit can still be provisioned afterward without
        # colliding with any leftover jj-side state.
        async with session:
            async with session.lease(_unit("bd-final", "final")) as lease:
                (lease.workspace_path / "ok.txt").write_text("ok\n", encoding="utf-8")
                result = await session.fold_back(lease)
        assert result.applied_paths == ("ok.txt",)
