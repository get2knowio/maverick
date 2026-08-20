"""T056-T058 — isolated-mode gate-failure handling (contract F4, F5, F10).

Three scenarios sharing one deterministic gate-failure mechanism: the
per-bead isolated gate (``_gate_impl_isolated``) always runs in the
*checkout*, single-shot, with ``validation_commands=None`` — so it always
falls back to the module-level ``maverick.library.actions.validation.
DEFAULT_STAGE_COMMANDS`` (see ``conftest.patch_default_gate_commands``'s
docstring). This module patches that same dict's ``"test"`` stage to a
tiny Python one-liner that checks for a sentinel file
(``fix-marker.txt``) in ``Path.cwd()`` — which is the checkout at gate
time, since ``gate`` is always bound to the checkout even in isolated
mode (T074, research.md R6).

* T056 (F4): a custom stub runtime's ``SubmitFixResultPayload`` handler
  writes the sentinel into ``Path.cwd()`` at fix-call time — which is the
  bead's *workspace* thanks to ``agent_step_scope``'s chdir — so it
  travels into the checkout on the next ``fold_back`` (``fold_scope=()``
  folds everything) and the retried gate then passes.
* T057 (F5): the same stub never writes the sentinel, so the gate fails
  on every attempt and ``undo_fold_back`` abandons the bead once
  ``MAX_GATE_FIX_ATTEMPTS`` (2) is exhausted.
* T058 (F10): ``IsolationSession.undo`` is monkeypatched to raise
  ``IsolationUndoFailedError`` unconditionally, so the very first gate
  failure halts the run before any fix round is attempted.

None of these scenarios fit ``conftest.run_fly_workflow`` unmodified:
T057/T058 both end in ``PythonWorkflow.execute()`` re-raising the
background task's exception after yielding ``WorkflowCompleted`` (T058
via ``FlyBeadsWorkflow._run``'s explicit ``raise WorkflowError(...)`` on
an isolation halt) — ``run_fly_workflow`` assumes a clean drain, so this
module defines its own tolerant driver instead of editing
``conftest.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.exceptions import IsolationUndoFailedError, WorkflowError
from maverick.payloads import SubmitFixResultPayload
from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

from .conftest import (
    BD_UNAVAILABLE,
    JJ_UNAVAILABLE,
    FlyRunOutcome,
    FlyStubRuntime,
    build_fly_repo,
    commit_descriptions_since,
    make_fly_config,
    noop_gate_commands,
    working_copy_dirt,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if BD_UNAVAILABLE or JJ_UNAVAILABLE:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)

_MARKER_NAME = "fix-marker.txt"


# ---------------------------------------------------------------------------
# Deterministic gate: "test" stage checks a checkout-relative sentinel file.
# ---------------------------------------------------------------------------


def _marker_gate_commands() -> dict[str, tuple[str, ...]]:
    """``DEFAULT_STAGE_COMMANDS`` replacement: format/lint no-op, test
    checks for ``fix-marker.txt`` in the process's current directory —
    which is the checkout at gate time (T074), regardless of isolation."""
    noop = tuple(noop_gate_commands())
    check_marker = (
        sys.executable,
        "-c",
        f"import pathlib, sys; sys.exit(0 if pathlib.Path({_MARKER_NAME!r}).is_file() else 1)",
    )
    return {"format": noop, "lint": noop, "typecheck": noop, "test": check_marker}


@pytest.fixture
def patch_marker_gate_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    from maverick.library.actions import validation as validation_module

    monkeypatch.setattr(validation_module, "DEFAULT_STAGE_COMMANDS", _marker_gate_commands())


# ---------------------------------------------------------------------------
# Stub runtime that can actually service a fix call (base FlyStubRuntime
# raises on SubmitFixResultPayload — the happy-path fixture never expects
# one).
# ---------------------------------------------------------------------------


def _make_cost() -> CostRecord:
    return CostRecord(
        provider_id="anthropic",
        model_id="claude-haiku-4-5",
        cost_usd=0.01,
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish="end_turn",
    )


class GateFixCapableStubRuntime(FlyStubRuntime):
    """Extends ``FlyStubRuntime``: a ``SubmitFixResultPayload`` call
    succeeds instead of raising, optionally writing the gate's sentinel
    file into ``Path.cwd()`` (the bead's workspace at fix-call time).

    Every fix call also writes a per-round, uniquely-named attempt file
    (``fix-attempt-<n>.txt``) regardless of whether it satisfies the
    gate. This is not incidental: a fix round that changes *nothing* in
    the workspace makes the retried ``fold_back`` squash produce a
    byte-identical commit (same tree, same parent) to the one the prior
    ``undo`` already discarded — and if both land within the same
    wall-clock second, jj's backend rejects it outright (``Internal
    error: ... Newly-created commit <id> already exists``), reproduced
    directly against the ``jj`` CLI outside this harness. That's a jj/
    fold-back-retry edge case orthogonal to what T057 means to exercise
    (repeated gate rejection -> exhaustion), so each round's attempt
    file keeps the retried trees distinct without ever satisfying the
    gate's own sentinel check.
    """

    #: Overridden per test via the factory below.
    write_marker_on_fix: bool = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.fix_call_count = 0

    async def execute(self, prompt: str, *, schema: Any = None, **kwargs: Any) -> RuntimeResult:
        if schema is SubmitFixResultPayload:
            self.calls.append({"prompt": prompt, "schema": schema, **kwargs})
            self.fix_call_count += 1
            (Path.cwd() / f"fix-attempt-{self.fix_call_count}.txt").write_text(
                "attempted\n", encoding="utf-8"
            )
            if self.write_marker_on_fix:
                (Path.cwd() / _MARKER_NAME).write_text("fixed\n", encoding="utf-8")
            structured: dict[str, Any] = {
                "summary": "Applied the gate fix.",
                "addressed": ["gate"],
                "contested": {},
                "assumptions": [],
            }
            return RuntimeResult(
                text="", structured=structured, cost=_make_cost(), finish="end_turn"
            )
        return await super().execute(prompt, schema=schema, **kwargs)


def gate_fix_stub_runtime_factory(
    monkeypatch: pytest.MonkeyPatch, *, write_marker_on_fix: bool
) -> list[GateFixCapableStubRuntime]:
    """Same wiring shape as ``conftest.stub_fly_runtime_factory``, but
    binds ``GateFixCapableStubRuntime`` instead of the base stub so this
    module's tests can exercise a real (successful) fix call."""
    constructed: list[GateFixCapableStubRuntime] = []
    shared_calls: list[dict[str, Any]] = []

    def _factory(provider_id: str) -> type[GateFixCapableStubRuntime]:
        class _Bound(GateFixCapableStubRuntime):
            write_marker_on_fix_bound = write_marker_on_fix

            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, calls=shared_calls, **kwargs)
                self.write_marker_on_fix = write_marker_on_fix
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


