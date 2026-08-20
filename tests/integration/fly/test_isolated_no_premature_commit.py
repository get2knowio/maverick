"""T063 — zero commits for a bead that failed any declared check, at every
failure point (contract F1-F10's shared guarantee G4, FR-016, SC-004).

Contract ``fly-isolated-mode.md`` states G4 plainly: "Nothing is committed
until every declared check has passed." The "Failure taxonomy" table names
four distinct outcomes a naive implementation would collapse into "the bead
failed" — this module drives each independently, with a fresh one-bead
fixture per scenario, and asserts the same thing every time: the run
reports the bead as failed, no ``bead(<id>): ...`` commit ever lands for
it, and the checkout shows no trace of its implementation.

* **Agent failure** — the implementer's own call raises (a non-transient
  error, per ``_call_implementer_with_escalation``'s ``except Exception``
  branch) before any check even runs.
* **Artifact-level check failure** — ``ac_check`` (verification commands
  from the bead's ``## Verification`` section) fails inside the workspace,
  and the base ``FlyStubRuntime``'s ``SubmitFixResultPayload`` handler
  raises (the happy-path fixture never expects a fix call), so the one
  permitted retry fails immediately too.
* **Fold-back conflict** — a real jj merge conflict, forced by mutating
  the checkout out-of-band (a real file write + ``jj commit``) between the
  bead's workspace already holding its own write to the same path and
  ``fold_back()``'s own squash — mirrors ``test_isolated_conflict.py``
  (T059)'s technique, replicated locally per this task's instructions
  rather than imported.
* **Environment-level check failure (the gate)** — ``DEFAULT_STAGE_COMMANDS``
  is patched so the ``format`` stage always fails; the same base-stub
  fix-raises-immediately behavior as the artifact-check scenario abandons
  the bead on the first ``gate_fix`` round rather than exhausting
  ``MAX_GATE_FIX_ATTEMPTS`` — either is a legitimate route to "the bead
  ultimately fails," per this task's own framing.

Every scenario below drives ``run_fly_workflow(..., max_beads=1)``. Nothing
in ``select_next_bead``/``record_outcome`` removes a failed-but-still-ready
bead from ``bd ready`` (only a *succeeded* bead is appended to
``completed_bead_ids``), so a deterministic, permanent failure — as every
scenario here is, by design — would otherwise have the drain loop reselect
and reprocess the very same bead forever within one run. ``max_beads=1``
bounds each run to exactly one bead-processing pass regardless of outcome,
which is exactly the one attempt each scenario needs to observe; it does
not change what is being asserted. Predates 057 and applies identically in
non-isolated mode — filed as
https://github.com/get2knowio/maverick/issues/189, not fixed here.

See ``specs/057-isolated-bead-workspaces/contracts/fly-isolated-mode.md``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from airframe.protocol import RuntimeResult

from maverick.payloads import SubmitImplementationPayload
from maverick.workspace import IsolationSession
from maverick.workspace.foldback import sync_workspace

from .conftest import (
    BD_UNAVAILABLE,
    JJ_UNAVAILABLE,
    BeadSpec,
    FlyFixtureRepo,
    FlyStubRuntime,
    build_fly_repo,
    commit_descriptions_since,
    make_fly_config,
    noop_gate_commands,
    run_fly_workflow,
    stub_fly_runtime_factory,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if BD_UNAVAILABLE or JJ_UNAVAILABLE:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)


# ---------------------------------------------------------------------------
# Shared assertions.
# ---------------------------------------------------------------------------


def _assert_bead_never_committed(repo: FlyFixtureRepo, bead_id: str) -> None:
    """No commit in this run's history carries this bead's ``bead(<id>):
    ...`` subject (G4). Checks the subject prefix rather than requiring an
    empty commit list outright, so this same helper works for the
    fold-back-conflict scenario below, which deliberately injects its own
    (non-bead) out-of-band commit into the same revset range."""
    descriptions = commit_descriptions_since(repo.path, repo.baseline_change_id)
    assert not any(d.startswith(f"bead({bead_id}):") for d in descriptions), descriptions


def _assert_no_implementation_file(repo: FlyFixtureRepo, bead_id: str) -> None:
    """The bead's own ``<bead_id>.txt`` (``FlyStubRuntime``'s implement
    marker) never reached the checkout — it only ever existed inside a
    workspace that was torn down without a fold-back landing."""
    produced = repo.path / f"{bead_id}.txt"
    assert not produced.is_file(), f"found {produced} in checkout after a failed bead"


_SOLO_BEAD = BeadSpec(
    title="Add solo module", description="Implement the solo module.", priority=1
)


# ---------------------------------------------------------------------------
# Scenario 1 — agent (implement) failure.
# ---------------------------------------------------------------------------


class _ImplementRaisesRuntime(FlyStubRuntime):
    """Like ``FlyStubRuntime``, except every ``SubmitImplementationPayload``
    call raises a plain (non-transient) exception — simulating the
    implementer agent itself failing before any check ever runs.
    ``_call_implementer_with_escalation``'s bare ``except Exception`` branch
    treats this as non-transient: no escalation, no retry, the bead is
    aborted immediately (``actions.py``, ``_implement_impl``)."""

    async def execute(self, prompt: str, *, schema: Any = None, **kwargs: Any) -> RuntimeResult:
        if schema is SubmitImplementationPayload:
            self.calls.append({"prompt": prompt, "schema": schema, **kwargs})
            raise RuntimeError("simulated implementer agent failure")
        return await super().execute(prompt, schema=schema, **kwargs)


def _implement_raises_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_ImplementRaisesRuntime]:
    """Local variant of ``conftest.stub_fly_runtime_factory`` bound to
    ``_ImplementRaisesRuntime`` — defined here rather than in
    ``conftest.py`` per this task's instructions."""
    constructed: list[_ImplementRaisesRuntime] = []
    shared_calls: list[dict[str, Any]] = []

    def _factory(provider_id: str) -> type[_ImplementRaisesRuntime]:
        class _Bound(_ImplementRaisesRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, calls=shared_calls, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_agent_error_produces_no_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo", bead_specs=(_SOLO_BEAD,))
    _implement_raises_runtime_factory(monkeypatch)
    config = make_fly_config(workspace_root=tmp_path / "workspaces")

    outcome = await run_fly_workflow(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
        max_beads=1,
    )

    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_processed"] == 1
    assert outcome.final_output["beads_succeeded"] == 0
    assert outcome.final_output["beads_failed"] == 1

    bead_id = repo.task_ids[0]
    _assert_bead_never_committed(repo, bead_id)
    _assert_no_implementation_file(repo, bead_id)


# ---------------------------------------------------------------------------
# Scenario 2 — artifact-level check failure (ac_check).
# ---------------------------------------------------------------------------

#: ``## Verification`` commands are only run when they start with one of
#: ``rg``/``grep``/``cargo``/``make`` (``_ac_check_impl``). A ``grep`` for a
#: marker string no produced file will ever contain always fails, whatever
#: bead id the fixture happens to assign.
_VERIFICATION_BEAD = BeadSpec(
    title="Add verified module",
    description=(
        "Implement the module.\n\n## Verification\n\n- grep -q nonexistent-marker-xyz *.txt\n"
    ),
    priority=1,
)


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_artifact_check_failure_produces_no_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo", bead_specs=(_VERIFICATION_BEAD,))
    stub_fly_runtime_factory(monkeypatch)
    config = make_fly_config(workspace_root=tmp_path / "workspaces")

    outcome = await run_fly_workflow(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
        max_beads=1,
    )

    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_processed"] == 1
    assert outcome.final_output["beads_succeeded"] == 0
    assert outcome.final_output["beads_failed"] == 1

    bead_id = repo.task_ids[0]
    _assert_bead_never_committed(repo, bead_id)
    _assert_no_implementation_file(repo, bead_id)


# ---------------------------------------------------------------------------
# Scenario 3 — fold-back conflict.
# ---------------------------------------------------------------------------


def _install_conflicting_out_of_band_mutation(
    monkeypatch: pytest.MonkeyPatch, *, checkout: Path, bead_id: str, content: str
) -> None:
    """Monkeypatch ``IsolationSession.fold_back`` so the *first* call (this
    single-bead fixture's only bead) mutates ``<bead_id>.txt`` in the
    checkout out-of-band — a real write plus a real ``jj commit`` — before
    delegating to the real implementation. That lands exactly between "the
    bead's workspace already holds its own write to that same path" (its
    implement step already ran) and "fold-back's own squash" (not yet
    run), producing a genuine two-sided jj conflict — mirrors
    ``test_isolated_conflict.py``'s ``_install_out_of_band_mutation``,
    replicated locally (not imported) per this task's instructions.

    The workspace's own working copy is snapshotted first
    (``sync_workspace``, the same chokepoint ``fold_back()`` itself calls
    as its step 1) so the agent's plain-file write is captured into the
    workspace's own commit *before* the checkout mutation advances the
    repo-wide jj operation log — skipping this ordering yields a silently
    empty fold-back with no conflict at all (verified by
    ``test_isolated_conflict.py``'s own module docstring).
    """
    real_fold_back = IsolationSession.fold_back
    mutated = {"done": False}

    async def _patched_fold_back(
        self: IsolationSession, lease: Any, *, fold_scope: tuple[str, ...] | None = None
    ) -> Any:
        if not mutated["done"]:
            mutated["done"] = True
            await sync_workspace(lease.workspace_path)
            target = checkout / f"{bead_id}.txt"
            target.write_text(content, encoding="utf-8")
            subprocess.run(
                ["jj", "commit", "-m", "out-of-band: concurrent checkout mutation"],
                cwd=checkout,
                check=True,
                capture_output=True,
                text=True,
            )
        return await real_fold_back(self, lease, fold_scope=fold_scope)

    monkeypatch.setattr(IsolationSession, "fold_back", _patched_fold_back)


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_foldback_conflict_produces_no_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo", bead_specs=(_SOLO_BEAD,))
    bead_id = repo.task_ids[0]
    out_of_band_content = "checkout out-of-band mutation\n"

    stub_fly_runtime_factory(monkeypatch)
    _install_conflicting_out_of_band_mutation(
        monkeypatch, checkout=repo.path, bead_id=bead_id, content=out_of_band_content
    )
    config = make_fly_config(workspace_root=tmp_path / "workspaces")

    outcome = await run_fly_workflow(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
        max_beads=1,
    )

    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_processed"] == 1
    assert outcome.final_output["beads_succeeded"] == 0
    assert outcome.final_output["beads_failed"] == 1

    _assert_bead_never_committed(repo, bead_id)

    # The checkout holds exactly the out-of-band mutation's content — the
    # bead's own implementation never overwrote or merged into it; the
    # conflict restore left the checkout exactly as the out-of-band commit
    # made it (SC-005).
    produced = repo.path / f"{bead_id}.txt"
    assert produced.is_file()
    assert produced.read_text(encoding="utf-8") == out_of_band_content


# ---------------------------------------------------------------------------
# Scenario 4 — environment-level check failure (the gate).
# ---------------------------------------------------------------------------


def _always_failing_stage_commands() -> dict[str, tuple[str, ...]]:
    """``DEFAULT_STAGE_COMMANDS`` replacement whose ``format`` stage always
    exits non-zero — mirrors ``noop_gate_commands()``'s
    ``[sys.executable, "-c", ...]`` idiom, inverted to fail unconditionally."""
    noop = tuple(noop_gate_commands())
    always_fail = (sys.executable, "-c", "import sys; sys.exit(1)")
    return {"format": always_fail, "lint": noop, "typecheck": noop, "test": noop}


@pytest.fixture
def patch_always_failing_gate_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    from maverick.library.actions import validation as validation_module

    monkeypatch.setattr(
        validation_module, "DEFAULT_STAGE_COMMANDS", _always_failing_stage_commands()
    )


@pytest.mark.usefixtures("patch_always_failing_gate_commands")
async def test_environment_check_failure_produces_no_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo", bead_specs=(_SOLO_BEAD,))
    # Base FlyStubRuntime raises on SubmitFixResultPayload (the happy-path
    # fixture never expects a fix call) — gate_fix's fix round therefore
    # fails immediately, abandoning the bead on the very first gate
    # failure rather than exhausting MAX_GATE_FIX_ATTEMPTS. Either route
    # is a legitimate way to make the bead ultimately fail; this is the
    # simplest one available without a custom runtime.
    stub_fly_runtime_factory(monkeypatch)
    config = make_fly_config(workspace_root=tmp_path / "workspaces")

    outcome = await run_fly_workflow(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
        max_beads=1,
    )

    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_processed"] == 1
    assert outcome.final_output["beads_succeeded"] == 0
    assert outcome.final_output["beads_failed"] == 1

    bead_id = repo.task_ids[0]
    _assert_bead_never_committed(repo, bead_id)
    # The gate ran against the checkout after a real APPLIED fold-back
    # (the implementation landed there transiently), then undo_fold_back
    # restored the checkout on gate failure — so, post-run, the file is
    # gone from the checkout just as if it had never folded back at all.
    _assert_no_implementation_file(repo, bead_id)
