"""Integration test: assumption ledger against real ``bd`` + ``jj``.

Automates quickstart.md Scenario 1 (record → commit → stamped entry;
abandoned bead → unstamped entry), Scenario 3 (medium blocks the land
gate until answered), Scenario 4 (high blocks the next spec's epic,
released by waive), and FR-013 legacy compatibility (a pre-feature
escalation bead flows through brief/review/the land gate without
errors) against real CLIs rather than stubs. Skips entirely when ``bd``
isn't on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from maverick.assumptions.ledger import (
    answer,
    open_blocking_entries,
    open_high_entries_before,
    record_assumption,
    stamp_change_id,
    waive,
)
from maverick.assumptions.models import KEY_CHANGE_IDS, KEY_STATUS, STATUS_OPEN
from maverick.beads.client import BeadClient
from maverick.beads.models import (
    BeadCategory,
    BeadDefinition,
    BeadDependency,
    BeadType,
    DependencyType,
)
from maverick.jj.client import JjClient
from maverick.payloads import AssumptionPayload

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

if shutil.which("bd") is None:
    pytest.skip("bd CLI not available on PATH", allow_module_level=True)


@pytest.fixture
def bd_jj_repo(tmp_path: Path) -> Path:
    """A tmp directory with a real, jj-colocated ``bd`` database."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["jj", "git", "init", "--colocate"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["bd", "init", "--non-interactive"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