# ---------------------------------------------------------------------------
# A tolerant driver — like conftest.run_fly_workflow, but catches the
# WorkflowError FlyBeadsWorkflow._run raises on an isolation halt (T058)
# instead of assuming a clean drain.
# ---------------------------------------------------------------------------


async def _run_fly_workflow_allow_halt(
    *,
    config: Any,
    cwd: Path,
    epic_id: str,
    isolated: bool,
    monkeypatch: pytest.MonkeyPatch,
    max_beads: int = 0,
) -> tuple[FlyRunOutcome, Exception | None]:
    monkeypatch.chdir(cwd)

    workflow = FlyBeadsWorkflow(config=config)
    inputs: dict[str, Any] = {
        "epic_id": epic_id,
        "max_beads": max_beads,
        "auto_commit": False,
        "watch": False,
        "skip_preflight": True,
        "cwd": str(cwd),
        "isolated": isolated,
    }

    events = []
    raised: Exception | None = None
    try:
        async for event in workflow.execute(inputs):
            events.append(event)
    except WorkflowError as exc:  # noqa: BLE001 — deliberately broad: this is the halt path
        raised = exc

    assert workflow.result is not None
    outcome = FlyRunOutcome(
        success=workflow.result.success,
        final_output=workflow.result.final_output,
        events=events,
    )
    return outcome, raised


# ---------------------------------------------------------------------------
# T056 — gate fails -> undo -> fix in workspace -> refold -> gate passes
# -> commit (contract F4, FR-014, FR-017).
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("patch_marker_gate_commands")
async def test_gate_failure_then_fix_then_pass_commits_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo")
    runtimes = gate_fix_stub_runtime_factory(monkeypatch, write_marker_on_fix=True)
    config = make_fly_config(workspace_root=tmp_path / "workspaces")

    outcome, raised = await _run_fly_workflow_allow_halt(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
    )

    assert raised is None
    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_succeeded"] == len(repo.task_ids)
    assert outcome.final_output["beads_failed"] == 0

    # Both beads landed as normal `bead(<id>): <title>` commits.
    descriptions = commit_descriptions_since(repo.path, repo.baseline_change_id)
    assert len(descriptions) == len(repo.task_ids), descriptions
    for description, task_id, title in zip(
        descriptions, repo.task_ids, repo.task_titles, strict=True
    ):
        assert description.startswith(f"bead({task_id}): {title}"), description
        assert f"\nBead: {task_id}" in description, description

    # Every bead's own implementation file landed in the checkout.
    for task_id in repo.task_ids:
        produced = repo.path / f"{task_id}.txt"
        assert produced.is_file(), f"missing {produced}"
        assert produced.read_text(encoding="utf-8") == f"implemented {task_id}\n"

    # The sentinel the fix call wrote made it into the checkout (folded
    # back, then committed alongside the first bead it unblocked) rather
    # than being left as uncommitted dirt.
    assert (repo.path / _MARKER_NAME).is_file()

    # A real fix call actually happened — the fix path was exercised, not
    # skipped by some other route to a passing gate.
    fix_calls = [
        call
        for runtime in runtimes
        for call in runtime.calls
        if call.get("schema") is SubmitFixResultPayload
    ]
    assert len(fix_calls) >= 1, "expected at least one SubmitFixResultPayload call"

    # Nothing but bd's own audit trail is left dirty.
    dirt = working_copy_dirt(repo.path)
    assert all(path.startswith(".beads/") for path in dirt), dirt


