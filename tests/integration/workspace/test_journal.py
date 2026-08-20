"""Integration test for `IsolationSession`'s stale-journal refusal against
a real, throwaway jj-colocated checkout.

Contract: `specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md`
section "Behavioral contract" C2, and the contract-test table T13:

    C2 -- Session entry refuses on a stale journal (FR-049)

    If `<checkout>/.maverick/runs/isolation-journal.json` exists on entry,
    `__aenter__` raises `IsolationRecoveryRequiredError` carrying the
    record's `unit_key`, `operation`, `workspace_path`, and
    `restore_operation_id`. The session performs no automatic rollback and
    no inference from the checkout's contents.

Mechanism: research.md R8 -- the journal answers "did a previous run die
mid-application?" and must survive the process; a run that starts and finds
an uncleared record refuses outright and never rolls back automatically,
because an automatic rollback would discard whatever the user did in the
checkout since the crash. data-model.md's `ApplicationRecord` section
documents the persisted shape this test writes by hand to simulate a
crashed prior run.

As of this writing, `IsolationSession.__aenter__` does not yet check the
journal on entry -- that wiring lands in this same phase's T049
(`session.py`'s `__aenter__`/`__aexit__` currently just `return self` /
`return None`). This test is written against the intended contract (C2)
regardless, per TDD: it is expected to fail (RED) right now because the
exception is never raised, not because the test itself is wrong. See the
task report for the exact observed failure mode.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.exceptions import IsolationRecoveryRequiredError
from maverick.jj.client import JjClient
from maverick.workspace import CheckoutPath, IsolationPolicy, IsolationSession
from maverick.workspace.journal import ApplicationRecord, write_record

pytestmark = pytest.mark.integration


def _make_session(
    colocated_repo: JjClient,
    isolation_home: Path,
    *,
    workflow: str = "fly",
    run_id: str = "test-run-recovering",
) -> IsolationSession:
    """Build an `IsolationSession` bound to the fixture checkout, mirroring
    `test_undo.py`'s `_make_session` helper byte-for-byte."""
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
        run_id=run_id,
        now=lambda: datetime.now(UTC),
        home=isolation_home,
    )


def _crashed_record(*, workflow: str = "fly") -> ApplicationRecord:
    """An `ApplicationRecord` shaped like one a prior run left behind
    mid-fold-back before crashing -- what `write_record` persisted right
    before step 4 of contract C4, never cleared because the process died
    before reaching step 6."""
    return ApplicationRecord(
        schema_version=1,
        run_id="prior-crashed-run",
        workflow=workflow,
        unit_key="bead-042",
        operation="fold-back",
        restore_operation_id="deadbeef1234",
        workspace_path="/home/user/.maverick/workspaces/repo/fly/bead-042",
        started_at=datetime(2026, 8, 20, 11, 55, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# T042 -- contract T13: a session that finds an uncleared record refuses
# with IsolationRecoveryRequiredError carrying unit, operation, workspace
# path, and restore operation id, and performs no automatic rollback.
# ---------------------------------------------------------------------------


async def test_session_entry_refuses_on_stale_journal(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """Simulate a prior run that crashed mid-application: write an
    `ApplicationRecord` to the checkout's journal path *before* the new
    session is ever entered. `__aenter__` must raise
    `IsolationRecoveryRequiredError` carrying the record's full recovery
    detail, and must never touch the checkout or the journal file itself
    while doing so."""
    checkout = colocated_repo.cwd
    record = _crashed_record()

    await write_record(checkout, record)

    session = _make_session(colocated_repo, isolation_home)

    # Call `__aenter__` directly rather than via `async with` -- the
    # refusal must happen at entry, before any lease body ever runs, so
    # there is no context-manager body to guard here.
    with pytest.raises(IsolationRecoveryRequiredError) as excinfo:
        await session.__aenter__()

    error = excinfo.value
    assert error.unit_key == record.unit_key
    assert error.operation == record.operation
    assert error.workspace_path == record.workspace_path
    assert error.restore_operation_id == record.restore_operation_id


async def test_session_entry_performs_no_automatic_rollback(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """The refusal must be a pure refusal: the journal record is left in
    place (not auto-cleared) and the checkout's own state is untouched --
    no jj operation is auto-restored on the session's behalf. An automatic
    rollback would discard whatever the user did in the checkout since the
    crash (research.md R8), so this session must not attempt one."""
    checkout = colocated_repo.cwd
    record = _crashed_record()
    await write_record(checkout, record)

    # The checkout's own state at the moment recovery is required -- some
    # uncommitted edit the user made after the crash, unrelated to the
    # stranded application. A rollback-on-refusal would be visible here as
    # this edit disappearing or the jj operation log changing.
    dirty_path = checkout / "tracked.txt"
    dirty_path.write_text("edited after the crash\n", encoding="utf-8")
    pre_attempt_status = await JjClient(cwd=checkout).status()

    session = _make_session(colocated_repo, isolation_home)

    with pytest.raises(IsolationRecoveryRequiredError):
        await session.__aenter__()

    # No rollback: the journal record is still there, untouched.
    journal_path = checkout / ".maverick" / "runs" / "isolation-journal.json"
    assert journal_path.is_file()

    # No rollback: the post-crash edit the user made is still exactly
    # as they left it.
    assert dirty_path.read_text(encoding="utf-8") == "edited after the crash\n"

    # No rollback: no jj operation was restored on the session's behalf.
    post_attempt_status = await JjClient(cwd=checkout).status()
    assert post_attempt_status.output == pre_attempt_status.output
