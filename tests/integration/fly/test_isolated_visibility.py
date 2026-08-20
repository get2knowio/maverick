"""T054 — the checkout never contains an in-flight bead's changes
(contract F2, FR-007, SC-002; contract fly-isolated-mode.md's guarantees
G2 and G3).

``maverick fly --isolated`` provisions a per-bead jj workspace and runs
``implement``/``ac_check``/``spec_check``/``review`` (+ fix rounds)
entirely inside it (``_isolation.agent_step_scope`` chdirs the process
there for every agent call); only after ``review`` succeeds does
``fold_back`` move the workspace delta into the checkout. G2 says the
checkout must hold **nothing** from a bead whose agent step is still
executing; G3 says beads are strictly serial — no unit begins while
another's delta is unverified in the checkout.

This test can't literally poll the checkout from a separate thread mid-run
(the fixture drives the whole workflow to completion in one ``await``), so
it observes G2/G3 from *inside* the run instead, at the two seams where a
bead's file could leak into the checkout early:

1. ``FlyStubRuntime.execute``'s ``SubmitImplementationPayload`` handler
   writes ``<bead-id>.txt`` to ``Path.cwd()`` — the workspace, thanks to
   ``chdir_scope``. A thin local subclass wraps that handler and checks,
   at the exact moment the write lands, that the *checkout* (a real,
   independently-tracked path, not ``Path.cwd()``) does not yet contain
   that file, and that every bead ordered before this one already does
   (G3 — strict serialization, checked from the same observation point).
2. ``IsolationSession.fold_back`` is wrapped so that, immediately before
   delegating to the real implementation, it re-checks the same
   not-yet-present condition for the bead about to be folded back.

Violations are collected rather than raised in place — raising from
inside the stub runtime would be swallowed by
``_call_implementer_with_escalation``'s non-transient ``except
Exception`` (it becomes an ordinary bead failure, not a loud test
failure) — so this test asserts on the collected list itself, after the
run, giving a precise, unambiguous failure message naming the exact bead
and path if G2/G3 is ever violated for real.

Uses the harness's default 2-bead fixture so bead 2's in-flight check can
also assert bead 1's file is *already* committed in the checkout by then
— proving the checkout only ever reflects committed beads, never the
currently-executing one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from airframe.protocol import RuntimeResult

from maverick.payloads import SubmitImplementationPayload
from maverick.workspace.models import IsolationLease
from maverick.workspace.session import IsolationSession

from .conftest import (
    BD_UNAVAILABLE,
    JJ_UNAVAILABLE,
    FlyStubRuntime,
    build_fly_repo,
    make_fly_config,
    run_fly_workflow,
    working_copy_dirt,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if BD_UNAVAILABLE or JJ_UNAVAILABLE:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)

_BEAD_ID_RE = re.compile(r"^## Bead: (\S+)", re.MULTILINE)


def _extract_bead_id(prompt: str) -> str:
    match = _BEAD_ID_RE.search(prompt)
    if match is None:
        raise AssertionError(f"could not find '## Bead: <id>' in prompt: {prompt[:200]!r}")
    return match.group(1)


def _guarded_stub_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    checkout: Path,
    task_order: tuple[str, ...],
    violations: list[str],
) -> list[FlyStubRuntime]:
    """Like ``conftest.stub_fly_runtime_factory``, but wraps the
    implement-payload handler with a G2/G3 checkout-visibility check at
    the exact moment each bead's file is written into its workspace.
    """
    constructed: list[FlyStubRuntime] = []
    shared_calls: list[dict[str, Any]] = []

    class _GuardedRuntime(FlyStubRuntime):
        async def execute(
            self, prompt: str, *, schema: Any = None, **kwargs: Any
        ) -> RuntimeResult:
            result = await super().execute(prompt, schema=schema, **kwargs)
            if schema is SubmitImplementationPayload:
                bead_id = _extract_bead_id(prompt)

                # G2: the checkout must not yet hold this bead's file —
                # its delta lives only in the workspace until fold_back.
                in_flight_file = checkout / f"{bead_id}.txt"
                if in_flight_file.exists():
                    violations.append(
                        f"G2 violation: checkout already contained "
                        f"{in_flight_file} while bead {bead_id}'s implement "
                        "step was still executing"
                    )

                # G3: strict serialization — every bead ordered before
                # this one must already be committed in the checkout.
                for earlier_id in task_order:
                    if earlier_id == bead_id:
                        break
                    earlier_file = checkout / f"{earlier_id}.txt"
                    if not earlier_file.is_file():
                        violations.append(
                            f"G3 violation: earlier bead's file {earlier_file} "
                            f"is missing from the checkout while bead {bead_id} "
                            "was executing — beads did not stay strictly serial"
                        )
            return result

    def _factory(provider_id: str) -> type[FlyStubRuntime]:
        class _Bound(_GuardedRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, calls=shared_calls, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


def _guard_fold_back(
    monkeypatch: pytest.MonkeyPatch, *, checkout: Path, violations: list[str]
) -> None:
    """Wrap ``IsolationSession.fold_back`` so that, immediately before a
    bead's delta is moved into the checkout, we re-confirm the checkout
    did not already contain that bead's file — the second, independent
    observation point the task calls for alongside the runtime-level one.
    """
    original_fold_back = IsolationSession.fold_back

    async def _guarded(
        self: IsolationSession,
        lease: IsolationLease,
        *,
        fold_scope: tuple[str, ...] | None = None,
    ) -> Any:
        bead_id = lease.unit.key
        pre_fold_file = checkout / f"{bead_id}.txt"
        if pre_fold_file.exists():
            violations.append(
                f"G2 violation: checkout already contained {pre_fold_file} "
                f"immediately before fold_back ran for bead {bead_id}"
            )
        return await original_fold_back(self, lease, fold_scope=fold_scope)

    monkeypatch.setattr(IsolationSession, "fold_back", _guarded)


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_checkout_never_shows_an_in_flight_beads_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo")
    checkout = repo.path
    violations: list[str] = []

    _guarded_stub_runtime_factory(
        monkeypatch,
        checkout=checkout,
        task_order=repo.task_ids,
        violations=violations,
    )
    _guard_fold_back(monkeypatch, checkout=checkout, violations=violations)

    config = make_fly_config(workspace_root=tmp_path / "workspaces")
    outcome = await run_fly_workflow(
        config=config,
        cwd=checkout,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
    )

    # --- No G2/G3 violation was ever observed during the run --------------
    assert violations == [], "\n".join(violations)

    # --- The run itself completed successfully, both beads landed ---------
    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_succeeded"] == len(repo.task_ids) == 2
    assert outcome.final_output["beads_failed"] == 0

    # --- Post-run: the checkout now holds every bead's file, since every
    #     bead finished (fold_back + commit) by the time the run ended ----
    for task_id in repo.task_ids:
        produced = checkout / f"{task_id}.txt"
        assert produced.is_file(), f"expected {produced} to exist after the run completed"
        assert produced.read_text(encoding="utf-8") == f"implemented {task_id}\n"

    # --- No leftover workspace-fold-back dirt in the checkout -------------
    dirt = working_copy_dirt(checkout)
    assert all(path.startswith(".beads/") for path in dirt), dirt
