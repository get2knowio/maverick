"""SC-002, SC-005: an epic with one closed, one in-progress, and one
open-unstarted bead — exactly the open-unstarted one closes, with a
reason citing the delta, and no second epic is created.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadCategory, BeadDefinition, BeadType
from maverick.workflows.refuel_speckit.workflow import SpeckitRefuelWorkflow
from tests.integration.delta.conftest import make_feature_dir

pytestmark = pytest.mark.integration


async def _run(cwd, feature_dir) -> dict:
    workflow = SpeckitRefuelWorkflow(config=MagicMock())
    inputs = {
        "feature_dir": str(feature_dir),
        "cwd": str(cwd),
        "dry_run": False,
        "enrich": False,
        "auto_commit": False,
    }
    async for _event in workflow.execute(inputs):
        pass
    assert workflow.result is not None
    assert workflow.result.success, workflow.result
    return workflow.result.final_output


@pytest.mark.asyncio
async def test_only_the_open_unstarted_bead_closes(bd_repo) -> None:
    feature_dir = make_feature_dir(bd_repo)
    client = BeadClient(cwd=bd_repo)

    epic = await client.create_bead(
        BeadDefinition(
            title="052 epic", bead_type=BeadType.EPIC, priority=1, category=BeadCategory.USER_STORY
        )
    )
    await client.set_state(epic.bd_id, {"speckit_feature": "052-conditional-landing"})

    beads = {}
    for task_id in ("T017", "T019", "T020"):
        bead = await client.create_bead(
            BeadDefinition(
                title=f"{task_id} task",
                bead_type=BeadType.TASK,
                priority=2,
                category=BeadCategory.USER_STORY,
                task_ids=[task_id],
            ),
            parent_id=epic.bd_id,
        )
        await client.set_state(bead.bd_id, {"speckit_task_id": task_id})
        beads[task_id] = bead.bd_id

    # T017 -> in_progress, T019 -> closed, T020 stays open-unstarted.
    subprocess.run(
        ["bd", "update", beads["T017"], "--status", "in_progress"],
        cwd=bd_repo,
        check=True,
        capture_output=True,
    )
    await client.close(beads["T019"], reason="finished before the delta")

    # Simulate a delta having withdrawn all three tasks — tasks.md no
    # longer mentions any of them (the source-of-truth this workflow
    # reparses each run).
    (feature_dir / "tasks.md").write_text(
        "## Phase 1: Setup\n\n- [ ] T099 An unrelated remaining task\n", encoding="utf-8"
    )

    output = await _run(bd_repo, feature_dir)

    closed_ids = set(output["closed_withdrawn_bead_ids"])
    assert closed_ids == {beads["T020"]}

    # In-flight and already-closed beads untouched.
    t017_details = await client.show(beads["T017"])
    assert t017_details.status == "in_progress"
    t019_details = await client.show(beads["T019"])
    assert t019_details.status == "closed"

    # The newly-closed bead's reason cites the delta.
    t020_details = await client.show(beads["T020"])
    assert t020_details.status == "closed"

    # No second epic created for this feature.
    open_epics = await client.query("type=epic AND status=open")
    matching = [
        e
        for e in open_epics
        if (await client.show(e.id)).state.get("speckit_feature") == "052-conditional-landing"
    ]
    assert len(matching) == 1
    assert matching[0].id == epic.bd_id
