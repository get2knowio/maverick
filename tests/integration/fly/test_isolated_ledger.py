"""T060 — isolated-bead assumptions land in the checkout's ledger (contract
F7, FR-020).

Exercises ``fly-isolated-mode.md``'s guarantee G6 ("bead, ledger, and
assumption writes target the checkout, never the workspace"): a bead
processed through the isolated pipeline (implement -> ac/spec check ->
review, all inside its own jj workspace) that reports an assumption in its
``submit_implementation`` payload must still end up with a real ledger bead
in the **checkout's** bd database, wired with a ``discovered-from`` edge
back to the implementing bead, and stamped with the same jj change id the
bead's commit landed under -- and the per-bead workspace that produced it
must be gone by the time the run completes (fly's ``IsolationPolicy`` has
``reuse=False``, torn down on every successfully-processed bead).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from airframe.cost import CostRecord
from airframe.protocol import RuntimeResult

from maverick.assumptions.models import (
    KEY_CHANGE_IDS,
    KEY_SOURCE_BEAD,
    KEY_STATUS,
    STATUS_OPEN,
)
from maverick.beads.client import BeadClient
from maverick.payloads import SubmitImplementationPayload
from maverick.workspace.lifecycle import workspace_dir

from .conftest import (
    BD_UNAVAILABLE,
    JJ_UNAVAILABLE,
    BeadSpec,
    FlyStubRuntime,
    build_fly_repo,
    make_fly_config,
    run_fly_workflow,
    working_copy_dirt,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if BD_UNAVAILABLE or JJ_UNAVAILABLE:
    pytest.skip("bd/jj CLI not available on PATH", allow_module_level=True)

_SOLO_BEAD = BeadSpec(
    title="Add ledger module", description="Implement the ledger module.", priority=1
)

_ASSUMPTION_QUESTION = "Should the retry backoff default to 2 seconds?"
_ASSUMPTION_ANSWER = "Yes -- matches the existing retry helper's default."

_BEAD_ID_RE = re.compile(r"^## Bead: (\S+)", re.MULTILINE)


def _extract_bead_id(prompt: str) -> str:
    """Local copy of ``conftest._extract_bead_id`` (private, not exported)."""
    match = _BEAD_ID_RE.search(prompt)
    if match is None:
        raise AssertionError(f"could not find '## Bead: <id>' in prompt: {prompt[:200]!r}")
    return match.group(1)


def _make_cost() -> CostRecord:
    """Local copy of ``conftest._make_cost`` (private, not exported)."""
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


class _AssumptionReportingStubRuntime(FlyStubRuntime):
    """``FlyStubRuntime`` whose implement handler also reports one
    low-severity assumption alongside its normal file write.

    Low severity (rather than medium/high) deliberately avoids the
    "blocks downstream epic" wiring (``_wire_high_blocks_edge`` in
    ``assumptions/ledger.py``) -- irrelevant to what this test checks and
    would need a second spec/epic in the fixture to observe.
    """

    async def execute(self, prompt: str, *, schema: Any = None, **kwargs: Any) -> RuntimeResult:
        self.calls.append({"prompt": prompt, "schema": schema, **kwargs})

        if schema is SubmitImplementationPayload:
            bead_id = _extract_bead_id(prompt)
            target = Path.cwd() / f"{bead_id}.txt"
            target.write_text(f"implemented {bead_id}\n", encoding="utf-8")
            self.written_files.append(target)
            structured: dict[str, Any] = {
                "summary": f"Implemented {bead_id}.",
                "files_changed": [target.name],
                "assumptions": [
                    {
                        "question": _ASSUMPTION_QUESTION,
                        "adopted_answer": _ASSUMPTION_ANSWER,
                        "alternatives": [],
                        "severity": "low",
                    }
                ],
            }
            return RuntimeResult(
                text="", structured=structured, cost=_make_cost(), finish="end_turn"
            )

        return await super().execute(prompt, schema=schema, **kwargs)


def _assumption_stub_runtime_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> list[_AssumptionReportingStubRuntime]:
    """Local sibling of ``conftest.stub_fly_runtime_factory`` binding
    ``_AssumptionReportingStubRuntime`` instead of the bare stub -- kept
    local per this test file's constraint of never touching ``conftest.py``.
    """
    constructed: list[_AssumptionReportingStubRuntime] = []
    shared_calls: list[dict[str, Any]] = []

    def _factory(provider_id: str) -> type[_AssumptionReportingStubRuntime]:
        class _Bound(_AssumptionReportingStubRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, calls=shared_calls, **kwargs)
                constructed.append(self)

        return _Bound

    monkeypatch.setattr("airframe.runtime_for", _factory)
    return constructed


def _jj(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["jj", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.mark.usefixtures("patch_default_gate_commands")
async def test_isolated_bead_assumption_lands_in_checkout_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = build_fly_repo(tmp_path / "repo", bead_specs=(_SOLO_BEAD,))
    workspace_root = tmp_path / "workspaces"
    _assumption_stub_runtime_factory(monkeypatch)
    config = make_fly_config(workspace_root=workspace_root)

    outcome = await run_fly_workflow(
        config=config,
        cwd=repo.path,
        epic_id=repo.epic_id,
        isolated=True,
        monkeypatch=monkeypatch,
    )

    assert outcome.success is True, outcome.final_output
    assert outcome.final_output is not None
    assert outcome.final_output["beads_succeeded"] == 1
    assert outcome.final_output["beads_failed"] == 0

    task_id = repo.task_ids[0]

    # --- The bead's commit landed directly in the checkout, exactly like
    #     the non-isolated path (G5) --------------------------------------
    revset = f"{repo.baseline_change_id}..@-"
    description = _jj(["log", "-r", revset, "--no-graph", "-T", "description"], repo.path)
    assert description.startswith(f"bead({task_id}): {repo.task_titles[0]}"), description
    assert f"\nBead: {task_id}" in description, description
    change_id = _jj(["log", "-r", revset, "--no-graph", "-T", "change_id"], repo.path).strip()
    assert change_id

    # --- G6 / F7 point 1: a new assumption bead exists in the checkout's
    #     ledger, with the question/adopted_answer we supplied ------------
    client = BeadClient(cwd=repo.path)
    candidates = await client.query("label=assumption")
    assert len(candidates) == 1, candidates
    entry_id = candidates[0].id

    entry_details = await client.show(entry_id)
    assert "assumption" in entry_details.labels
    assert "assumption-review" in entry_details.labels
    assert "needs-human-review" in entry_details.labels
    assert _ASSUMPTION_QUESTION in entry_details.description
    assert _ASSUMPTION_ANSWER in entry_details.description
    assert entry_details.state[KEY_STATUS] == STATUS_OPEN
    assert entry_details.state[KEY_SOURCE_BEAD] == task_id

    # discovered-from edge back to the implementing bead.
    dep_result = subprocess.run(
        ["bd", "dep", "list", entry_id, "--json"],
        cwd=repo.path,
        capture_output=True,
        text=True,
        check=True,
    )
    deps = json.loads(dep_result.stdout)
    assert any(
        d.get("dependency_type") == "discovered-from" and d.get("id") == task_id for d in deps
    ), deps

    # --- F7 point 2: stamped with the exact change id the bead's commit
    #     landed under, cross-checked against the real jj log -------------
    change_ids = entry_details.state[KEY_CHANGE_IDS].split(",")
    assert change_ids == [change_id], entry_details.state

    # --- F7 point 3: the ledger bead is visible from a fresh BeadClient
    #     query rooted at the checkout, and the per-bead workspace that
    #     produced it is gone -- not left behind, and never itself the
    #     thing satisfying the query above (BeadClient(cwd=repo.path) only
    #     ever talks to the checkout's own .beads/, never a workspace's) --
    fresh_client = BeadClient(cwd=repo.path)
    reshown = await fresh_client.show(entry_id)
    assert reshown.id == entry_id

    per_bead_workspace = workspace_dir(
        root=workspace_root, checkout=repo.path, workflow="fly", key=task_id
    )
    assert not per_bead_workspace.exists(), (
        f"per-bead workspace {per_bead_workspace} still exists after a successful run -- "
        "fly's IsolationPolicy has reuse=False and should have torn it down"
    )

    # --- No leftover workspace-fold-back dirt in the checkout -------------
    dirt = working_copy_dirt(repo.path)
    assert all(path.startswith(".beads/") for path in dirt), dirt
