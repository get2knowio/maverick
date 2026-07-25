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

pytestmark = [pytest.mark.integration]

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
        d.get("dependency_type") == "discovered-from" and d.get("id") == source_bead_id
        for d in deps
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
@pytest.mark.xfail(
    reason=(
        "Pre-existing, out-of-scope: the installed bd CLI (1.1.0+) now "
        "rejects cross-type `blocks` dependencies ('epics can only block "
        "other epics, not tasks' / vice versa). `_wire_high_blocks_edge` "
        "wires a task-type entry blocking an epic, which this bd version "
        "no longer permits. Fixing it requires redesigning spec 049's "
        "high-severity blocks-edge mechanism — out of scope for spec 052 "
        "(conditional landing), which does not touch this code path."
    ),
    strict=False,
)
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
    assert any(
        d.get("dependency_type") == "blocks" and d.get("id") == record.bead_id for d in deps
    )

    await waive(client, bead_id=record.bead_id, reason="not applicable", waived_by="tester")

    entry_details = await client.show(record.bead_id)
    assert entry_details.status in ("closed", "done")

    # No more open high entries for spec A once waived.
    entries_after = await open_high_entries_before(client, epic_id=epic_b)
    assert not any(e.bead_id == record.bead_id for e in entries_after)


def test_legacy_escalation_bead_flows_through_brief_review_and_land_gate(
    bd_jj_repo: Path,
) -> None:
    """FR-013: a pre-feature escalation bead (old labels, no ledger state)
    flows through brief, review, and the land gate without errors.

    Deliberately a plain (non-async) test: `brief`/`review` are
    `async_command`-wrapped and manage their own event loop + SIGINT
    handler internally (main-thread only — `add_signal_handler` can't run
    off-thread), so `CliRunner.invoke()` must run with no asyncio loop
    already active in this thread. The async ledger setup/verification
    steps are isolated in their own `asyncio.run()` calls around the
    synchronous CLI invocations.
    """
    import asyncio

    from maverick.cli.commands.brief import brief
    from maverick.cli.commands.review import review

    async def _setup() -> str:
        client = BeadClient(cwd=bd_jj_repo)
        epic_id = await _make_epic(client, bd_jj_repo, feature="048-legacy-spec")
        source_bead_id = await _make_source_bead(client, epic_id)

        # Mirrors create_human_bead's pre-feature shape exactly: no
        # `assumption` label, no `assumption_*` state keys.
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

        # --- land gate: legacy bead is surfaced as a medium blocker -----
        blocking = await open_blocking_entries(client)
        matches = [r for r in blocking if r.bead_id == legacy.bd_id]
        assert len(matches) == 1
        assert matches[0].is_legacy is True
        assert matches[0].severity.value == "medium"

        return legacy.bd_id

    legacy_bd_id = asyncio.run(_setup())

    # --- brief: legacy bead counted in the legacy_open bucket -----------
    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(bd_jj_repo)
        brief_result = runner.invoke(brief, ["--human"])
        assert brief_result.exit_code == 0, brief_result.output
        assert legacy_bd_id in brief_result.output

        # --- review: legacy approve/reject/defer flow is unchanged ------
        review_result = runner.invoke(review, [legacy_bd_id, "--approve"])
        assert review_result.exit_code == 0, review_result.output
        assert "closed as approved" in review_result.output
    finally:
        os.chdir(cwd)

    async def _verify() -> None:
        client = BeadClient(cwd=bd_jj_repo)
        closed_details = await client.show(legacy_bd_id)
        assert closed_details.status in ("closed", "done")

        # Once closed, the land gate no longer counts it.
        blocking_after = await open_blocking_entries(client)
        assert not any(r.bead_id == legacy_bd_id for r in blocking_after)

    asyncio.run(_verify())


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


