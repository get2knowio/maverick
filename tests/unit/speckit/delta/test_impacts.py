"""Unit tests for speckit/delta/impacts.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from maverick.beads.models import BeadDetails, BeadSummary
from maverick.speckit.delta.impacts import detect_impacts
from maverick.speckit.delta.models import DeltaDocument, TaskEntry

_PATH = Path("specs/052-conditional-landing/deltas/001-sample.md")


def _make_client(
    *, children: list[BeadSummary], details_by_id: dict[str, BeadDetails]
) -> MagicMock:
    client = MagicMock()
    client.children = AsyncMock(return_value=children)

    async def _show(bead_id: str) -> BeadDetails:
        return details_by_id[bead_id]

    client.show = AsyncMock(side_effect=_show)
    return client


def _document(*task_entries: TaskEntry) -> DeltaDocument:
    return DeltaDocument(
        path=_PATH,
        title="sample",
        target_feature="052-conditional-landing",
        task_entries=task_entries,
        sequence=1,
    )


@pytest.mark.asyncio
async def test_in_flight_task_is_a_blocking_impact() -> None:
    client = _make_client(
        children=[BeadSummary(id="mv-1", title="T017", status="in_progress")],
        details_by_id={
            "mv-1": BeadDetails(
                id="mv-1", title="T017", status="in_progress", state={"speckit_task_id": "T017"}
            )
        },
    )
    doc = _document(TaskEntry(kind="withdrawn", task_id="T017", line_number=1))
    impacts = await detect_impacts(doc, client=client, epic_id="mv-epic")
    assert len(impacts) == 1
    assert impacts[0].reason == "in-flight"
    assert impacts[0].bead_id == "mv-1"
    assert impacts[0].task_id == "T017"


@pytest.mark.asyncio
async def test_closed_task_is_a_blocking_impact() -> None:
    client = _make_client(
        children=[BeadSummary(id="mv-2", title="T019", status="closed")],
        details_by_id={
            "mv-2": BeadDetails(
                id="mv-2", title="T019", status="closed", state={"speckit_task_id": "T019"}
            )
        },
    )
    doc = _document(TaskEntry(kind="withdrawn", task_id="T019", line_number=1))
    impacts = await detect_impacts(doc, client=client, epic_id="mv-epic")
    assert len(impacts) == 1
    assert impacts[0].reason == "closed"


@pytest.mark.asyncio
async def test_open_unstarted_task_is_not_an_impact() -> None:
    client = _make_client(
        children=[BeadSummary(id="mv-3", title="T020", status="open")],
        details_by_id={
            "mv-3": BeadDetails(
                id="mv-3", title="T020", status="open", state={"speckit_task_id": "T020"}
            )
        },
    )
    doc = _document(TaskEntry(kind="withdrawn", task_id="T020", line_number=1))
    impacts = await detect_impacts(doc, client=client, epic_id="mv-epic")
    assert impacts == ()


@pytest.mark.asyncio
async def test_unstamped_bead_is_reported_never_closed() -> None:
    # A bead under the epic with no speckit_task_id at all (research R7).
    client = _make_client(
        children=[BeadSummary(id="mv-4", title="mystery", status="open")],
        details_by_id={"mv-4": BeadDetails(id="mv-4", title="mystery", status="open", state={})},
    )
    doc = _document(TaskEntry(kind="withdrawn", task_id="T099", line_number=1))
    impacts = await detect_impacts(doc, client=client, epic_id="mv-epic")
    unstamped = [i for i in impacts if i.reason == "unstamped"]
    assert len(unstamped) == 1
    assert unstamped[0].bead_id == "mv-4"
    assert unstamped[0].task_id == ""


@pytest.mark.asyncio
async def test_withdrawn_task_with_no_bead_yet_is_not_an_impact() -> None:
    # Delta applied before any refuel ran — nothing in flight to refuse on.
    client = _make_client(children=[], details_by_id={})
    doc = _document(TaskEntry(kind="withdrawn", task_id="T017", line_number=1))
    impacts = await detect_impacts(doc, client=client, epic_id="mv-epic")
    assert impacts == ()


@pytest.mark.asyncio
async def test_added_task_entries_never_produce_impacts() -> None:
    client = _make_client(children=[], details_by_id={})
    doc = _document(TaskEntry(kind="added", task_id="T042", line="A new task", line_number=1))
    impacts = await detect_impacts(doc, client=client, epic_id="mv-epic")
    assert impacts == ()
