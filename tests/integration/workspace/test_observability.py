"""Integration tests for the isolation primitive's observability contract.

Covers tasks.md T112 -- FR-051 and SC-013
(specs/057-isolated-bead-workspaces/spec.md):

    FR-051: Every isolation lifecycle transition -- provision, agent-step
    boundary, artifact-level checks, fold-back, environment-level checks,
    undo, teardown, and sweep -- MUST be logged with the unit's identity
    and its workspace, and fold-backs, undos, verification rejections, and
    conflicts MUST additionally appear on the run's user-visible progress
    output.

    SC-013: An operator can reconstruct what happened during an
    interruption, a refused concurrent run, or an undo from log output
    and progress messages alone, without inspecting version-control
    internals.

Log capture mechanism: this repo wires structlog through the stdlib
``logging`` module (``maverick.logging.configure_logging`` ->
``structlog.stdlib.LoggerFactory`` + ``wrap_for_formatter``), so a
structlog event reaches ``pytest``'s ``caplog`` as an ordinary
``logging.LogRecord`` whose ``.msg`` is the *raw event dict* (not yet
rendered to a string) -- confirmed empirically against this repo's actual
``configure_logging()`` wiring before writing these assertions. This is
the same ``caplog``-based capture every other structured-logging test in
this repo uses (e.g. ``tests/unit/assumptions/test_suggestions.py``,
``tests/unit/test_config_workspace.py``); no ``structlog.testing`` helper
is used anywhere in this codebase, so none is introduced here either.

Ground truth for the assertions below was read directly from
``src/maverick/workspace/{lifecycle,foldback,session,journal}.py``'s
actual ``logger.info``/``logger.warning``/``logger.error`` call sites,
not assumed from the spec text. That reading surfaced genuine gaps
against FR-051's "unit's identity and its workspace" requirement --
which this repo's ``IsolationPolicy.workflow`` docstring identifies as
the ``workflow`` log field specifically ("Path segment and log field:
'fly', 'spec-chain'"). Per the task brief, these are reported rather than
worked around by loosening the assertions:

  * ``isolation_fold_back_started`` (foldback.py) passes
    ``workflow=lease.workspace_name`` -- ``IsolationLease.workspace_name``
    is the jj workspace's directory basename (``unit.key``, e.g.
    ``"bead-042"``), not the workflow slug (``"fly"`` /
    ``"spec-chain"``) every sibling event (``isolation_provisioned``,
    ``isolation_torn_down``, ``isolation_retained``) logs under that same
    field name. The field is present but holds the wrong value.
  * ``isolation_fold_back_completed`` (foldback.py) does not log
    ``workflow`` at all.
  * ``isolation_undo_started`` / ``isolation_undo_completed``
    (session.py) do not log ``workflow`` at all.
  * ``isolation_journal_stale`` (session.py) does not log ``workflow``,
    even though the persisted ``ApplicationRecord`` it reads
    (journal.py) carries a ``workflow`` field.

Each assertion below is written against the correct contract regardless,
so these gaps show up as failing assertions rather than being silently
accepted.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.exceptions import IsolationLockedError, IsolationRecoveryRequiredError
from maverick.jj.client import JjClient
from maverick.workspace import (
    CheckoutPath,
    FoldBackOutcome,
    IsolationPolicy,
    IsolationSession,
    UnitOfWork,
)
from maverick.workspace.journal import ApplicationRecord, write_record

pytestmark = pytest.mark.integration

_LOCK_RELPATH = Path(".maverick") / "runs" / "isolation.lock"


def _make_session(
    colocated_repo: JjClient,
    isolation_home: Path,
    *,
    workflow: str = "fly",
    run_id: str = "test-run-observability",
) -> IsolationSession:
    """Build an `IsolationSession` bound to the fixture checkout.

    Mirrors `test_undo.py`/`test_journal.py`/`test_foldback.py`'s
    `_make_session` helper byte-for-byte -- deliberately duplicated here
    rather than imported, per the instruction that this file define any
    local helpers it needs rather than reaching into a sibling test
    module or editing `conftest.py`.
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
        run_id=run_id,
        now=lambda: datetime.now(UTC),
        home=isolation_home,
    )