# ---------------------------------------------------------------------------
# T057 — gate fails, fix attempts exhausted -> undo -> bead abandoned ->
# checkout byte-identical (contract F5, SC-003).
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("patch_marker_gate_commands")
async def test_gate_failure_exhausted_abandons_bead_checkout_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from .conftest import BeadSpec

    solo_bead = BeadSpec(title="Add solo module", description="Implement the solo module.")
    repo = build_fly_repo(tmp_path / "repo", bead_specs=(solo_bead,))
    runtimes = gate_fix_stub_runtime_factory(monkeypatch, write_marker_on_fix=False)
    config = make_fly_config(workspace_root=tmp_path / "workspaces")

    # A bead that never satisfies the gate is never marked complete, so
    # `bd ready` keeps returning it forever — `select_next_bead` has no
    # notion of "already exhausted this run" for a *failed* bead (only
    # successes are tracked via `completed_bead_ids`). Bound the run to
    # this bead's one (exhausted) attempt explicitly, exactly like the
    # non-isolated exhausted-gate scenario would need to as well. Predates
    # 057 — https://github.com/get2knowio/maverick/issues/189, not fixed
    # here.
    outcome, raised = await _run_fly_workflow_allow_halt(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
        max_beads=1,
    )

    assert raised is None
    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_succeeded"] == 0
    assert outcome.final_output["beads_failed"] >= 1

    # No commit landed for the abandoned bead.
    descriptions = commit_descriptions_since(repo.path, repo.baseline_change_id)
    assert descriptions == [], descriptions

    # The bead's implementation file never made it into the checkout — it
    # only ever existed in the (torn-down, never-retained) workspace.
    task_id = repo.task_ids[0]
    assert not (repo.path / f"{task_id}.txt").exists()
    assert not (repo.path / _MARKER_NAME).exists()

    # Checkout is byte-identical to its pre-run state modulo bd's own
    # audit trail.
    dirt = working_copy_dirt(repo.path)
    assert all(path.startswith(".beads/") for path in dirt), dirt

    # The fix path was actually exercised (not skipped) — up to
    # MAX_GATE_FIX_ATTEMPTS (2) fix calls, none of which closed the gate.
    fix_calls = [
        call
        for runtime in runtimes
        for call in runtime.calls
        if call.get("schema") is SubmitFixResultPayload
    ]
    assert len(fix_calls) >= 1, "expected at least one SubmitFixResultPayload call"


# ---------------------------------------------------------------------------
# T058 — undo failure halts the run and starts no further bead (contract
# F10, FR-018).
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("patch_marker_gate_commands")
async def test_undo_failure_halts_run_before_next_bead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maverick.workspace.session import IsolationSession

    repo = build_fly_repo(tmp_path / "repo")  # two beads: alpha, beta

    async def _always_fail_undo(self: IsolationSession, lease: Any, result: Any) -> None:
        raise IsolationUndoFailedError(
            "simulated jj op restore failure",
            workspace_path=str(lease.workspace_path),
            restore_operation_id=result.restore_operation_id,
        )

    monkeypatch.setattr(IsolationSession, "undo", _always_fail_undo)

    # Gate never passes (sentinel never written) — reached only for the
    # first bead, since the run halts before a second bead can start.
    from .conftest import stub_fly_runtime_factory

    stub_fly_runtime_factory(monkeypatch)
    config = make_fly_config(workspace_root=tmp_path / "workspaces")

    outcome, raised = await _run_fly_workflow_allow_halt(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
    )

    # The run halts hard: FlyBeadsWorkflow._run raises WorkflowError, and
    # PythonWorkflow.execute() re-raises it after recording a failed result.
    assert raised is not None
    assert "halted" in str(raised) or "isolation" in str(raised).lower()
    assert outcome.success is False

    # No commit exists for either bead — bead 1 never reached `commit`
    # (its gate never passed), and bead 2 was never even selected.
    descriptions = commit_descriptions_since(repo.path, repo.baseline_change_id)
    assert descriptions == [], descriptions

    # The second bead never started at all: not selected, not
    # implemented, no trace of its implementation file anywhere. (Bead
    # 1's own implementation file, by contrast, MAY still be sitting in
    # the checkout — that is exactly the "unverified fold-back delta"
    # FR-018/contract F10 describes: `undo` never got the chance to
    # restore the checkout because it failed outright.)
    second_task_id = repo.task_ids[1]
    assert not (repo.path / f"{second_task_id}.txt").exists(), second_task_id
