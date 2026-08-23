"""SC-003: the whole sequence — parse -> validate -> impacts -> apply ->
archive -> ``refuel --speckit`` — makes zero model calls.

Patches ``runtime_for_agent`` to raise; asserting only the ingestion leg
would leave the other five unproven, and this feature's entire premise is
that none of them needs a model.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadCategory, BeadDefinition, BeadType
from maverick.speckit.delta.apply import apply_delta
from maverick.speckit.delta.parser import parse_delta_md
from maverick.speckit.delta.validate import validate_delta
from maverick.speckit.parser import parse_tasks_md
from maverick.speckit.requirements import parse_requirements
from maverick.workflows.refuel_speckit.workflow import SpeckitRefuelWorkflow
from tests.integration.delta.conftest import make_feature_dir

pytestmark = pytest.mark.integration


def _explode(*args, **kwargs):
    raise AssertionError("runtime_for_agent was called — this path must make zero model calls")


@pytest.mark.asyncio
async def test_full_sequence_makes_zero_model_calls(bd_repo) -> None:
    feature_dir = make_feature_dir(bd_repo)
    client = BeadClient(cwd=bd_repo)

    with patch("maverick.runtime.agent_factory.runtime_for_agent", side_effect=_explode):
        epic = await client.create_bead(
            BeadDefinition(
                title="052 epic",
                bead_type=BeadType.EPIC,
                priority=1,
                category=BeadCategory.USER_STORY,
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

        delta_text = (
            "# Delta: full sequence\n\n**Target**: 052-conditional-landing\n\n"
            "## MODIFIED FR-002\n\n### Before\n\n"
            "- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
            "### After\n\n- **FR-002**: The gate MUST evaluate the assumption frontier "
            "before any curation step runs.\n\n"
            "## TASKS\n\n- WITHDRAWN: T017\n"
        )
        delta_path = feature_dir / "deltas" / "001-full.md"
        delta_path.write_text(delta_text, encoding="utf-8")

        # 1. parse
        document = parse_delta_md(delta_text, path=delta_path)

        # 2. validate
        section = parse_requirements(
            (feature_dir / "spec.md").read_text(encoding="utf-8"), file="spec.md"
        )
        phases, _ = parse_tasks_md(
            (feature_dir / "tasks.md").read_text(encoding="utf-8"), file="tasks.md"
        )
        problems = validate_delta(document, spec_section=section, tasks_phases=phases)
        assert problems == ()

        # 3+4+5. impacts + apply + archive (apply_delta does all three)
        outcome = await apply_delta(
            document, document_text=delta_text, feature_dir=feature_dir, client=client
        )
        # T017 is open-and-unstarted -> no impact -> applies straight through.
        assert outcome.status == "applied"
        assert outcome.tasks.withdrawn == ("T017",)

        # 6. refuel --speckit
        workflow = SpeckitRefuelWorkflow(config=MagicMock())
        inputs = {
            "feature_dir": str(feature_dir),
            "cwd": str(bd_repo),
            "dry_run": False,
            "enrich": False,
            "auto_commit": False,
        }
        async for _event in workflow.execute(inputs):
            pass
        assert workflow.result is not None
        assert workflow.result.success, workflow.result

    output = workflow.result.final_output
    assert task.bd_id in output["closed_withdrawn_bead_ids"]
    closed_details = await client.show(task.bd_id)
    assert closed_details.status == "closed"