def _unit(key: str, label: str) -> UnitOfWork:
    return UnitOfWork(key=key, label=label, seed_inputs=())


def _events_named(records: Iterable[logging.LogRecord], event: str) -> list[dict[str, object]]:
    """Every captured structlog event dict named *event*, in emission
    order.

    `record.msg` is the raw structlog event dict on this repo's wiring
    (see module docstring) -- not yet rendered to a string -- so this
    filters on its `"event"` key directly rather than substring-matching
    rendered text (which the rest of this repo's `caplog`-based tests do
    only when they don't need individual field values, e.g.
    `"foo_happened" in caplog.text`).
    """
    found: list[dict[str, object]] = []
    for record in records:
        payload = record.msg
        if isinstance(payload, dict) and payload.get("event") == event:
            found.append(payload)
    return found


def _missing_or_wrong(payload: dict[str, object], *, expected: dict[str, object]) -> list[str]:
    """Field-completeness diagnostics for one event payload against
    *expected* key/value pairs. Returns an empty list when everything
    matches."""
    problems: list[str] = []
    for key, value in expected.items():
        if key not in payload:
            problems.append(f"missing field {key!r} (payload keys: {sorted(payload)})")
        elif payload[key] != value:
            problems.append(f"field {key!r} = {payload[key]!r}, expected {value!r}")
    return problems


# ---------------------------------------------------------------------------
# Scenario 1 -- normal lifecycle (provision -> fold-back -> teardown).
# ---------------------------------------------------------------------------