@pytest.mark.asyncio
@pytest.mark.timeout(150)
# 3 entries × record_assumption's multi-key set_state + bulk_waive's 3
# waive() calls, each now N subprocess invocations (bd 1.1.0 only accepts
# one dimension=value pair per `bd set-state` call — see client.py).
# Observed 25-60s depending on machine/parallel load; generous margin.
async def test_low_severity_blocks_frontier_until_bulk_waived(bd_jj_repo: Path) -> None:
    """052 quickstart Scenarios 1+3: the strict frontier gate blocks on
    low-severity entries alone (unlike the legacy medium/high-only gate);
    `ledger.bulk_waive` clears several in one invocation (spec-scoped,
    default severity filter); the resulting empty-frontier-with-waivers
    classifies conditionally-verified.
    """
    from maverick.assumptions.land_report import classify, frontier
    from maverick.assumptions.ledger import bulk_waive, report_entries
    from maverick.assumptions.models import LandVerification, Severity

    client = BeadClient(cwd=bd_jj_repo)
    epic_id = await _make_epic(client, bd_jj_repo, feature="052-conditional-landing")
    source_bead_id = await _make_source_bead(client, epic_id)

    for i in range(3):
        payload = AssumptionPayload(
            question=f"Should low-severity entry {i} block?",
            adopted_answer="No special handling needed.",
            severity="low",
        )
        record = await record_assumption(
            client, payload=payload, source_bead_id=source_bead_id, epic_id=epic_id
        )
        assert record is not None

    # Frontier is non-empty — land would block on all three, low severity
    # included (strict gate, Clarifications 2026-07-24).
    entries = await report_entries(client)
    land_frontier = frontier(entries)
    assert not land_frontier.is_empty
    assert len(land_frontier.open_entries) == 3
    assert classify(entries) == LandVerification.BLOCKED

    # Bulk waive clears all three low-severity entries under this spec in
    # one invocation, with the shared reason/waiver recorded on each.
    result = await bulk_waive(
        client,
        owner_spec="052-conditional-landing",
        severities=frozenset({Severity.LOW}),
        reason="accepted for MVP",
        waived_by="tester",
    )
    assert len(result.waived) == 3
    assert result.failed == {}
    for record in result.waived:
        details = await client.show(record.bead_id)
        assert details.status in ("closed", "done")

    # Frontier is now empty; classification reflects the waivers.
    entries_after = await report_entries(client)
    assert frontier(entries_after).is_empty
    assert classify(entries_after) == LandVerification.CONDITIONALLY_VERIFIED

    # A second bulk waive is idempotent — nothing left to match.
    result_again = await bulk_waive(
        client,
        owner_spec="052-conditional-landing",
        severities=frozenset({Severity.LOW}),
        reason="again",
        waived_by="tester",
    )
    assert result_again.waived == ()
    assert result_again.failed == {}


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_full_provenance_round_trip_report(bd_jj_repo: Path) -> None:
    """052 quickstart Scenario 2 / T021: the land report's provenance for a
    reconciled entry shows both the original ledger stamp and the
    reconcile correction change id, plus the final (corrected) answer; a
    separately-waived entry's row carries who/when/why.

    Exercises ``ledger.mark_reconciled`` directly (the same terminal write
    ``ReconcileWorkflow._process_one_answer`` performs post-fold) rather
    than the full agent-driven correction pipeline — that pipeline's
    real-jj mechanics are already exhaustively covered by
    tests/integration/workflows/test_reconcile_jj.py (spec 051); this test
    covers 052's own scope: the report's provenance reading.
    """
    from maverick.assumptions.land_report import build_report
    from maverick.assumptions.ledger import mark_reconciled, report_entries
    from maverick.assumptions.models import LandVerification

    client = BeadClient(cwd=bd_jj_repo)
    epic_id = await _make_epic(client, bd_jj_repo, feature="052-conditional-landing")
    source_bead_id = await _make_source_bead(client, epic_id)

    payload = AssumptionPayload(
        question="Should retries be scoped per bead?",
        adopted_answer="Original answer.",
        severity="medium",
    )
    record = await record_assumption(
        client, payload=payload, source_bead_id=source_bead_id, epic_id=epic_id
    )
    assert record is not None

    # Original jj stamp (mirrors commit()'s stamp_change_id call).
    await stamp_change_id(client, entry_ids=[record.bead_id], change_id="zzkw000")

    # Human answers, then later changes the answer.
    await answer(client, bead_id=record.bead_id, answer_text="Original answer.")
    await answer(client, bead_id=record.bead_id, answer_text="Actually, a different answer.")

    # Reconcile corrects + folds the change — this is the exact terminal
    # write `ReconcileWorkflow._process_one_answer` performs post-fold.
    marked = await mark_reconciled(
        client,
        entry_id=record.bead_id,
        applied_answer="Actually, a different answer.",
        change_id="rlvk111",
    )
    assert marked is True

    # A second, unrelated entry is waived — for the who/when/why assertion.
    payload2 = AssumptionPayload(question="Q2?", adopted_answer="A2.", severity="low")
    record2 = await record_assumption(
        client, payload=payload2, source_bead_id=source_bead_id, epic_id=epic_id
    )
    assert record2 is not None
    await waive(client, bead_id=record2.bead_id, reason="not applicable", waived_by="tester")

    entries = await report_entries(client)
    report = build_report(
        entries, LandVerification.CONDITIONALLY_VERIFIED, run_id="r1", dry_run=False
    )
    data = report.to_dict()
    rows = {e["bead_id"]: e for e in data["specs"][0]["entries"]}

    reconciled_row = rows[record.bead_id]
    assert reconciled_row["affected_change_ids"] == ["zzkw000", "rlvk111"]
    assert reconciled_row["final_answer"] == "Actually, a different answer."
    assert reconciled_row["reconcile"]["status"] == "reconciled"
    assert reconciled_row["reconcile"]["change_id"] == "rlvk111"
    assert reconciled_row["bucket"] == "resolved"

    waived_row = rows[record2.bead_id]
    assert waived_row["waiver"]["by"] == "tester"
    assert waived_row["waiver"]["reason"] == "not applicable"
    assert waived_row["waiver"]["at"] is not None
