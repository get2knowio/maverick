"""Tests for refuel cache-write behaviour.

The supervisor persists briefing / outline / per-unit detail JSON so a
Ctrl-C'd run resumes at the phase it was in instead of replaying
everything. These tests verify each cache-write helper directly (no
pool round-trip needed — the helpers are pure I/O).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maverick.actors.xoscar.refuel_supervisor import RefuelInputs, RefuelSupervisor
from maverick.tools.supervisor_inbox.models import (
    SubmitNavigatorBriefPayload,
    SubmitOutlinePayload,
    WorkUnitDetailPayload,
    WorkUnitOutlinePayload,
)


def _make_supervisor(
    tmp_path: Path,
    *,
    skip_briefing: bool = True,
) -> RefuelSupervisor:
    """Build a supervisor directly (bypassing ``__post_create__``) so the
    cache helpers can be exercised without a live pool or children."""
    inputs = RefuelInputs(
        cwd=str(tmp_path),
        flight_plan=SimpleNamespace(name="p", objective="o", success_criteria=[]),
        skip_briefing=skip_briefing,
        briefing_cache_path=str(tmp_path / "refuel-briefing.json"),
        outline_cache_path=str(tmp_path / "refuel-outline.json"),
        detail_cache_dir=str(tmp_path / "refuel-details"),
        briefing_cache_key="fixed-key-aaa",
        briefing_cache_schema_version=1,
        outline_cache_key_inputs={
            "flight_plan_content": "plan",
            "verification_properties": "verify",
        },
        outline_cache_schema_version=1,
    )
    sup = RefuelSupervisor(inputs)
    # Fake the fields that __post_create__ would have set.
    sup._outline = None
    sup._briefing_results = {}
    return sup


def test_cache_briefing_results_writes_envelope(tmp_path: Path) -> None:
    sup = _make_supervisor(tmp_path)
    sup._briefing_results = {
        "navigator": SubmitNavigatorBriefPayload(
            architecture_decisions=(),
            module_structure="mod",
            integration_points=(),
            summary="s",
        )
    }
    # Workflow normally seeds this after briefing. Mirror the hook.
    sup._inputs.initial_payload["briefing"] = {
        "navigator": {
            "architecture_decisions": [],
            "module_structure": "mod",
            "integration_points": [],
            "summary": "s",
        }
    }
    sup._cache_briefing_results()

    cache_file = tmp_path / "refuel-briefing.json"
    assert cache_file.exists()
    envelope = json.loads(cache_file.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == 1
    assert envelope["cache_key"] == "fixed-key-aaa"
    assert "navigator" in envelope["payloads"]


def test_cache_briefing_results_no_op_without_path(tmp_path: Path) -> None:
    inputs = RefuelInputs(
        cwd=str(tmp_path),
        flight_plan=SimpleNamespace(name="p", objective="o", success_criteria=[]),
        skip_briefing=True,
        briefing_cache_path="",  # disabled
    )
    sup = RefuelSupervisor(inputs)
    sup._briefing_results = {}
    # Must not raise or write anything.
    sup._cache_briefing_results()
    assert not any((tmp_path).iterdir())


def test_cache_outline_writes_envelope_with_cache_key(tmp_path: Path) -> None:
    sup = _make_supervisor(tmp_path)
    sup._outline = SubmitOutlinePayload(
        work_units=(
            WorkUnitOutlinePayload(id="wu-1", task="T1"),
            WorkUnitOutlinePayload(id="wu-2", task="T2"),
        )
    )
    sup._cache_outline()

    cache_file = tmp_path / "refuel-outline.json"
    assert cache_file.exists()
    envelope = json.loads(cache_file.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == 1
    # Cache key is sha256 of inputs — just assert presence + shape.
    assert envelope["cache_key"]
    assert len(envelope["cache_key"]) == 16
    assert [wu["id"] for wu in envelope["payload"]["work_units"]] == ["wu-1", "wu-2"]


def test_cache_detail_writes_per_unit_file(tmp_path: Path) -> None:
    sup = _make_supervisor(tmp_path)
    detail = WorkUnitDetailPayload(
        id="wu-1",
        instructions="Do the thing",
        acceptance_criteria=(),
        verification=("echo ok",),
    )
    sup._cache_detail("wu-1", detail)

    details_dir = tmp_path / "refuel-details"
    detail_file = details_dir / "wu-1.json"
    assert detail_file.exists()
    loaded = json.loads(detail_file.read_text(encoding="utf-8"))
    assert loaded["id"] == "wu-1"
    assert loaded["instructions"] == "Do the thing"


def test_cache_detail_no_op_without_dir(tmp_path: Path) -> None:
    inputs = RefuelInputs(
        cwd=str(tmp_path),
        flight_plan=SimpleNamespace(name="p", objective="o", success_criteria=[]),
        skip_briefing=True,
        detail_cache_dir="",
    )
    sup = RefuelSupervisor(inputs)
    detail = WorkUnitDetailPayload(id="wu-1", instructions="x")
    sup._cache_detail("wu-1", detail)
    # No files written.
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_supervisor_with_cache_paths_accepts_them(tmp_path: Path) -> None:
    """Construction sanity check with all cache fields populated."""
    inputs = RefuelInputs(
        cwd=str(tmp_path),
        flight_plan=SimpleNamespace(name="p", objective="o", success_criteria=[]),
        briefing_cache_path=str(tmp_path / "b.json"),
        outline_cache_path=str(tmp_path / "o.json"),
        detail_cache_dir=str(tmp_path / "d"),
        briefing_cache_key="k",
        outline_cache_key_inputs={"flight_plan_content": "x", "verification_properties": "y"},
    )
    sup = RefuelSupervisor(inputs)
    assert sup._inputs.briefing_cache_path == str(tmp_path / "b.json")
    assert sup._inputs.detail_cache_dir == str(tmp_path / "d")