async def test_normal_lifecycle_logs_unit_key_workflow_and_workspace_path(
    colocated_repo: JjClient, isolation_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A full provision -> fold-back -> teardown cycle must log every
    transition with the unit's identity (`unit_key`) and its workspace
    (`workspace_path`), plus the owning `workflow` -- FR-051's "unit's
    identity and its workspace" requirement, read together with
    `IsolationPolicy.workflow`'s docstring identifying `workflow` as the
    log field it maps to.

    All diagnostics are collected before asserting so a single test run
    reports every gap at once, rather than stopping at the first one --
    this is an aggregation of independently-correct checks, not a
    weakened assertion.
    """
    workflow = "fly"
    session = _make_session(colocated_repo, isolation_home, workflow=workflow)
    unit = _unit("bead-112", "T112 unit")

    problems: list[str] = []

    with caplog.at_level(logging.DEBUG):
        async with session:
            async with session.lease(unit) as lease:
                expected_workspace_path = str(lease.workspace_path)

                (lease.workspace_path / "observed.txt").write_text(
                    "logged transitions\n", encoding="utf-8"
                )

                result = await session.fold_back(lease)
                assert result.outcome == FoldBackOutcome.APPLIED

    provisioned = _events_named(caplog.records, "isolation_provisioned")
    assert len(provisioned) == 1, f"expected exactly one provision event, got {provisioned}"
    problems += [
        f"isolation_provisioned: {p}"
        for p in _missing_or_wrong(
            provisioned[0],
            expected={
                "unit_key": unit.key,
                "workflow": workflow,
                "workspace_path": expected_workspace_path,
            },
        )
    ]

    fold_back_started = _events_named(caplog.records, "isolation_fold_back_started")
    assert len(fold_back_started) == 1, (
        f"expected exactly one fold-back-started event, got {fold_back_started}"
    )
    problems += [
        f"isolation_fold_back_started: {p}"
        for p in _missing_or_wrong(
            fold_back_started[0],
            expected={
                "unit_key": unit.key,
                "workflow": workflow,
                "workspace_path": expected_workspace_path,
            },
        )
    ]

    fold_back_completed = _events_named(caplog.records, "isolation_fold_back_completed")
    assert len(fold_back_completed) == 1, (
        f"expected exactly one fold-back-completed event, got {fold_back_completed}"
    )
    problems += [
        f"isolation_fold_back_completed: {p}"
        for p in _missing_or_wrong(
            fold_back_completed[0],
            expected={
                "unit_key": unit.key,
                "workflow": workflow,
                "workspace_path": expected_workspace_path,
                "outcome": FoldBackOutcome.APPLIED.value,
            },
        )
    ]

    torn_down = _events_named(caplog.records, "isolation_torn_down")
    assert len(torn_down) == 1, f"expected exactly one teardown event, got {torn_down}"
    problems += [
        f"isolation_torn_down: {p}"
        for p in _missing_or_wrong(
            torn_down[0],
            expected={
                "unit_key": unit.key,
                "workflow": workflow,
                "workspace_path": expected_workspace_path,
            },
        )
    ]

    assert not problems, (
        "one or more lifecycle-transition log events are missing unit_key/"
        "workflow/workspace_path, or hold a wrong value for one of them "
        "(FR-051):\n" + "\n".join(problems)
    )


# ---------------------------------------------------------------------------
# Scenario 2 -- refused concurrent run.
# ---------------------------------------------------------------------------


async def test_refused_concurrent_run_is_logged_and_self_explanatory(
    colocated_repo: JjClient, isolation_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A second isolated session refusing to start while a live pid holds
    the checkout's lock (contract C1, FR-048) must be reconstructable two
    ways, per SC-013:

    1. The raised `IsolationLockedError`'s message alone -- with no log
       inspection -- must name the holding pid and describe the
       situation in plain language (an operator "without inspecting
       version-control internals" reading only the exception text).
    2. A structured `isolation_lock_held` log event must also exist,
       naming the same pid, so the same fact is independently visible in
       log output.

    Mirrors `test_lock.py`'s
    `test_second_session_refuses_when_live_pid_holds_lock` -- own pid,
    guaranteed live for the duration of this test.
    """
    own_pid = os.getpid()
    lock_path = colocated_repo.cwd / _LOCK_RELPATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(own_pid), encoding="utf-8")

    session = _make_session(colocated_repo, isolation_home, run_id="run-observability-locked")

    with caplog.at_level(logging.WARNING), pytest.raises(IsolationLockedError) as excinfo:
        async with session:
            pass  # Entry itself must raise -- the body must never run.

    error = excinfo.value
    assert error.pid == own_pid

    # (1) The exception message alone names the pid and the situation in
    # plain language -- no log inspection, no jj/version-control detail
    # required to understand it.
    message = str(error)
    assert str(own_pid) in message, (
        f"IsolationLockedError message does not name the holding pid on its own: {message!r}"
    )
    assert "isolation lock" in message.lower() or "exclusive" in message.lower(), (
        f"IsolationLockedError message does not explain the situation in "
        f"plain language: {message!r}"
    )

    # (2) The same fact is independently visible in structured log output.
    lock_held_events = _events_named(caplog.records, "isolation_lock_held")
    assert len(lock_held_events) == 1, (
        f"expected exactly one isolation_lock_held log event, got {lock_held_events}"
    )
    assert lock_held_events[0].get("holding_pid") == own_pid


# ---------------------------------------------------------------------------
# Scenario 3 -- undo.
# ---------------------------------------------------------------------------


