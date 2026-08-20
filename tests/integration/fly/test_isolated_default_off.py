"""T055 — isolated mode defaults off (contract F3, FR-035, SC-011).

``build_fly_application``'s isolated-mode params are opt-in
(``isolated: bool = False``) and ``FlyBeadsWorkflow._run`` reads the input
via ``bool(inputs.get("isolated", False))`` — so a caller that never
mentions isolation at all (the shape every pre-057 caller used, and what
the CLI itself sends absent both ``--isolated`` and a configured
``workspace.enabled``) must produce byte-identical behavior to before this
feature existed (FR-035, SC-011): the non-isolated Burr transition table
(``_NON_ISOLATED_TRANSITIONS`` in ``burr_graph.py``), the same commit
shape, and — the sharpest possible proof that isolation never engaged —
zero filesystem activity under the configured workspace root, since only
the isolated path ever touches it.

This is deliberately the *same* happy-path shape T053 exercises on its
non-isolated side (build repo, stub runtime, run one bead to a commit);
the point here isn't a new scenario, it's confirming the omitted-input
default resolves to exactly that unchanged behavior — consistent with the
task's own framing that this test "can literally run the same assertions
as an existing non-isolated fly integration/unit test."
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from .conftest import (
    BD_UNAVAILABLE,
    JJ_UNAVAILABLE,
    BeadSpec,
    build_fly_repo,
    make_fly_config,
    run_fly_workflow,
    stub_fly_runtime_factory,
    working_copy_dirt,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if BD_UNAVAILABLE or JJ_UNAVAILABLE:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)

_SOLO_BEAD = BeadSpec(
    title="Add solo module", description="Implement the solo module.", priority=1
)


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_fly_with_isolated_key_omitted_behaves_exactly_like_before_057(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo", bead_specs=(_SOLO_BEAD,))
    stub_fly_runtime_factory(monkeypatch)
    # A workspace root IS configured (proving isolation *could* engage if
    # anything mistakenly triggered it) — but never referenced, because
    # "isolated" is never passed to run_fly_workflow below.
    workspace_root = tmp_path / "workspaces"
    config = make_fly_config(workspace_root=workspace_root)

    outcome = await run_fly_workflow(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=None,  # omit the key entirely — see conftest.run_fly_workflow
        monkeypatch=monkeypatch,
    )

    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_succeeded"] == 1
    assert outcome.final_output["beads_failed"] == 0
    assert outcome.final_output["beads_processed"] == 1

    # --- Exactly the commit shape the non-isolated path has always made ---
    task_id = repo.task_ids[0]
    revset = f"{repo.baseline_change_id}..@-"
    result = _jj(["log", "-r", revset, "--no-graph", "-T", "description"], repo.path)
    assert result.startswith(f"bead({task_id}): {repo.task_titles[0]}"), result
    assert f"\nBead: {task_id}" in result, result
    # Exactly one bead commit landed between the baseline and @- — a
    # second, unexpected commit would mean something (e.g. a stray
    # fold-back/undo artifact) leaked in from the isolated code path.
    assert result.count("bead(") == 1, result

    # --- The bead's file landed directly in the checkout -------------------
    produced = repo.path / f"{task_id}.txt"
    assert produced.is_file()
    assert produced.read_text(encoding="utf-8") == f"implemented {task_id}\n"

    # --- Zero isolation-primitive activity: the configured workspace root
    #     was never created, let alone written to — the sharpest possible
    #     proof this run never took the isolated path at all (FR-035).
    assert not workspace_root.exists(), list(workspace_root.rglob("*"))

    # --- No leftover workspace-fold-back dirt: whatever's left in the
    #     working copy is at most bd's own post-close audit log (see
    #     conftest.working_copy_dirt) -----------------------------------
    dirt = working_copy_dirt(repo.path)
    assert all(path.startswith(".beads/") for path in dirt), dirt


def _jj(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["jj", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout
