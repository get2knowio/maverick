"""FR-027: a pending, unapplied delta is neither applied nor read by
``refuel --speckit`` — the refuel result is identical to the same run
with the delta absent.

The existing coverage only proves refuel is unchanged when ``deltas/``
does not exist at all, which is the easy half; this proves the harder
half — a real pending delta sitting right there changes nothing.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

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
async def test_pending_delta_is_neither_applied_nor_read(bd_repo) -> None:
    baseline_dir = make_feature_dir(bd_repo, name="052-baseline")
    with_delta_dir = make_feature_dir(bd_repo, name="052-with-delta")
    # A pending delta sitting right there, never applied.
    (with_delta_dir / "deltas" / "001-reword.md").write_text(
        "# Delta: reword\n\n**Target**: 052-with-delta\n\n"
        "## MODIFIED FR-002\n\n### Before\n\n"
        "- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
        "### After\n\n- **FR-002**: Something entirely different.\n",
        encoding="utf-8",
    )

    baseline_output = await _run(bd_repo, baseline_dir)
    with_delta_output = await _run(bd_repo, with_delta_dir)

    # Generated bead ids differ run to run; every content-derived field
    # must not.
    assert len(baseline_output["created_bead_ids"]) == len(with_delta_output["created_bead_ids"])
    for key in (
        "skipped_completed",
        "skipped_existing",
        "edge_count",
        "delta_run",
        "dry_run",
        "enriched",
        "adopted_remediation_bead_ids",
        "closed_withdrawn_bead_ids",
    ):
        assert baseline_output[key] == with_delta_output[key], key

    # Warnings carry the feature directory's own name (e.g. "no Success
    # Criteria section") — normalize that one expected difference away
    # before comparing shape/content.
    normalized_baseline = [
        w.replace("052-baseline", "<feature>") for w in baseline_output["warnings"]
    ]
    normalized_with_delta = [
        w.replace("052-with-delta", "<feature>") for w in with_delta_output["warnings"]
    ]
    assert normalized_baseline == normalized_with_delta

    # The spec.md text itself is untouched by the pending delta's content
    # — both feature dirs were seeded with the identical static fixture.
    assert (with_delta_dir / "spec.md").read_text(encoding="utf-8") == (
        baseline_dir / "spec.md"
    ).read_text(encoding="utf-8")
