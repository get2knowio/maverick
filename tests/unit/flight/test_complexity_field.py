"""Tests for the per-bead ``complexity`` classification field.

Phase 1 of the per-bead complexity routing work (FUTURE.md §1.4):
the decomposer outputs a complexity hint per work unit; we persist it
through the schema → spec → WorkUnit → markdown round-trip; nothing yet
*acts* on it. These tests pin down the persistence contract so Phase 2
(tier-based model routing) and Phase 3 (extending tiers to review/fix/
decompose_detail) can rely on the field being there.
"""

from __future__ import annotations

import pytest

from maverick.flight.loader import WorkUnitFile
from maverick.flight.models import (
    AcceptanceCriterion,
    FileScope,
    WorkUnit,
)
from maverick.flight.serializer import serialize_work_unit
from maverick.tools.agent_inbox.models import (
    SubmitOutlinePayload,
    WorkUnitOutlinePayload,
)
from maverick.workflows.refuel_maverick.models import WorkUnitSpec


def _minimal_work_unit(complexity: str | None) -> WorkUnit:
    return WorkUnit(
        id="wu-1",
        flight_plan="my-plan",
        sequence=1,
        depends_on=(),
        task="do the thing",
        acceptance_criteria=(AcceptanceCriterion(text="it works"),),
        file_scope=FileScope(create=("foo.py",), modify=(), protect=()),
        instructions="step 1",
        verification=("pytest",),
        complexity=complexity,
    )


@pytest.mark.parametrize("value", ["trivial", "simple", "moderate", "complex", None])
def test_work_unit_accepts_all_complexity_values(value: str | None) -> None:
    wu = _minimal_work_unit(value)
    assert wu.complexity == value


def test_work_unit_rejects_invalid_complexity() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _minimal_work_unit("medium")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["trivial", "simple", "moderate", "complex"])
def test_serializer_round_trip_preserves_complexity(value: str, tmp_path: object) -> None:
    wu = _minimal_work_unit(value)
    serialized = serialize_work_unit(wu)
    # complexity is in the YAML frontmatter
    assert f"complexity: {value}" in serialized

    # Round-trip through the loader: write, parse, compare.
    from pathlib import Path

    path = Path(tmp_path) / "001-wu-1.md"  # type: ignore[arg-type]
    path.write_text(serialized, encoding="utf-8")
    loaded = WorkUnitFile.load(path)
    assert loaded.complexity == value


def test_serializer_omits_complexity_when_none() -> None:
    wu = _minimal_work_unit(None)
    serialized = serialize_work_unit(wu)
    # Frontmatter should not have a ``complexity:`` line at all.
    assert "complexity:" not in serialized


def test_loader_silently_ignores_unknown_complexity_value(
    tmp_path: object,
) -> None:
    """Forward-compat: an unknown enum value loads as None rather than crashing."""
    from pathlib import Path

    md = (
        "---\n"
        "work-unit: wu-1\n"
        "flight-plan: my-plan\n"
        "sequence: 1\n"
        "depends-on: []\n"
        "complexity: epic-level\n"  # not in the enum
        "---\n\n"
        "## Task\n\ndo the thing\n\n"
        "## Acceptance Criteria\n\n- it works\n\n"
        "## File Scope\n\n### Create\n\n- foo.py\n\n### Modify\n\n### Protect\n\n"
        "## Procedure\n\nstep 1\n\n"
        "## Verification\n\n- pytest\n"
    )
    path = Path(tmp_path) / "001-wu-1.md"  # type: ignore[arg-type]
    path.write_text(md, encoding="utf-8")
    loaded = WorkUnitFile.load(path)
    assert loaded.complexity is None


# ---------------------------------------------------------------------------
# Schema flow: outline payload → spec → WorkUnit
# ---------------------------------------------------------------------------


def test_outline_payload_carries_complexity() -> None:
    p = WorkUnitOutlinePayload(id="wu-1", task="do it", complexity="complex")
    assert p.complexity == "complex"


def test_outline_payload_complexity_optional() -> None:
    p = WorkUnitOutlinePayload(id="wu-1", task="do it")
    assert p.complexity is None


def test_submit_outline_payload_round_trips_complexity() -> None:
    payload = SubmitOutlinePayload(
        work_units=(
            WorkUnitOutlinePayload(id="a", task="trivial work", complexity="trivial"),
            WorkUnitOutlinePayload(id="b", task="hard work", complexity="complex"),
            WorkUnitOutlinePayload(id="c", task="legacy"),  # no complexity
        )
    )
    assert [wu.complexity for wu in payload.work_units] == [
        "trivial",
        "complex",
        None,
    ]


def test_work_unit_spec_carries_complexity() -> None:
    spec = WorkUnitSpec(
        id="wu-1",
        sequence=1,
        task="do it",
        acceptance_criteria=[],
        verification=["pytest"],
        complexity="moderate",
    )
    assert spec.complexity == "moderate"


def test_work_unit_spec_complexity_optional() -> None:
    spec = WorkUnitSpec(
        id="wu-1",
        sequence=1,
        task="do it",
        acceptance_criteria=[],
        verification=["pytest"],
    )
    assert spec.complexity is None
