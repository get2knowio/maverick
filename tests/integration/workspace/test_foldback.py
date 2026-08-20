"""Integration tests for `IsolationSession.fold_back()` against a real,
throwaway jj-colocated checkout.

Contract: `specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md`
(section "Behavioral contract" C4, and the contract-test table T1/T3-T7).
Mechanism: `specs/057-isolated-bead-workspaces/research.md` R2 (how a delta
moves from a workspace into the checkout via `jj squash --from '<name>@'
--into @ <filesets>`) and R3 (the snapshot chokepoint that makes fold-back
correct at all).

None of `src/maverick/workspace/` exists yet — these tests are written
against the intended public API (data-model.md + the contract above) and are
expected to fail at collection with `ImportError`/`ModuleNotFoundError`
until a later phase implements it. That failure is the "red" of this
feature's TDD red-green-refactor cycle.

Task IDs (tasks.md): T021-T026, T029.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.jj.client import JjClient
from maverick.workspace import (
    CheckoutPath,
    FoldBackOutcome,
    IsolationPolicy,
    IsolationSession,
    UnitOfWork,
)


def _make_session(
    colocated_repo: JjClient,
    isolation_home: Path,
    *,
    workflow: str = "fly",
) -> IsolationSession:
    """Build an `IsolationSession` bound to the fixture checkout.

    `policy.root` and the constructor's `home=` both point at the
    throwaway `isolation_home` fixture so nothing here ever touches a
    developer's real `~/.maverick/workspaces`.
    """
    policy = IsolationPolicy(
        workflow=workflow,
        root=isolation_home,
        reuse=True,
        retain_on_failure=False,
        fold_scope=(),
        fold_exclusions=(),
    )
    return IsolationSession(
        checkout=CheckoutPath(colocated_repo.cwd),
        policy=policy,
        jj_client=colocated_repo,
        run_id="test-run",
        now=lambda: datetime.now(UTC),
        home=isolation_home,
    )


def _unit(key: str, label: str) -> UnitOfWork:
    return UnitOfWork(key=key, label=label, seed_inputs=())


# ---------------------------------------------------------------------------
# T021 — contract T1: no changes visible in the checkout while a unit's
# agent step is running (FR-007, SC-002).
# ---------------------------------------------------------------------------


async def test_checkout_shows_no_changes_while_agent_step_runs(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """An agent write inside a leased workspace must not be observable in
    the checkout — on disk or in `jj status` — until `fold_back()` runs.

    This is SC-002's user-visible guarantee: a bystander watching the
    checkout during a bead's implement/review phase must never see a
    partially-implemented bead.
    """
    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-021", "T021 unit")

    async with session:
        async with session.lease(unit) as lease:
            (lease.workspace_path / "agent-output.txt").write_text(
                "mid-flight\n", encoding="utf-8"
            )

            # Not on disk in the checkout...
            assert not (colocated_repo.cwd / "agent-output.txt").exists()

            # ...and jj agrees the checkout has no changes at all.
            checkout_status = await JjClient(cwd=colocated_repo.cwd).status()
            assert "agent-output.txt" not in checkout_status.output
            assert "The working copy has no changes." in checkout_status.output


# ---------------------------------------------------------------------------
# T022 — contract T3: create + modify + delete all fold back in one
# application, and `applied_paths` lists exactly them (FR-005, FR-009).
# ---------------------------------------------------------------------------


async def test_create_modify_delete_fold_back_in_one_application(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """A single `fold_back()` call must move a create, a modify, and a
    delete together, and `applied_paths` must name exactly those three
    paths.

    Assumption for a later implementer to double-check: `applied_paths`
    entries are repo-relative POSIX-style strings with no leading `./`
    (e.g. `"tracked.txt"`, not `"/tracked.txt"` or `"./tracked.txt"`) —
    this matches data-model.md's `FoldBackResult.applied_paths` field
    description ("Repo-relative posix paths written to the checkout").
    """
    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-022", "T022 unit")

    async with session:
        async with session.lease(unit) as lease:
            (lease.workspace_path / "tracked.txt").write_text(
                "modified by the workspace\n", encoding="utf-8"
            )
            (lease.workspace_path / "README.md").unlink()
            (lease.workspace_path / "created.txt").write_text("brand new\n", encoding="utf-8")

            result = await session.fold_back(lease)

            assert result.outcome == FoldBackOutcome.APPLIED
            assert set(result.applied_paths) == {
                "tracked.txt",
                "README.md",
                "created.txt",
            }

            # Verified immediately, still inside the lease — fold-back's
            # effect on the checkout does not depend on teardown.
            assert (colocated_repo.cwd / "tracked.txt").read_text(
                encoding="utf-8"
            ) == "modified by the workspace\n"
            assert not (colocated_repo.cwd / "README.md").exists()
            assert (colocated_repo.cwd / "created.txt").read_text(
                encoding="utf-8"
            ) == "brand new\n"

    # And still true after the lease (and its teardown) has exited.
    assert (colocated_repo.cwd / "tracked.txt").read_text(
        encoding="utf-8"
    ) == "modified by the workspace\n"
    assert not (colocated_repo.cwd / "README.md").exists()
    assert (colocated_repo.cwd / "created.txt").read_text(encoding="utf-8") == "brand new\n"


# ---------------------------------------------------------------------------
# T023 — contract T4 / research.md R3: the single highest-value test in the
# feature. Fold-back must snapshot the workspace's working copy before the
# squash, or the fold-back silently moves nothing.
# ---------------------------------------------------------------------------


async def test_fold_back_snapshots_plain_file_writes_before_squash(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """R3 regression guard: writes made via plain file I/O (never a jj
    command bound to the workspace) must still fold back correctly.

    Mechanism (research.md R3, validated against real jj 0.44): jj
    auto-snapshots a workspace's working copy only on a jj command bound
    to *that* workspace. An agent step writes into `lease.workspace_path`
    using ordinary file I/O — it never runs `jj` there. If `foldback.py`
    ever squashes straight from the checkout (`jj squash --from
    '<name>@' --into @ ...`) without first forcing a snapshot inside the
    workspace, `'<name>@'` still points at the workspace's *stale*
    working-copy commit, and the squash "succeeds" while moving zero
    files — silently indistinguishable from a legitimate empty delta
    (FR-006's case, covered separately by
    `test_empty_delta_returns_empty_not_success`... see below).

    A black-box integration test against the public `IsolationSession`
    API cannot literally instruct the implementation to *skip* its own
    internal snapshot call — that call is exactly the fix, not something
    a caller controls. So this test proves the fix works the way the
    contract intends: it writes into the workspace using *only* plain
    file I/O (deliberately never touching a `JjClient` bound to
    `lease.workspace_path`), calls the public `fold_back()`, and asserts
    the write actually arrived in the checkout. If a future change to
    `foldback.py` ever drops the mandatory pre-squash snapshot (contract
    C4 step 1), this test fails — the outcome flips from `APPLIED` to
    the silent `EMPTY` this whole mechanism exists to prevent.
    """
    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-023", "T023 unit")

    async with session:
        async with session.lease(unit) as lease:
            # Deliberately plain file I/O only. No JjClient bound to
            # `lease.workspace_path` is constructed or invoked anywhere
            # in this test — that is the entire point of the regression
            # it guards against.
            (lease.workspace_path / "agent-write.txt").write_text(
                "written by plain file I/O, no jj command in the workspace\n",
                encoding="utf-8",
            )

            result = await session.fold_back(lease)

    assert result.outcome == FoldBackOutcome.APPLIED, (
        "fold_back() returned "
        f"{result.outcome!r} for a plain-file-I/O write instead of APPLIED. "
        "This is exactly the R3 silent-empty-fold-back failure mode: the "
        "workspace's working copy was never snapshotted before the squash, "
        "so jj had nothing to move from '<name>@'. See research.md R3 and "
        "contract T4 in isolation-primitive.md — the fix is a mandatory "
        "pre-squash snapshot (JjClient.snapshot_working_copy() bound to "
        "the workspace path), and it must never be skippable."
    )
    assert "agent-write.txt" in result.applied_paths
    assert (colocated_repo.cwd / "agent-write.txt").read_text(encoding="utf-8") == (
        "written by plain file I/O, no jj command in the workspace\n"
    )


# ---------------------------------------------------------------------------
# T024 — contract T5: a genuinely empty delta is a success, not an error
# (FR-006).
# ---------------------------------------------------------------------------


async def test_empty_delta_returns_empty_not_error(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """When the agent step changes nothing at all, `fold_back()` must
    return `FoldBackOutcome.EMPTY` as an ordinary success — no exception,
    no `applied_paths` entries. This is the legitimate counterpart to
    T023's silent-failure case: EMPTY is correct here because the delta
    genuinely is empty, not because the snapshot step was skipped.
    """
    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-024", "T024 unit")

    async with session:
        async with session.lease(unit) as lease:
            # No writes at all.
            result = await session.fold_back(lease)

    assert result.outcome == FoldBackOutcome.EMPTY
    assert result.applied_paths == ()


# ---------------------------------------------------------------------------
# T025 — contract T6: ignored paths never fold back (FR-010).
# ---------------------------------------------------------------------------


async def test_ignored_paths_never_fold_back(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """Paths jj never tracks — a gitignored build directory and
    `*.jsonl` files — must never appear in the checkout after
    `fold_back()`, even when a real, non-ignored change folds back in
    the same application.

    This holds by construction (research.md R2): jj does not track
    ignored paths, so they never enter the workspace's working-copy
    commit and cannot travel via `jj squash`. The point of this test is
    to assert that directly, as a regression guard.
    """
    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-025", "T025 unit")

    async with session:
        async with session.lease(unit) as lease:
            build_dir = lease.workspace_path / "ignored-build"
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "new-artifact.bin").write_text("junk\n", encoding="utf-8")
            (lease.workspace_path / "notes.jsonl").write_text(
                '{"scratch": true}\n', encoding="utf-8"
            )
            # A real, non-ignored change too, so the fold-back isn't
            # itself an empty delta (that case is T024's).
            (lease.workspace_path / "tracked.txt").write_text(
                "changed alongside ignored paths\n", encoding="utf-8"
            )

            result = await session.fold_back(lease)

            assert result.outcome == FoldBackOutcome.APPLIED
            assert "ignored-build/new-artifact.bin" not in result.applied_paths
            assert "notes.jsonl" not in result.applied_paths
            assert "tracked.txt" in result.applied_paths

    assert not (colocated_repo.cwd / "ignored-build" / "new-artifact.bin").exists()
    assert not (colocated_repo.cwd / "notes.jsonl").exists()
    assert (colocated_repo.cwd / "tracked.txt").read_text(encoding="utf-8") == (
        "changed alongside ignored paths\n"
    )


# ---------------------------------------------------------------------------
# T026 — contract T7: `.maverick/**` never folds back even when modified
# inside the workspace (FR-011).
# ---------------------------------------------------------------------------


async def test_maverick_directory_never_folds_back(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """`.maverick/**` must never fold back, per contract T7 and
    research.md R2's verified `jj squash ... '~.maverick'` example.

    Caveat for a future reader: in the `colocated_repo` fixture,
    `.maverick/` is *also* listed in `.gitignore`, so this specific test
    cannot, by itself, distinguish "excluded because jj never tracked it"
    (FR-010's mechanism, already covered by T025) from "excluded because
    fold-back's fileset argument explicitly excludes it" (FR-011's
    mechanism, the actual contract this test targets — see research.md
    R2, which verifies the fileset exclusion by hand against a *tracked*
    `.maverick/runs/r.json`). This test still asserts the observable
    contract — a write under `.maverick/` inside the workspace must never
    reach the checkout, and the fixture's pre-existing `.keep` file must
    be left completely untouched — which is the behavior FR-011 requires
    regardless of which mechanism enforces it in this particular fixture.
    """
    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-026", "T026 unit")

    async with session:
        async with session.lease(unit) as lease:
            stray_runs_dir = lease.workspace_path / ".maverick" / "runs"
            stray_runs_dir.mkdir(parents=True, exist_ok=True)
            (stray_runs_dir / "stray.json").write_text('{"leaked": true}\n', encoding="utf-8")
            # A real, non-ignored change too, so the fold-back isn't
            # itself an empty delta.
            (lease.workspace_path / "tracked.txt").write_text(
                "changed alongside a .maverick write\n", encoding="utf-8"
            )

            result = await session.fold_back(lease)

            assert result.outcome == FoldBackOutcome.APPLIED
            assert not any(
                path == ".maverick" or path.startswith(".maverick/")
                for path in result.applied_paths
            )
            assert "tracked.txt" in result.applied_paths

    assert not (colocated_repo.cwd / ".maverick" / "runs" / "stray.json").exists()
    keep_file = colocated_repo.cwd / ".maverick" / "runs" / ".keep"
    assert keep_file.exists()
    assert keep_file.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# T029 — an agent-step error discards the delta and leaves the checkout
# byte-identical (FR-006).
# ---------------------------------------------------------------------------


class _SimulatedAgentError(Exception):
    """Marks that the agent step failed before producing a foldable delta.

    Used only to simulate a failing agent step inside `session.lease(...)`;
    it deliberately carries no isolation-specific meaning so this test does
    not depend on any exception type the implementation itself defines.
    """


async def test_discarding_a_failed_agent_step_leaves_checkout_untouched(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """If the agent step fails before `fold_back()` is ever called, the
    checkout must be left exactly as it was — nothing partially applied,
    nothing leaked.

    FR-006 is framed around a genuinely empty delta being a success
    (T024); the complementary case here is an agent step that never gets
    as far as producing a delta worth folding back at all. The workspace
    may hold partial work, but since `fold_back()` is never invoked, none
    of it should ever reach the checkout — exercised here by raising out
    of the `async with session.lease(unit) as lease:` block, which is the
    natural shape of "the agent step raised" for a caller of this API.
    """
    tracked_before = (colocated_repo.cwd / "tracked.txt").read_bytes()
    readme_before = (colocated_repo.cwd / "README.md").read_bytes()
    entries_before = {entry.name for entry in colocated_repo.cwd.iterdir()}

    session = _make_session(colocated_repo, isolation_home)
    unit = _unit("bead-029", "T029 unit")

    with pytest.raises(_SimulatedAgentError):
        async with session:
            async with session.lease(unit) as lease:
                (lease.workspace_path / "partial-work.txt").write_text(
                    "half-finished output\n", encoding="utf-8"
                )
                (lease.workspace_path / "tracked.txt").write_text(
                    "half-finished edit, never folded back\n", encoding="utf-8"
                )
                # The agent step fails before fold_back() is ever
                # called — nothing it wrote should ever leave the
                # workspace.
                raise _SimulatedAgentError("agent step failed")

    assert (colocated_repo.cwd / "tracked.txt").read_bytes() == tracked_before
    assert (colocated_repo.cwd / "README.md").read_bytes() == readme_before
    assert {entry.name for entry in colocated_repo.cwd.iterdir()} == entries_before

    checkout_status = await JjClient(cwd=colocated_repo.cwd).status()
    assert "The working copy has no changes." in checkout_status.output
