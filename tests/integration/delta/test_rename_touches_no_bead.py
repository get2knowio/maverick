"""SC-009: a RENAMED-only delta touches zero beads.

A rename changes an identifier in spec.md; treating it as remove-plus-add
would close and recreate beads, which is exactly the lineage loss FR-002a
exists to prevent.
"""

from __future__ import annotations

import subprocess

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadCategory, BeadDefinition, BeadType
from maverick.speckit.delta.apply import apply_delta
from maverick.speckit.delta.parser import parse_delta_md
from tests.integration.delta.conftest import git_commit_all, make_feature_dir

pytestmark = pytest.mark.integration

_ALL_STATUSES_QUERY = (
    "status=open OR status=in_progress OR status=blocked OR status=deferred OR status=closed"
)


@pytest.mark.asyncio
async def test_rename_only_delta_leaves_every_bead_untouched(bd_repo) -> None:
    feature_dir = make_feature_dir(bd_repo)
    # spec.md needs an FR-018 for the rename to target — add one.
    spec_path = feature_dir / "spec.md"
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace(
            "- **FR-021**:", "- **FR-018**: A requirement due to be renamed.\n- **FR-021**:"
        ),
        encoding="utf-8",
    )

    client = BeadClient(cwd=bd_repo)
    epic = await client.create_bead(
        BeadDefinition(
            title="052 epic", bead_type=BeadType.EPIC, priority=1, category=BeadCategory.USER_STORY
        )
    )
    await client.set_state(epic.bd_id, {"speckit_feature": "052-conditional-landing"})
    task = await client.create_bead(
        BeadDefinition(
            title="T017 task",
            bead_type=BeadType.TASK,
            priority=2,
            category=BeadCategory.USER_STORY,
            task_ids=["T017"],
        ),
        parent_id=epic.bd_id,
    )
    await client.set_state(task.bd_id, {"speckit_task_id": "T017"})
    subprocess.run(
        ["bd", "update", task.bd_id, "--status", "in_progress"],
        cwd=bd_repo,
        check=True,
        capture_output=True,
    )
    git_commit_all(bd_repo)

    before = await client.query(_ALL_STATUSES_QUERY)
    before_snapshot = sorted((b.id, b.status, b.title) for b in before)

    delta_text = (
        "# Delta: rename\n\n**Target**: 052-conditional-landing\n\n"
        "## RENAMED\n\n- FROM: FR-018\n- TO: FR-019\n"
    )
    delta_path = feature_dir / "deltas" / "001-rename.md"
    delta_path.write_text(delta_text, encoding="utf-8")
    document = parse_delta_md(delta_text, path=delta_path)

    outcome = await apply_delta(
        document, document_text=delta_text, feature_dir=feature_dir, client=client
    )
    assert outcome.status == "applied"
    assert outcome.requirements.renamed == (("FR-018", "FR-019"),)

    after = await client.query(_ALL_STATUSES_QUERY)
    after_snapshot = sorted((b.id, b.status, b.title) for b in after)

    assert before_snapshot == after_snapshot

    new_spec = spec_path.read_text(encoding="utf-8")
    assert "FR-019" in new_spec
    assert "FR-018" not in new_spec