async def _make_epic(client: BeadClient, cwd: Path, feature: str = "049-assumption-ledger") -> str:
    epic = await client.create_bead(
        BeadDefinition(
            title=f"Integration epic ({feature})",
            bead_type=BeadType.EPIC,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
    )
    await client.set_state(epic.bd_id, {"speckit_feature": feature})
    return epic.bd_id


async def _make_source_bead(client: BeadClient, epic_id: str) -> str:
    source = await client.create_bead(
        BeadDefinition(
            title="Implement the thing",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        ),
        parent_id=epic_id,
    )
    return source.bd_id


@pytest.mark.asyncio
async def test_record_commit_stamp_flow(bd_jj_repo: Path) -> None:
    client = BeadClient(cwd=bd_jj_repo)
    jj_client = JjClient(cwd=bd_jj_repo)

    epic_id = await _make_epic(client, bd_jj_repo)
    source_bead_id = await _make_source_bead(client, epic_id)

    payload = AssumptionPayload(
        question="Should retries be scoped per bead?",
        adopted_answer="Per bead — matches existing scoping.",
        alternatives=("Per run",),
        severity="high",
    )
    record = await record_assumption(
        client, payload=payload, source_bead_id=source_bead_id, epic_id=epic_id
    )
    assert record is not None

    # Labels + state land as documented in data-model.md.
    entry_details = await client.show(record.bead_id)
    assert "assumption" in entry_details.labels
    assert "assumption-review" in entry_details.labels
    assert "needs-human-review" in entry_details.labels
    assert entry_details.state[KEY_STATUS] == STATUS_OPEN
    assert KEY_CHANGE_IDS not in entry_details.state  # unstamped until commit

    # discovered-from edge to the source bead.
    dep_list_result = subprocess.run(
        ["bd", "dep", "list", record.bead_id, "--json"],
        cwd=bd_jj_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    deps = json.loads(dep_list_result.stdout)
    assert any(
        d.get("type") == "discovered-from" and d.get("issue_id") == source_bead_id for d in deps
    )

    # Commit the (empty) working-copy change, mirroring the fly `commit`
    # action's jj_commit_bead call, then stamp the entry.
    (bd_jj_repo / "work.txt").write_text("done", encoding="utf-8")
    commit_result = await jj_client.commit(f"bead({source_bead_id}): Implement the thing")
    assert commit_result.change_id

    stamp_result = await stamp_change_id(
        client, entry_ids=[record.bead_id], change_id=commit_result.change_id
    )
    assert stamp_result.stamped == (record.bead_id,)
    assert stamp_result.failed == {}

    stamped_details = await client.show(record.bead_id)
    change_ids = stamped_details.state[KEY_CHANGE_IDS].split(",")
    assert commit_result.change_id in change_ids

    # The stamped change ID resolves via `jj log`.
    log_result = subprocess.run(
        ["jj", "log", "-r", commit_result.change_id, "--no-graph"],
        cwd=bd_jj_repo,
        capture_output=True,
        text=True,
    )
    assert log_result.returncode == 0
    assert commit_result.change_id[:8] in log_result.stdout or commit_result.change_id in (
        log_result.stdout
    )


@pytest.mark.asyncio
async def test_abandoned_bead_leaves_unstamped_entry(bd_jj_repo: Path) -> None:
    """A run that ends before commit leaves the entry with no change_ids (US1-S4)."""
    client = BeadClient(cwd=bd_jj_repo)
    epic_id = await _make_epic(client, bd_jj_repo)
    source_bead_id = await _make_source_bead(client, epic_id)

    payload = AssumptionPayload(question="Q?", adopted_answer="A.")
    record = await record_assumption(
        client, payload=payload, source_bead_id=source_bead_id, epic_id=epic_id
    )
    assert record is not None

    # No commit/stamp call — entry simply stays as created.
    entry_details = await client.show(record.bead_id)
    assert KEY_CHANGE_IDS not in entry_details.state
    assert entry_details.state[KEY_STATUS] == STATUS_OPEN


@pytest.mark.asyncio
async def test_medium_blocks_land_gate_until_answered(bd_jj_repo: Path) -> None:
    """Quickstart Scenario 3: medium entry blocks the land gate until answered."""
    client = BeadClient(cwd=bd_jj_repo)
    epic_id = await _make_epic(client, bd_jj_repo, feature="048-spec-a")
    source_bead_id = await _make_source_bead(client, epic_id)

    payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="medium")
    record = await record_assumption(
        client, payload=payload, source_bead_id=source_bead_id, epic_id=epic_id
    )
    assert record is not None

    blocking = await open_blocking_entries(client)
    assert any(r.bead_id == record.bead_id for r in blocking)

    await answer(client, bead_id=record.bead_id, answer_text="Yes, per bead.")

    blocking_after = await open_blocking_entries(client)
    assert not any(r.bead_id == record.bead_id for r in blocking_after)

    entry_details = await client.show(record.bead_id)
    assert entry_details.status in ("closed", "done")


@pytest.mark.asyncio
async def test_high_blocks_next_spec_epic_and_waive_releases(bd_jj_repo: Path) -> None:
    """Quickstart Scenario 4: high entry blocks the next spec's epic; waive releases it."""
    client = BeadClient(cwd=bd_jj_repo)
    epic_a = await _make_epic(client, bd_jj_repo, feature="048-spec-a")
    source_bead_id = await _make_source_bead(client, epic_a)

    payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="high")
    record = await record_assumption(
        client, payload=payload, source_bead_id=source_bead_id, epic_id=epic_a
    )
    assert record is not None

    # Spec B is refueled after the entry was recorded — mirrors
    # refuel_speckit._chain_epic's post-recording wiring hook.
    epic_b = await _make_epic(client, bd_jj_repo, feature="049-spec-b")
    entries = await open_high_entries_before(client, epic_id=epic_b)
    assert any(e.bead_id == record.bead_id for e in entries)

    await client.add_dependency(
        BeadDependency(
            blocker_id=record.bead_id, blocked_id=epic_b, dep_type=DependencyType.BLOCKS
        )
    )

    dep_list = subprocess.run(
        ["bd", "dep", "list", epic_b, "--json"],
        cwd=bd_jj_repo,
        capture_output=True,
        text=True,
        check=True,
    )
    deps = json.loads(dep_list.stdout)
    assert any(d.get("type") == "blocks" and d.get("issue_id") == record.bead_id for d in deps)

    await waive(client, bead_id=record.bead_id, reason="not applicable", waived_by="tester")

    entry_details = await client.show(record.bead_id)
    assert entry_details.status in ("closed", "done")

    # No more open high entries for spec A once waived.
    entries_after = await open_high_entries_before(client, epic_id=epic_b)
    assert not any(e.bead_id == record.bead_id for e in entries_after)


