"""Shared fixtures for SpeckitRefuelWorkflow tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from maverick.beads.models import BeadDetails, BeadSummary
from maverick.workflows.refuel_speckit.workflow import SpeckitRefuelWorkflow

#: tasks.md fixture mirroring tests/unit/speckit/conftest.py's FULL_TASKS_MD,
#: kept small and dependency-free for fast workflow-level tests.
WORKFLOW_TASKS_MD = """\
## Phase 1: Setup

- [ ] T001 Initialize project
- [ ] T002 [P] Create config file in src/config.py

## Phase 2: Core

- [ ] T003 Implement core feature in src/core.py
"""

WORKFLOW_SPEC_MD = """\
# Feature Specification: Workflow Sample

## Success Criteria

### Measurable Outcomes

- **SC-001**: The feature works.
"""


def make_mock_bead_client(
    *,
    existing_epics: list[BeadSummary] | None = None,
    epic_details_by_id: dict[str, BeadDetails] | None = None,
    children_by_epic: dict[str, list[BeadSummary]] | None = None,
    create_bead_side_effect: Any = None,
) -> MagicMock:
    """Build a MagicMock standing in for ``BeadClient``.

    All async methods used by SpeckitRefuelWorkflow are stubbed:
    ``create_bead``, ``add_dependency``, ``set_state``, ``query``,
    ``show``, ``children``.
    """
    client = MagicMock()
    epic_details_by_id = dict(epic_details_by_id or {})
    children_by_epic = dict(children_by_epic or {})
    counter = {"n": 0}

    async def _default_create_bead(definition: Any, parent_id: str | None = None) -> Any:
        counter["n"] += 1
        return SimpleNamespace(bd_id=f"bead-{counter['n']}", definition=definition)

    client.create_bead = AsyncMock(side_effect=create_bead_side_effect or _default_create_bead)
    client.add_dependency = AsyncMock(return_value=None)
    client.set_state = AsyncMock(return_value=None)
    client.query = AsyncMock(return_value=existing_epics or [])

    async def _show(bead_id: str) -> BeadDetails:
        if bead_id in epic_details_by_id:
            return epic_details_by_id[bead_id]
        raise LookupError(bead_id)

    client.show = AsyncMock(side_effect=_show)

    async def _children(parent_id: str) -> list[BeadSummary]:
        return children_by_epic.get(parent_id, [])

    client.children = AsyncMock(side_effect=_children)
    return client


async def collect_events(
    workflow: SpeckitRefuelWorkflow,
    inputs: dict[str, Any],
    *,
    ignore_exception: bool = False,
) -> tuple[list[Any], Any]:
    """Drain the execute() generator and return (events, workflow.result)."""
    events: list[Any] = []
    try:
        async for event in workflow.execute(inputs):
            events.append(event)
    except Exception:
        if not ignore_exception:
            raise
    return events, workflow.result
