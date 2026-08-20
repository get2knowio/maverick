"""Contract tests for `IsolationSession.lease()` provisioning.

Covers tasks.md T018/T019/T020/T028 — the provisioning slice of
specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md's
contract C3 ("`lease()` provisions before the agent runs"):

- T018 -> contract T1's prerequisite (FR-002): the workspace lands at
  `root/<project>/<workflow>/<key>/`, and two units never share a
  directory.
- T019 -> contract T2 (FR-003): the workspace sees the checkout's
  uncommitted work at provision time (`jj workspace add -r @` semantics).
- T020 (FR-004): `seed_inputs` files that never entered committed history
  are readable inside the workspace.
- T028 (FR-001 edge case): a provisioning failure raises
  `IsolationProvisioningError` before any agent runs, with a message that
  distinguishes "could not isolate" from "the work failed".

None of `src/maverick/workspace/{session,models}.py`'s isolation-primitive
surface exists yet at the time this file is written (TDD red phase) — every
test here is expected to fail on import (`ImportError`/`ModuleNotFoundError`)
until a later phase implements `maverick.workspace.IsolationSession` and
friends. That failure mode is the point, not a bug in this file.

Lock acquisition/journal recovery (contract C1/C2) are out of scope for this
slice — Phase 4 wires `__aenter__`/`__aexit__` to the run lock. Tests here
still use `async with session:` because that is the intended calling
convention every consumer follows, even though this phase's `lease()` only
needs the provisioning behavior underneath it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.exceptions import IsolationProvisioningError
from maverick.jj.client import JjClient
from maverick.workspace import IsolationPolicy, IsolationSession, UnitOfWork

pytestmark = pytest.mark.integration


def _fixed_now() -> datetime:
    """A deterministic clock — the primitive never calls `datetime.now()`
    directly (054's clock-seam convention, reused here for `IsolationLease
    .created_at`)."""
    return datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _policy(*, root: Path, workflow: str = "test-workflow") -> IsolationPolicy:
    return IsolationPolicy(workflow=workflow, root=root)


async def test_provision_creates_workspace_at_root_project_workflow_key(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """T018: provisioning lands at `root/<project>/<workflow>/<key>/`, and
    two distinct units never end up sharing a directory (contract T1's
    prerequisite, FR-002)."""
    checkout = colocated_repo.cwd
    policy = _policy(root=isolation_home)
    session = IsolationSession(
        checkout=checkout,
        policy=policy,
        jj_client=colocated_repo,
        run_id="run-t018",
        now=_fixed_now,
        home=isolation_home,
    )

    unit_a = UnitOfWork(key="bd-1", label="First bead")
    unit_b = UnitOfWork(key="bd-2", label="Second bead")

    expected_root = isolation_home / checkout.name / policy.workflow

    async with session:
        async with session.lease(unit_a) as lease_a:
            assert lease_a.workspace_path == expected_root / "bd-1"
            assert lease_a.workspace_path.is_dir()

        async with session.lease(unit_b) as lease_b:
            assert lease_b.workspace_path == expected_root / "bd-2"
            assert lease_b.workspace_path.is_dir()

    # Two units, two distinct directories -- never the same path.
    assert (expected_root / "bd-1") != (expected_root / "bd-2")


async def test_provision_sees_uncommitted_checkout_work(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """T019: `jj workspace add -r @` roots the new workspace's working-copy
    commit as a child of the checkout's `@`, so uncommitted work in the
    checkout is visible inside the workspace at provision time (contract
    T2, FR-003) -- without the caller doing anything special."""
    checkout = colocated_repo.cwd

    # Uncommitted work: written to disk, never `jj commit`-ed.
    wip_content = "work in progress, not yet committed\n"
    (checkout / "wip.txt").write_text(wip_content, encoding="utf-8")

    policy = _policy(root=isolation_home)
    session = IsolationSession(
        checkout=checkout,
        policy=policy,
        jj_client=colocated_repo,
        run_id="run-t019",
        now=_fixed_now,
        home=isolation_home,
    )
    unit = UnitOfWork(key="bd-1", label="Sees uncommitted work")

    async with session, session.lease(unit) as lease:
        seen_path = lease.workspace_path / "wip.txt"
        assert seen_path.exists(), (
            "the workspace should see the checkout's uncommitted wip.txt "
            "(jj workspace add -r @ makes the new working-copy commit a "
            "child of @)"
        )
        assert seen_path.read_text(encoding="utf-8") == wip_content


async def test_seed_inputs_readable_inside_workspace(
    colocated_repo: JjClient, isolation_home: Path, tmp_path: Path
) -> None:
    """T020: `seed_inputs` files that are absent from committed history
    (e.g. a PRD staged outside the repo entirely) are copied into the
    workspace and readable there (FR-004).

    NOTE for the implementer: this test deliberately does not assert an
    exact destination path/filename beyond the source file's basename --
    spec_chain.py's precedent (`_workspace_dir`'s sibling, the chain's PRD
    copy) places seeded files under an `inputs/` subdirectory of the
    workspace, but that exact layout isn't part of the public contract
    here. If the implementation lands seeded files somewhere else, update
    the search below rather than hardcoding a subdir.
    """
    checkout = colocated_repo.cwd

    # A file that exists on disk but was never part of the checkout or its
    # committed history -- e.g. a PRD living outside the repo.
    seed_content = "PRD: build the isolated workspace primitive.\n"
    seed_file = tmp_path / "external-inputs" / "prd.md"
    seed_file.parent.mkdir(parents=True)
    seed_file.write_text(seed_content, encoding="utf-8")

    policy = _policy(root=isolation_home)
    session = IsolationSession(
        checkout=checkout,
        policy=policy,
        jj_client=colocated_repo,
        run_id="run-t020",
        now=_fixed_now,
        home=isolation_home,
    )
    unit = UnitOfWork(key="bd-1", label="Seeded unit", seed_inputs=(seed_file,))

    async with session, session.lease(unit) as lease:
        candidates = list(lease.workspace_path.rglob(seed_file.name))
        assert candidates, (
            f"expected a copy of {seed_file.name!r} to be readable somewhere "
            f"under {lease.workspace_path} (spec_chain.py's precedent puts "
            "seeded files under an inputs/ subdir)"
        )
        assert any(c.read_text(encoding="utf-8") == seed_content for c in candidates)


async def test_provisioning_failure_raises_before_any_agent_runs(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """T028: when provisioning cannot create the workspace directory, the
    session raises `IsolationProvisioningError` before the lease body ever
    executes -- the caller never gets a chance to hand a workspace path to
    an agent, and the error message must read as a provisioning problem,
    not a work-outcome problem (FR-001 edge case).
    """
    checkout = colocated_repo.cwd
    policy = _policy(root=isolation_home)

    # Force `mkdir` to fail: plant a plain FILE at the exact path the
    # workspace directory needs to occupy (root/<project>/<workflow>/),
    # so creating `.../<workflow>/<key>/` underneath it is impossible.
    blocking_path = isolation_home / checkout.name / policy.workflow
    blocking_path.parent.mkdir(parents=True, exist_ok=True)
    blocking_path.write_text("not a directory\n", encoding="utf-8")

    session = IsolationSession(
        checkout=checkout,
        policy=policy,
        jj_client=colocated_repo,
        run_id="run-t028",
        now=_fixed_now,
        home=isolation_home,
    )
    unit = UnitOfWork(key="bd-1", label="Doomed unit")

    agent_ran = False

    with pytest.raises(IsolationProvisioningError) as excinfo:
        async with session, session.lease(unit) as lease:
            # If provisioning genuinely failed before the agent runs, this
            # body must never execute.
            agent_ran = True
            _ = lease

    assert not agent_ran, (
        "the lease body ran despite provisioning failing -- "
        "IsolationProvisioningError must be raised before any agent runs"
    )

    message = str(excinfo.value).lower()
    # The message must read as a provisioning problem ("could not isolate"),
    # not a work-outcome problem ("the work failed") -- callers upstream
    # rely on this distinction to avoid conflating the two failure modes.
    assert "isolat" in message or "provision" in message or "workspace" in message
    assert "review failed" not in message
    assert "implementation failed" not in message
