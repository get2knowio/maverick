"""T053 — isolated ↔ normal equivalence (contract F1, SC-001, FR-033).

The single most load-bearing test in 057-isolated-bead-workspaces: run the
same beads from the same starting repo state twice — once through the
normal (non-isolated) fly graph, once through the isolated graph — and
assert the two runs produce identical commit subjects, trailers, ordering,
and final tracked file contents (contract ``fly-isolated-mode.md``'s G5,
and the "Ordering note" under "Per-bead sequence": isolated mode runs the
gate *after* review instead of right after implement, which is a
deliberate internal step-order difference that must NOT show up in the
resulting history this test compares).

See ``specs/057-isolated-bead-workspaces/quickstart.md`` Scenario 2 for
the manual-run version of what this test automates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import (
    BD_UNAVAILABLE,
    JJ_UNAVAILABLE,
    build_fly_repo,
    clone_fly_repo,
    commit_descriptions_since,
    make_fly_config,
    run_fly_workflow,
    stub_fly_runtime_factory,
    working_copy_dirt,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if BD_UNAVAILABLE or JJ_UNAVAILABLE:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)


def _normalize(description: str, *, epic_id: str, task_ids: tuple[str, ...]) -> str:
    """Replace this run's own (randomly-suffixed, per-repo) bead IDs with
    positional placeholders so two independently-``bd init``'d repos'
    commit descriptions can be compared byte-for-byte.

    Only the literal ID tokens are substituted — subject text, trailer
    labels/shape, tags, and whitespace are left completely alone, so this
    normalization cannot mask a real difference in anything contract F1
    actually cares about (subjects, trailers, ordering).
    """
    normalized = description
    for i, task_id in enumerate(task_ids):
        normalized = normalized.replace(task_id, f"<TASK-{i}>")
    normalized = normalized.replace(epic_id, "<EPIC>")
    return normalized


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_isolated_and_normal_runs_produce_identical_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = build_fly_repo(tmp_path / "base")
    normal_repo = clone_fly_repo(base, tmp_path / "normal")
    isolated_repo = clone_fly_repo(base, tmp_path / "isolated")

    # --- Normal run -------------------------------------------------------
    stub_fly_runtime_factory(monkeypatch)
    normal_config = make_fly_config()
    normal_outcome = await run_fly_workflow(
        config=normal_config,
        cwd=normal_repo.path,
        epic_id=normal_repo.epic_id,
        isolated=False,
        monkeypatch=monkeypatch,
    )
    assert normal_outcome.success is True, normal_outcome.final_output
    assert normal_outcome.final_output is not None
    assert normal_outcome.final_output["beads_succeeded"] == len(base.task_ids)
    assert normal_outcome.final_output["beads_failed"] == 0

    # --- Isolated run — independent stub runtime, independent monkeypatch
    #     scope, same fixture-driven behavior --------------------------
    stub_fly_runtime_factory(monkeypatch)
    isolated_config = make_fly_config(workspace_root=tmp_path / "workspaces")
    isolated_outcome = await run_fly_workflow(
        config=isolated_config,
        cwd=isolated_repo.path,
        epic_id=isolated_repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
    )
    assert isolated_outcome.success is True, isolated_outcome.final_output
    assert isolated_outcome.final_output is not None
    assert isolated_outcome.final_output["beads_succeeded"] == len(base.task_ids)
    assert isolated_outcome.final_output["beads_failed"] == 0

    # --- Same number of beads processed the same way ----------------------
    assert (
        normal_outcome.final_output["beads_succeeded"]
        == isolated_outcome.final_output["beads_succeeded"]
    )

    # --- Identical commit subjects + trailers + ordering (G5, SC-001) -----
    normal_descriptions = commit_descriptions_since(normal_repo.path, base.baseline_change_id)
    isolated_descriptions = commit_descriptions_since(isolated_repo.path, base.baseline_change_id)
    assert len(normal_descriptions) == len(base.task_ids), normal_descriptions
    assert len(isolated_descriptions) == len(base.task_ids), isolated_descriptions

    normalized_normal = [
        _normalize(d, epic_id=normal_repo.epic_id, task_ids=normal_repo.task_ids)
        for d in normal_descriptions
    ]
    normalized_isolated = [
        _normalize(d, epic_id=isolated_repo.epic_id, task_ids=isolated_repo.task_ids)
        for d in isolated_descriptions
    ]
    assert normalized_normal == normalized_isolated

    # Every commit carries the `bead(<id>): <title>` subject + `Bead: <id>`
    # trailer shape the contract's G5 names, self-consistently (the id in
    # the subject line is the same id the trailer names) — checked against
    # each run's own (real, unnormalized) ids.
    for descriptions, repo in (
        (normal_descriptions, normal_repo),
        (isolated_descriptions, isolated_repo),
    ):
        for description, task_id, title in zip(
            descriptions, repo.task_ids, repo.task_titles, strict=True
        ):
            assert description.startswith(f"bead({task_id}): {title}"), description
            assert f"\nBead: {task_id}" in description, description

    # --- Identical final tracked file contents -----------------------------
    for task_id_normal, task_id_isolated in zip(
        normal_repo.task_ids, isolated_repo.task_ids, strict=True
    ):
        normal_file = normal_repo.path / f"{task_id_normal}.txt"
        isolated_file = isolated_repo.path / f"{task_id_isolated}.txt"
        assert normal_file.is_file(), f"normal run never wrote {normal_file}"
        assert isolated_file.is_file(), f"isolated run never wrote {isolated_file}"
        # Content embeds each run's own bead id (see FlyStubRuntime) —
        # normalize the same way as the commit descriptions above.
        assert normal_file.read_text(encoding="utf-8").replace(
            task_id_normal, "<TASK>"
        ) == isolated_file.read_text(encoding="utf-8").replace(task_id_isolated, "<TASK>")

    # --- No leftover workspace-fold-back dirt: whatever's left in the
    #     working copy is at most bd's own post-close audit log, never a
    #     stray bead-produced file or an un-folded-back workspace delta -
    for repo in (normal_repo, isolated_repo):
        dirt = working_copy_dirt(repo.path)
        assert all(path.startswith(".beads/") for path in dirt), dirt
