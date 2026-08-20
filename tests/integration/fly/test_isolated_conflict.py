"""T059 — a fold-back conflict fails exactly one bead (contract F6, FR-034).

Produces a *genuine* jj merge conflict, not a simulated one: the checkout's
``@`` is mutated out-of-band (a real file write + a real ``jj commit``,
executed from a monkeypatched hook on ``IsolationSession.fold_back``)
between the moment the conflicting bead's workspace already holds its own
delta to a shared path and the moment ``fold_back()``'s own
``jj squash --from '<ws>@' --into @`` runs — a classic "both sides added
the same path with different content" two-sided conflict (verified by hand
against a throwaway ``jj workspace add`` repro before this test was
written: ``jj squash`` reports ``Warning: There are unresolved conflicts
at these paths: shared.txt    2-sided conflict``).

**Why this test doesn't assert "the conflicting bead never gets a commit
for the rest of the run".** ``abandon_bead``/the isolated ``fold_back``
action's ``CONFLICT`` branch mark the bead failed (``bead_aborted=True``)
without touching ``bd`` at all (no close, no label) — exactly the same
shape the *non-isolated* gate-exhaustion path already uses (see
``actions.py``'s ``gate``). A bead abandoned this way stays ``bd ready``,
so ``select_next_bead``'s next tick can and does pick it again; this was
confirmed empirically (a debug run against this exact fixture showed
``beads_processed=3`` for 2 fixture beads: the conflicting bead's failed
attempt, its own successful retry, then the other bead). That is a
faithful demonstration of G7/FR-034 ("a fold-back conflict fails *exactly
one bead*" — one attempt, not the whole run) rather than something to
engineer around: the run does not halt, does not fail any other bead, and
fully recovers. This test asserts against that real shape instead of
forcing an artificial one — see
``specs/057-isolated-bead-workspaces/contracts/fly-isolated-mode.md``
guarantee G7 and the "Failure taxonomy" table's "Fold-back conflict" row
("checkout moved under the bead" -> "bead failed, conflicting paths
named").
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from airframe.protocol import RuntimeResult

from maverick.payloads import SubmitImplementationPayload
from maverick.workspace import FoldBackOutcome, IsolationSession
from maverick.workspace.foldback import sync_workspace

from .conftest import (
    BD_UNAVAILABLE,
    JJ_UNAVAILABLE,
    FlyStubRuntime,
    _extract_bead_id,  # noqa: PLC2701 — no exported equivalent, see module docstring
    _make_cost,  # noqa: PLC2701 — no exported equivalent, see module docstring
    build_fly_repo,
    commit_descriptions_since,
    make_fly_config,
    run_fly_workflow,
    working_copy_dirt,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if BD_UNAVAILABLE or JJ_UNAVAILABLE:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)

#: A path both the conflicting bead's workspace delta and the out-of-band
#: checkout mutation write to — the shared collision point.
_SHARED_FILENAME = "shared.txt"
_OUT_OF_BAND_CONTENT = "checkout out-of-band mutation\n"


def _conflict_prone_stub_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> list[FlyStubRuntime]:
    """Like ``conftest.stub_fly_runtime_factory``, except the *first* bead
    whose implement step runs writes a fixed, shared filename
    (``shared.txt``) instead of ``FlyStubRuntime``'s normal per-bead-id
    file — that's the bead this test drives into a fold-back conflict.
    Every other bead's implement call falls back to the normal per-bead-id
    file untouched, so its fold-back stays ordinary. A retry of the
    conflicting bead itself (same bead id, see module docstring) still
    routes through the shared-filename branch, consistent with the first
    attempt.

    Which bead is "first" is discovered at runtime (the first implement
    call observed), never assumed from bead-creation order — ``bd``'s
    ready-queue ordering is an implementation detail this test does not
    need to pin down.
    """
    constructed: list[FlyStubRuntime] = []
    shared_calls: list[dict[str, Any]] = []
    conflict_bead_id: list[str] = []

    class _ConflictProneStubRuntime(FlyStubRuntime):
        async def execute(
            self, prompt: str, *, schema: Any = None, **kwargs: Any
        ) -> RuntimeResult:
            if schema is SubmitImplementationPayload:
                bead_id = _extract_bead_id(prompt)
                if not conflict_bead_id:
                    conflict_bead_id.append(bead_id)
                if bead_id == conflict_bead_id[0]:
                    self.calls.append({"prompt": prompt, "schema": schema, **kwargs})
                    target = Path.cwd() / _SHARED_FILENAME
                    target.write_text(f"implemented {bead_id}\n", encoding="utf-8")
                    self.written_files.append(target)
                    structured: dict[str, Any] = {
                        "summary": f"Implemented {bead_id}.",
                        "files_changed": [target.name],
                        "assumptions": [],
                    }
                    return RuntimeResult(
                        text="", structured=structured, cost=_make_cost(), finish="end_turn"
                    )
            return await super().execute(prompt, schema=schema, **kwargs)

    def _factory(provider_id: str) -> type[FlyStubRuntime]:
        class _Bound(_ConflictProneStubRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, calls=shared_calls, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


def _install_out_of_band_mutation(
    monkeypatch: pytest.MonkeyPatch, *, checkout: Path, content: str
) -> list[str]:
    """Monkeypatch ``IsolationSession.fold_back`` so that, the *first* time
    it is called (i.e. the conflicting bead's own fold-back), the
    checkout's ``shared.txt`` is mutated and committed out-of-band
    immediately before delegating to the real implementation — landing
    exactly between "the workspace already holds its own write to that
    path" (its implement step already ran) and "fold-back's own squash"
    (not yet run). Every subsequent call (a retry, or a different bead's
    fold-back) delegates straight through, unmodified.

    Before touching the checkout, this snapshots the *workspace*'s own
    working copy first (the same chokepoint ``fold_back()`` itself calls
    as its step 1) so the agent's plain-file write to ``shared.txt`` is
    captured into the workspace's own commit before the checkout mutation
    advances the repo-wide jj operation log. Skipping this ordering
    reproduces a real regression: any jj operation anywhere in the repo —
    including one against the checkout, an entirely different workspace —
    makes every other on-disk workspace "stale" relative to the shared
    operation log, and recovering from that staleness via
    ``jj workspace update-stale`` resets the workspace's on-disk files to
    its *last known commit* — discarding an uncommitted write that hadn't
    been snapshotted yet. Confirmed by running this test without the
    pre-mutation snapshot: the fold-back squashed an empty delta and no
    conflict occurred at all.

    Returns a list that accumulates the checkout's ``shared.txt`` content
    read immediately after any fold-back call that resolves as
    ``CONFLICT`` — the checkout has already been restored to its
    pre-squash operation by ``foldback.fold_back()`` itself by the time it
    returns, so this captures exactly what SC-005/G7 promise ("the
    checkout is left unchanged") at the moment it matters, independent of
    whatever a later retry does to that same path.
    """
    real_fold_back = IsolationSession.fold_back
    mutated = {"done": False}
    conflict_snapshots: list[str] = []

    async def _patched_fold_back(
        self: IsolationSession, lease: Any, *, fold_scope: tuple[str, ...] | None = None
    ) -> Any:
        if not mutated["done"]:
            mutated["done"] = True
            await sync_workspace(lease.workspace_path)
            shared_path = checkout / _SHARED_FILENAME
            shared_path.write_text(content, encoding="utf-8")
            subprocess.run(
                ["jj", "commit", "-m", "out-of-band: mutate shared.txt"],
                cwd=checkout,
                check=True,
                capture_output=True,
                text=True,
            )
        result = await real_fold_back(self, lease, fold_scope=fold_scope)
        if result.outcome is FoldBackOutcome.CONFLICT:
            conflict_snapshots.append((checkout / _SHARED_FILENAME).read_text(encoding="utf-8"))
        return result

    monkeypatch.setattr(IsolationSession, "fold_back", _patched_fold_back)
    return conflict_snapshots


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_fold_back_conflict_fails_exactly_one_bead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo")
    _conflict_prone_stub_runtime_factory(monkeypatch)
    conflict_snapshots = _install_out_of_band_mutation(
        monkeypatch, checkout=repo.path, content=_OUT_OF_BAND_CONTENT
    )

    config = make_fly_config(workspace_root=tmp_path / "workspaces")
    outcome = await run_fly_workflow(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
    )

    # --- Exactly one bead-attempt failed via the conflict; the run kept
    #     going and recovered — the conflicting bead's own retry and the
    #     other bead both landed (G7: "fails exactly one bead", FR-034) --
    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_failed"] == 1, outcome.final_output
    assert outcome.final_output["beads_succeeded"] == len(repo.task_ids), outcome.final_output
    assert outcome.final_output["beads_processed"] == len(repo.task_ids) + 1, outcome.final_output

    # --- Exactly one fold-back call in the whole run hit CONFLICT, and at
    #     that instant the checkout held precisely the out-of-band
    #     mutation's content for the colliding path — never a partial
    #     merge of the two sides, proving the conflict restore left the
    #     checkout exactly as the mutation left it (SC-005) -------------
    assert conflict_snapshots == [_OUT_OF_BAND_CONTENT], conflict_snapshots

    # --- Both fixture beads eventually got a commit, in order, with the
    #     normal `bead(<id>): <title>` subject + `Bead: <id>` trailer
    #     shape — the conflicting bead's per-bead file never landed
    #     (it always wrote to the shared, colliding path instead). The
    #     revset also picks up this test's own out-of-band mutation
    #     commit (it lands strictly after the baseline too) — filtered out
    #     here since it isn't a bead commit and carries no such shape ----
    all_descriptions = commit_descriptions_since(repo.path, repo.baseline_change_id)
    descriptions = [d for d in all_descriptions if d.startswith("bead(")]
    assert len(all_descriptions) == len(repo.task_ids) + 1, all_descriptions
    assert len(descriptions) == len(repo.task_ids), descriptions
    for description, task_id, title in zip(
        descriptions, repo.task_ids, repo.task_titles, strict=True
    ):
        assert description.startswith(f"bead({task_id}): {title}"), description
        assert f"\nBead: {task_id}" in description, description

    conflicting_id = repo.task_ids[0]
    surviving_id = repo.task_ids[1]
    assert not (repo.path / f"{conflicting_id}.txt").exists()
    surviving_file = repo.path / f"{surviving_id}.txt"
    assert surviving_file.is_file()
    assert surviving_file.read_text(encoding="utf-8") == f"implemented {surviving_id}\n"

    # --- The final `shared.txt` reflects the conflicting bead's own
    #     eventually-successful retry, not the stale out-of-band mutation
    #     — proving the retry's fold-back genuinely applied afterward ---
    shared_path = repo.path / _SHARED_FILENAME
    assert shared_path.is_file()
    assert shared_path.read_text(encoding="utf-8") == f"implemented {conflicting_id}\n"

    # --- No leftover workspace-fold-back dirt beyond bd's own audit log --
    dirt = working_copy_dirt(repo.path)
    assert all(path.startswith(".beads/") for path in dirt), dirt
