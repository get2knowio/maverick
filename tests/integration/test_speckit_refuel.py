"""Integration test: Spec Kit ingestion against a real ``bd`` database.

Automates quickstart.md Scenario 2 (fresh ingest + ready-order) and
Scenario 4 (delta re-run + no-op), exercising the real ``bd`` CLI rather
than a stub. Skips entirely when ``bd`` isn't on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from maverick.beads.client import BeadClient
from maverick.workflows.refuel_speckit.workflow import SpeckitRefuelWorkflow

pytestmark = pytest.mark.integration

#: SC-001: ingestion of a typical feature completes in < 30s wall clock.
_SC_001_BOUND_SECONDS = 30.0

_TASKS_MD = """\
## Phase 1: Setup

- [ ] T001 Initialize project
- [ ] T002 [P] Create config file in src/config.py

## Phase 2: Core

- [ ] T003 Implement core feature in src/core.py
- [ ] T004 [P] Add supporting util in src/util.py
"""
_SPEC_MD = """\
# Feature Specification: Integration Sample

## Success Criteria

### Measurable Outcomes

- **SC-001**: The feature works end to end.
"""

if shutil.which("bd") is None:
    pytest.skip("bd CLI not available on PATH", allow_module_level=True)


@pytest.fixture
def bd_repo(tmp_path: Path) -> Path:
    """A tmp directory with a real, initialized ``bd`` database."""
    subprocess.run(
        ["bd", "init", "--non-interactive"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


def _make_feature_dir(cwd: Path, name: str = "048-integration-sample") -> Path:
    feature_dir = cwd / "specs" / name
    feature_dir.mkdir(parents=True)
    (feature_dir / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    (feature_dir / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    return feature_dir


async def _run(cwd: Path, feature_dir: Path, **overrides: object) -> dict[str, object]:
    workflow = SpeckitRefuelWorkflow(config=MagicMock())
    inputs: dict[str, object] = {
        "feature_dir": str(feature_dir),
        "cwd": str(cwd),
        "dry_run": False,
        "enrich": False,
        "auto_commit": False,
    }
    inputs.update(overrides)
    async for _event in workflow.execute(inputs):
        pass
    assert workflow.result is not None
    assert workflow.result.success, workflow.result
    output = workflow.result.final_output
    assert isinstance(output, dict)
    return output


@pytest.mark.asyncio
async def test_speckit_refuel_lifecycle(bd_repo: Path) -> None:
    feature_dir = _make_feature_dir(bd_repo)
    client = BeadClient(cwd=bd_repo)

    # --- Scenario 2: fresh ingest -------------------------------------
    start = time.monotonic()
    output = await _run(bd_repo, feature_dir)
    elapsed = time.monotonic() - start
    if elapsed > _SC_001_BOUND_SECONDS:
        import warnings

        warnings.warn(
            f"speckit ingestion took {elapsed:.1f}s, exceeding the SC-001 "
            f"{_SC_001_BOUND_SECONDS}s bound",
            stacklevel=1,
        )

    epic_id = output["epic_id"]
    assert len(output["created_bead_ids"]) == 4

    epic_details = await client.show(epic_id)
    assert epic_details.state.get("speckit_feature") == "048-integration-sample"
    assert "speckit" in epic_details.labels

    children = await client.children(epic_id)
    assert len(children) == 4

    # SC-003: bd ready only surfaces phase-1 sources (T001, T002) — not
    # phase-2 tasks, which are blocked by the phase barrier.
    ready = await client.ready(epic_id, limit=10)
    ready_titles = {r.title for r in ready}
    assert any(t.startswith("T001:") for t in ready_titles) or any(
        t.startswith("T002:") for t in ready_titles
    )
    assert not any(t.startswith("T003:") for t in ready_titles)
    assert not any(t.startswith("T004:") for t in ready_titles)

    # --- Scenario 4: delta append --------------------------------------
    tasks_path = feature_dir / "tasks.md"
    tasks_path.write_text(
        tasks_path.read_text(encoding="utf-8")
        + "\n## Phase 3: Polish\n\n- [ ] T005 [P] Add docs in src/docs.py\n",
        encoding="utf-8",
    )

    delta_output = await _run(bd_repo, feature_dir)
    assert delta_output["delta_run"] is True
    assert delta_output["epic_id"] == epic_id
    assert len(delta_output["created_bead_ids"]) == 1
    assert set(delta_output["skipped_existing"]) == {"T001", "T002", "T003", "T004"}

    # --- Scenario 4: no-op ----------------------------------------------
    noop_output = await _run(bd_repo, feature_dir)
    assert noop_output["created_bead_ids"] == []
    assert noop_output["delta_run"] is True

    open_epics = await client.query("type=epic AND status=open")
    matching = [
        e
        for e in open_epics
        if (await client.show(e.id)).state.get("speckit_feature") == "048-integration-sample"
    ]
    assert len(matching) == 1