async def test_undo_logs_unit_key_workflow_and_workspace_path(
    colocated_repo: JjClient, isolation_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`IsolationSession.undo()` (contract C5) must log both its start
    and its completion with the unit's identity, its workspace, and the
    owning workflow -- mirrors `test_undo.py`'s successful-undo flow
    (lease -> fold_back -> undo), asserting on the log events that flow
    produces rather than the checkout-state postconditions `test_undo.py`
    already covers.
    """
    workflow = "fly"
    session = _make_session(colocated_repo, isolation_home, workflow=workflow)
    unit = _unit("bead-112-undo", "T112 undo unit")

    problems: list[str] = []

    with caplog.at_level(logging.DEBUG):
        async with session:
            async with session.lease(unit) as lease:
                expected_workspace_path = str(lease.workspace_path)
                (lease.workspace_path / "rejected.py").write_text(
                    "# work a reviewer rejects\n", encoding="utf-8"
                )

                result = await session.fold_back(lease)
                assert result.outcome == FoldBackOutcome.APPLIED

                await session.undo(lease, result)

    undo_started = _events_named(caplog.records, "isolation_undo_started")
    assert len(undo_started) == 1, f"expected exactly one undo-started event, got {undo_started}"
    problems += [
        f"isolation_undo_started: {p}"
        for p in _missing_or_wrong(
            undo_started[0],
            expected={
                "unit_key": unit.key,
                "workflow": workflow,
                "workspace_path": expected_workspace_path,
            },
        )
    ]

    undo_completed = _events_named(caplog.records, "isolation_undo_completed")
    assert len(undo_completed) == 1, (
        f"expected exactly one undo-completed event, got {undo_completed}"
    )
    problems += [
        f"isolation_undo_completed: {p}"
        for p in _missing_or_wrong(
            undo_completed[0],
            expected={
                "unit_key": unit.key,
                "workflow": workflow,
                "workspace_path": expected_workspace_path,
            },
        )
    ]

    assert not problems, (
        "isolation_undo_started/isolation_undo_completed are missing "
        "unit_key/workflow/workspace_path, or hold a wrong value for one "
        "of them (FR-051):\n" + "\n".join(problems)
    )


# ---------------------------------------------------------------------------
# Scenario 4 -- interruption (stale journal from a crashed prior run).
# ---------------------------------------------------------------------------


async def test_interrupted_run_stale_journal_is_reconstructable_from_logs(
    colocated_repo: JjClient, isolation_home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A crashed prior run's uncleared `ApplicationRecord` (contract C2,
    FR-049) must be reconstructable from log output alone: which unit was
    mid-application, which operation (fold-back or undo), where its
    workspace is, and the recovery handle (`restore_operation_id`) a
    human hands to `jj op restore` -- SC-013's "reconstruct ... an
    interruption ... from log ... output alone" and FR-049's "logged with
    enough detail to support manual recovery".

    Mirrors `test_journal.py`'s `_crashed_record()` +
    `test_session_entry_refuses_on_stale_journal` pattern.
    """
    checkout = colocated_repo.cwd
    record = ApplicationRecord(
        schema_version=1,
        run_id="prior-crashed-run",
        workflow="fly",
        unit_key="bead-112-interrupted",
        operation="fold-back",
        restore_operation_id="deadbeef1234",
        workspace_path=str(checkout.parent / "workspaces" / "repo" / "fly" / "bead-112"),
        started_at=datetime(2026, 8, 20, 11, 55, 0, tzinfo=UTC),
    )
    await write_record(checkout, record)

    session = _make_session(colocated_repo, isolation_home, run_id="run-observability-recovery")

    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(IsolationRecoveryRequiredError) as excinfo,
    ):
        await session.__aenter__()

    error = excinfo.value
    # The exception alone already carries the full recovery detail
    # (contract C2) -- confirmed here as a precondition for the log
    # assertion below, not a new contract this file introduces.
    assert error.unit_key == record.unit_key
    assert error.operation == record.operation
    assert error.workspace_path == record.workspace_path
    assert error.restore_operation_id == record.restore_operation_id

    stale_events = _events_named(caplog.records, "isolation_journal_stale")
    assert len(stale_events) == 1, (
        f"expected exactly one isolation_journal_stale log event, got {stale_events}"
    )
    problems = _missing_or_wrong(
        stale_events[0],
        expected={
            "unit_key": record.unit_key,
            "workflow": record.workflow,
            "operation": record.operation,
            "workspace_path": record.workspace_path,
            "restore_operation_id": record.restore_operation_id,
        },
    )
    assert not problems, (
        "isolation_journal_stale is missing detail an operator needs to "
        "reconstruct the interruption from logs alone (FR-049, SC-013):\n" + "\n".join(problems)
    )