@pytest.mark.asyncio
async def test_legacy_escalation_bead_flows_through_brief_review_and_land_gate(
    bd_jj_repo: Path,
) -> None:
    """FR-013: a pre-feature escalation bead (old labels, no ledger state)
    flows through brief, review, and the land gate without errors."""
    from maverick.cli.commands.brief import brief
    from maverick.cli.commands.review import review

    client = BeadClient(cwd=bd_jj_repo)
    epic_id = await _make_epic(client, bd_jj_repo, feature="048-legacy-spec")
    source_bead_id = await _make_source_bead(client, epic_id)

    # Mirrors create_human_bead's pre-feature shape exactly: no `assumption`
    # label, no `assumption_*` state keys.
    legacy = await client.create_bead(
        BeadDefinition(
            title="Review: legacy escalation",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.REVIEW,
            description="## Escalation Reason\n\nReview rounds exhausted.",
            assignee="human",
            labels=["assumption-review", "needs-human-review"],
        ),
        parent_id=epic_id,
    )
    await client.set_state(
        legacy.bd_id,
        {
            "source_bead": source_bead_id,
            "escalation_type": "fix_exhaustion",
            "flight_plan": "048-legacy-spec",
        },
    )

    # --- land gate: legacy bead is surfaced as a medium blocker ---------
    blocking = await open_blocking_entries(client)
    matches = [r for r in blocking if r.bead_id == legacy.bd_id]
    assert len(matches) == 1
    assert matches[0].is_legacy is True
    assert matches[0].severity.value == "medium"

    # --- brief: legacy bead counted in the legacy_open bucket -----------
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(bd_jj_repo)
        brief_result = runner.invoke(brief, ["--human"])
        assert brief_result.exit_code == 0, brief_result.output
        assert legacy.bd_id in brief_result.output

        # --- review: legacy approve/reject/defer flow is unchanged ------
        review_result = runner.invoke(review, [legacy.bd_id, "--approve"])
        assert review_result.exit_code == 0, review_result.output
        assert "closed as approved" in review_result.output
    finally:
        os.chdir(cwd)

    closed_details = await client.show(legacy.bd_id)
    assert closed_details.status in ("closed", "done")

    # Once closed, the land gate no longer counts it.
    blocking_after = await open_blocking_entries(client)
    assert not any(r.bead_id == legacy.bd_id for r in blocking_after)


@pytest.mark.asyncio
async def test_low_severity_is_advisory_only(bd_jj_repo: Path) -> None:
    """Quickstart Scenario 2: low entries are deferred out of `bd ready`,
    never block land, and still count in `per_spec_counts`."""
    from maverick.assumptions.report import per_spec_counts

    client = BeadClient(cwd=bd_jj_repo)
    epic_id = await _make_epic(client, bd_jj_repo, feature="049-assumption-ledger")
    source_bead_id = await _make_source_bead(client, epic_id)

    payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="low")
    record = await record_assumption(
        client, payload=payload, source_bead_id=source_bead_id, epic_id=epic_id
    )
    assert record is not None

    # Deferred — absent from `bd ready`.
    ready = await client.ready(epic_id, limit=50)
    assert not any(r.id == record.bead_id for r in ready)

    # Never blocks land.
    blocking = await open_blocking_entries(client)
    assert not any(r.bead_id == record.bead_id for r in blocking)

    # Still counted (open, low) in per-spec reporting.
    from maverick.assumptions.models import Severity

    counts = await per_spec_counts(client)
    row = next(r for r in counts if r.owner_spec == "049-assumption-ledger")
    assert row.open[Severity.LOW] == 1
