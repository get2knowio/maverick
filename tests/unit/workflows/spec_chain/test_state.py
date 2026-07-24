"""Unit tests for spec-chain state persistence and resume discovery.

Covers `maverick.workflows.spec_chain.state` (T009 — atomic save/load of
`ChainState` to ``.maverick/runs/<run-id>/spec-chain.json``, plus
``discover_resumable`` feature-keyed scan), per
``specs/050-headless-spec-chain/contracts/chain-state.md``.

At authorship time (T005) both ``maverick.workflows.spec_chain.models``
(T008) and ``maverick.workflows.spec_chain.state`` (T009) are empty
placeholder stubs, so this module is expected to fail at collection
(``ImportError``) until those tasks land. That is the intended red state
for TDD — do not "fix" this file to import around the stubs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from maverick.assumptions.models import Severity
from maverick.workflows.spec_chain.constants import ChainStep
from maverick.workflows.spec_chain.models import ChainState, ClarifyDecision, StepRecord
from maverick.workflows.spec_chain.state import (
    discover_resumable,
    load_chain_state,
    save_chain_state,
)

RUNS_SUBDIR = Path(".maverick") / "runs"
STATE_FILENAME = "spec-chain.json"


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------


def _step_record(
    step: ChainStep,
    *,
    status: str = "succeeded",
    landed: bool = True,
    attempts: int = 1,
    error: str | None = None,
) -> StepRecord:
    now = datetime.now(tz=UTC)
    return StepRecord(
        step=step,
        status=status,
        attempts=attempts,
        artifacts=[f"{step.value}.md"],
        landed=landed,
        error=error,
        started_at=now,
        finished_at=now if status in {"succeeded", "failed"} else None,
    )


def _clarify_decision(*, ledger_bead_id: str | None = None) -> ClarifyDecision:
    return ClarifyDecision(
        question="Should exports include archived widgets?",
        adopted_answer="No, exclude archived widgets by default.",
        alternatives=("Include all widgets", "Prompt per-run"),
        severity=Severity.LOW,
        severity_defaulted=True,
        path="non_interactive",
        ledger_bead_id=ledger_bead_id,
    )


def _chain_state(
    *,
    run_id: str = "run-00000000",
    feature: str = "widget-export",
    status: str = "running",
    started_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> ChainState:
    started = started_at or datetime.now(tz=UTC)
    updated = updated_at or started
    return ChainState(
        schema_version=1,
        run_id=run_id,
        feature=feature,
        feature_dir=f"specs/050-{feature}",
        prd_path="docs/widget-export-prd.md",
        prd_digest="a" * 64,
        workspace_path=(f"/home/user/.maverick/workspaces/proj/spec-chain/{feature}"),
        status=status,
        steps={
            ChainStep.SPECIFY: _step_record(ChainStep.SPECIFY),
            ChainStep.CLARIFY: _step_record(ChainStep.CLARIFY, status="in_progress", landed=False),
        },
        clarify_decisions=[_clarify_decision()],
        remediation_bead_ids=["bead-123"],
        started_at=started,
        updated_at=updated,
    )


def _raw_state_json(
    *,
    run_id: str,
    feature: str,
    status: str,
    updated_at: str,
    started_at: str | None = None,
) -> dict:
    """Build a schema-conforming raw dict, bypassing save_chain_state entirely.

    Used for discover_resumable tests so they don't depend on save()/the
    model layer being correct — only on state.py's own read/scan/parse path.
    """
    started = started_at or updated_at
    return {
        "schema_version": 1,
        "run_id": run_id,
        "feature": feature,
        "feature_dir": f"specs/050-{feature}",
        "prd_path": "docs/prd.md",
        "prd_digest": "0" * 64,
        "workspace_path": f"/home/user/.maverick/workspaces/proj/spec-chain/{feature}",
        "status": status,
        "steps": {
            "specify": {
                "step": "specify",
                "status": "succeeded",
                "attempts": 1,
                "artifacts": ["spec.md"],
                "landed": True,
                "error": None,
                "started_at": started,
                "finished_at": updated_at,
            },
        },
        "clarify_decisions": [],
        "remediation_bead_ids": [],
        "started_at": started,
        "updated_at": updated_at,
    }


def _write_raw_run(
    base: Path,
    *,
    run_id: str,
    feature: str,
    status: str,
    updated_at: str,
    started_at: str | None = None,
) -> Path:
    run_dir = base / RUNS_SUBDIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / STATE_FILENAME
    state_path.write_text(
        json.dumps(
            _raw_state_json(
                run_id=run_id,
                feature=feature,
                status=status,
                updated_at=updated_at,
                started_at=started_at,
            )
        ),
        encoding="utf-8",
    )
    return state_path


# ---------------------------------------------------------------------------
# save_chain_state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_chain_state_writes_expected_file(temp_dir: Path) -> None:
    state = _chain_state(run_id="run-save-1")

    await save_chain_state(state, temp_dir)

    state_path = temp_dir / RUNS_SUBDIR / "run-save-1" / STATE_FILENAME
    assert state_path.is_file()
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == "run-save-1"
    assert on_disk["feature"] == "widget-export"
    assert on_disk["schema_version"] == 1


@pytest.mark.asyncio
async def test_save_chain_state_is_atomic_no_leftover_tmp_files(temp_dir: Path) -> None:
    state = _chain_state(run_id="run-save-atomic")

    await save_chain_state(state, temp_dir)

    run_dir = temp_dir / RUNS_SUBDIR / "run-save-atomic"
    leftover_tmp = [p for p in run_dir.iterdir() if "tmp" in p.name.lower()]
    assert leftover_tmp == []
    assert (run_dir / STATE_FILENAME).is_file()


@pytest.mark.asyncio
async def test_save_chain_state_overwrites_existing_file(temp_dir: Path) -> None:
    state = _chain_state(run_id="run-save-overwrite", status="running")
    await save_chain_state(state, temp_dir)

    updated = state.model_copy(update={"status": "halted"})
    await save_chain_state(updated, temp_dir)

    state_path = temp_dir / RUNS_SUBDIR / "run-save-overwrite" / STATE_FILENAME
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["status"] == "halted"


# ---------------------------------------------------------------------------
# load_chain_state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_chain_state_round_trips_saved_state(temp_dir: Path) -> None:
    started = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    updated = datetime(2026, 7, 1, 12, 30, 0, tzinfo=UTC)
    state = _chain_state(
        run_id="run-roundtrip",
        feature="widget-export",
        status="halted",
        started_at=started,
        updated_at=updated,
    )

    await save_chain_state(state, temp_dir)
    loaded = await load_chain_state("run-roundtrip", temp_dir)

    assert loaded is not None
    assert loaded == state


@pytest.mark.asyncio
async def test_load_chain_state_round_trips_nested_steps_and_decisions(
    temp_dir: Path,
) -> None:
    state = _chain_state(run_id="run-nested")

    await save_chain_state(state, temp_dir)
    loaded = await load_chain_state("run-nested", temp_dir)

    assert loaded is not None
    assert set(loaded.steps.keys()) == {ChainStep.SPECIFY, ChainStep.CLARIFY}
    assert loaded.steps[ChainStep.SPECIFY].status == "succeeded"
    assert loaded.steps[ChainStep.SPECIFY].landed is True
    assert loaded.steps[ChainStep.CLARIFY].status == "in_progress"
    assert loaded.steps[ChainStep.CLARIFY].landed is False
    assert len(loaded.clarify_decisions) == 1
    decision = loaded.clarify_decisions[0]
    assert decision.question == "Should exports include archived widgets?"
    assert decision.severity == Severity.LOW
    assert decision.alternatives == ("Include all widgets", "Prompt per-run")
    assert loaded.remediation_bead_ids == ["bead-123"]


@pytest.mark.asyncio
async def test_load_chain_state_missing_run_returns_none(temp_dir: Path) -> None:
    loaded = await load_chain_state("does-not-exist", temp_dir)
    assert loaded is None


@pytest.mark.asyncio
async def test_load_chain_state_missing_runs_dir_returns_none(temp_dir: Path) -> None:
    # .maverick/runs doesn't exist at all under this base.
    loaded = await load_chain_state("whatever", temp_dir)
    assert loaded is None


# ---------------------------------------------------------------------------
# discover_resumable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_resumable_returns_newest_matching_status(
    temp_dir: Path,
) -> None:
    base_time = datetime(2026, 7, 1, tzinfo=UTC)
    _write_raw_run(
        temp_dir,
        run_id="run-older",
        feature="widget-export",
        status="halted",
        updated_at=(base_time).isoformat(),
    )
    _write_raw_run(
        temp_dir,
        run_id="run-newer",
        feature="widget-export",
        status="running",
        updated_at=(base_time + timedelta(hours=1)).isoformat(),
    )

    result = await discover_resumable("widget-export", temp_dir)

    assert result is not None
    assert result.run_id == "run-newer"
    assert result.status == "running"


@pytest.mark.asyncio
async def test_discover_resumable_ignores_non_matching_feature(temp_dir: Path) -> None:
    base_time = datetime(2026, 7, 1, tzinfo=UTC)
    _write_raw_run(
        temp_dir,
        run_id="run-other-feature",
        feature="other-feature",
        status="halted",
        updated_at=base_time.isoformat(),
    )

    result = await discover_resumable("widget-export", temp_dir)

    assert result is None


@pytest.mark.asyncio
async def test_discover_resumable_only_completed_chains_returns_none(
    temp_dir: Path,
) -> None:
    base_time = datetime(2026, 7, 1, tzinfo=UTC)
    _write_raw_run(
        temp_dir,
        run_id="run-completed",
        feature="widget-export",
        status="completed",
        updated_at=base_time.isoformat(),
    )
    _write_raw_run(
        temp_dir,
        run_id="run-failed",
        feature="widget-export",
        status="failed",
        updated_at=(base_time + timedelta(hours=1)).isoformat(),
    )

    result = await discover_resumable("widget-export", temp_dir)

    assert result is None


@pytest.mark.asyncio
async def test_discover_resumable_prefers_running_or_halted_over_older_completed(
    temp_dir: Path,
) -> None:
    base_time = datetime(2026, 7, 1, tzinfo=UTC)
    # Newest run for the feature is completed (terminal) -- should be skipped
    # in favor of the older, still-resumable halted run.
    _write_raw_run(
        temp_dir,
        run_id="run-completed-newest",
        feature="widget-export",
        status="completed",
        updated_at=(base_time + timedelta(hours=2)).isoformat(),
    )
    _write_raw_run(
        temp_dir,
        run_id="run-halted-older",
        feature="widget-export",
        status="halted",
        updated_at=(base_time + timedelta(hours=1)).isoformat(),
    )

    result = await discover_resumable("widget-export", temp_dir)

    assert result is not None
    assert result.run_id == "run-halted-older"


@pytest.mark.asyncio
async def test_discover_resumable_tie_breaks_among_newest(temp_dir: Path) -> None:
    tied_time = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC).isoformat()
    _write_raw_run(
        temp_dir,
        run_id="run-tie-a",
        feature="widget-export",
        status="halted",
        updated_at=tied_time,
    )
    _write_raw_run(
        temp_dir,
        run_id="run-tie-b",
        feature="widget-export",
        status="running",
        updated_at=tied_time,
    )

    result = await discover_resumable("widget-export", temp_dir)

    # Contract only guarantees "newest first"; with an exact tie either
    # candidate is an acceptable resume target, but one of them must win.
    assert result is not None
    assert result.run_id in {"run-tie-a", "run-tie-b"}
    assert result.status in {"halted", "running"}


@pytest.mark.asyncio
async def test_discover_resumable_empty_runs_dir_returns_none(temp_dir: Path) -> None:
    (temp_dir / RUNS_SUBDIR).mkdir(parents=True)

    result = await discover_resumable("widget-export", temp_dir)

    assert result is None


@pytest.mark.asyncio
async def test_discover_resumable_missing_runs_dir_returns_none(temp_dir: Path) -> None:
    # temp_dir has no .maverick/runs at all.
    result = await discover_resumable("widget-export", temp_dir)

    assert result is None


@pytest.mark.asyncio
async def test_discover_resumable_skips_unparseable_state_files(temp_dir: Path) -> None:
    """A corrupt/partial state file must not crash discovery of a valid one."""
    corrupt_dir = temp_dir / RUNS_SUBDIR / "run-corrupt"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / STATE_FILENAME).write_text("not valid json{{{", encoding="utf-8")

    _write_raw_run(
        temp_dir,
        run_id="run-valid",
        feature="widget-export",
        status="halted",
        updated_at=datetime(2026, 7, 1, tzinfo=UTC).isoformat(),
    )

    result = await discover_resumable("widget-export", temp_dir)

    assert result is not None
    assert result.run_id == "run-valid"
