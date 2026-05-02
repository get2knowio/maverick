"""Unit tests for bead generation actions."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.beads.models import BeadDefinition
from maverick.library.actions.beads import (
    create_beads,
    wire_dependencies,
)

# =============================================================================
# create_beads
# =============================================================================


class TestCreateBeads:
    """Tests for create_beads action."""

    def _make_epic_def(self) -> dict:
        return {
            "title": "test-project",
            "bead_type": "epic",
            "priority": 1,
            "category": "foundation",
            "description": "Test epic",
            "phase_names": ["Phase 1"],
            "task_ids": ["T001"],
        }

    def _make_work_def(self, title: str = "Foundation") -> dict:
        return {
            "title": title,
            "bead_type": "task",
            "priority": 1,
            "category": "foundation",
            "description": "Test bead",
            "phase_names": ["Phase 1"],
            "task_ids": ["T001"],
        }

    @pytest.mark.asyncio
    async def test_dry_run_returns_synthetic_ids(self) -> None:
        result = await create_beads(
            epic_definition=self._make_epic_def(),
            work_definitions=[self._make_work_def()],
            dry_run=True,
            cwd=Path("/tmp"),
        )

        assert result.epic is not None
        assert result.epic["bd_id"] == "dry-run-epic"
        assert len(result.work_beads) == 1
        assert result.work_beads[0]["bd_id"] == "dry-run-0"
        assert result.created_map["Foundation"] == "dry-run-0"
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_creates_beads_via_client(self) -> None:
        from maverick.beads.models import CreatedBead

        mock_client = AsyncMock()
        epic_def_obj = BeadDefinition.model_validate(self._make_epic_def())
        work_def_obj = BeadDefinition.model_validate(self._make_work_def())

        mock_client.create_bead.side_effect = [
            CreatedBead(bd_id="epic-123", definition=epic_def_obj),
            CreatedBead(bd_id="bead-456", definition=work_def_obj),
        ]

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await create_beads(
                epic_definition=self._make_epic_def(),
                work_definitions=[self._make_work_def()],
                dry_run=False,
                cwd=Path("/tmp"),
            )

        assert result.epic is not None
        assert result.epic["bd_id"] == "epic-123"
        assert len(result.work_beads) == 1
        assert result.created_map["Foundation"] == "bead-456"
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_handles_epic_creation_failure(self) -> None:
        mock_client = AsyncMock()
        mock_client.create_bead.side_effect = RuntimeError("bd not found")

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await create_beads(
                epic_definition=self._make_epic_def(),
                work_definitions=[self._make_work_def()],
                dry_run=False,
                cwd=Path("/tmp"),
            )

        assert result.epic is None
        assert len(result.errors) == 1
        assert "Epic creation failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_handles_work_bead_creation_failure(self) -> None:
        from maverick.beads.models import CreatedBead

        mock_client = AsyncMock()
        epic_def_obj = BeadDefinition.model_validate(self._make_epic_def())

        mock_client.create_bead.side_effect = [
            CreatedBead(bd_id="epic-123", definition=epic_def_obj),
            RuntimeError("bead creation failed"),
        ]

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await create_beads(
                epic_definition=self._make_epic_def(),
                work_definitions=[self._make_work_def()],
                dry_run=False,
                cwd=Path("/tmp"),
            )

        assert result.epic is not None
        assert len(result.work_beads) == 0
        assert len(result.errors) == 1


# =============================================================================
# wire_dependencies
# =============================================================================


class TestWireDependencies:
    """Tests for wire_dependencies action."""

    def _make_definitions(self) -> list[dict]:
        return [
            {
                "title": "Foundation",
                "bead_type": "task",
                "priority": 1,
                "category": "foundation",
                "phase_names": ["Phase 1"],
                "task_ids": ["T001"],
            },
            {
                "title": "Greeting",
                "bead_type": "task",
                "priority": 2,
                "category": "user_story",
                "phase_names": ["Phase 2"],
                "user_story_id": "US1",
                "task_ids": ["T002"],
            },
            {
                "title": "Cleanup",
                "bead_type": "task",
                "priority": 3,
                "category": "cleanup",
                "phase_names": ["Phase 3"],
                "task_ids": ["T003"],
            },
        ]

    def _make_created_map(self) -> dict[str, str]:
        return {
            "Foundation": "bead-foundation",
            "Greeting": "bead-greeting",
            "Cleanup": "bead-cleanup",
        }

    @pytest.mark.asyncio
    async def test_dry_run_computes_structural_deps(self) -> None:
        result = await wire_dependencies(
            work_definitions=self._make_definitions(),
            created_map=self._make_created_map(),
            tasks_content="",
            extracted_deps="[]",
            dry_run=True,
            cwd=Path("/tmp"),
        )

        assert result.success is True
        assert len(result.errors) == 0
        # Foundation -> Greeting, Greeting -> Cleanup = 2 deps
        assert len(result.dependencies) == 2

        dep_pairs = [(d["blocker_id"], d["blocked_id"]) for d in result.dependencies]
        assert ("bead-foundation", "bead-greeting") in dep_pairs
        assert ("bead-greeting", "bead-cleanup") in dep_pairs

    @pytest.mark.asyncio
    async def test_inter_story_deps_from_extracted(self) -> None:
        defs = [
            {
                "title": "Story A",
                "bead_type": "task",
                "priority": 1,
                "category": "user_story",
                "phase_names": ["Phase 1"],
                "user_story_id": "US1",
                "task_ids": ["T001"],
            },
            {
                "title": "Story B",
                "bead_type": "task",
                "priority": 2,
                "category": "user_story",
                "phase_names": ["Phase 2"],
                "user_story_id": "US3",
                "task_ids": ["T002"],
            },
        ]
        created_map = {"Story A": "bead-a", "Story B": "bead-b"}
        extracted = json.dumps([["US3", "US1"]])

        result = await wire_dependencies(
            work_definitions=defs,
            created_map=created_map,
            tasks_content="",
            extracted_deps=extracted,
            dry_run=True,
            cwd=Path("/tmp"),
        )

        dep_pairs = [(d["blocker_id"], d["blocked_id"]) for d in result.dependencies]
        # US3 depends on US1 means US1 blocks US3 => (bead-a, bead-b)
        assert ("bead-a", "bead-b") in dep_pairs

    @pytest.mark.asyncio
    async def test_invalid_extracted_deps_gracefully_ignored(self) -> None:
        defs = [self._make_definitions()[1]]  # Just one story
        created_map = {"Greeting": "bead-greeting"}

        result = await wire_dependencies(
            work_definitions=defs,
            created_map=created_map,
            tasks_content="",
            extracted_deps="not valid json {{{",
            dry_run=True,
            cwd=Path("/tmp"),
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_wires_via_client(self) -> None:
        mock_client = AsyncMock()
        mock_client.add_dependency.return_value = None
        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await wire_dependencies(
                work_definitions=self._make_definitions(),
                created_map=self._make_created_map(),
                tasks_content="",
                extracted_deps="[]",
                dry_run=False,
                cwd=Path("/tmp"),
            )

        assert result.success is True
        assert mock_client.add_dependency.call_count == 2

    @pytest.mark.asyncio
    async def test_foundation_blocks_cleanup_when_no_stories(self) -> None:
        defs = [
            {
                "title": "Foundation",
                "bead_type": "task",
                "priority": 1,
                "category": "foundation",
                "phase_names": ["Phase 1"],
                "task_ids": ["T001"],
            },
            {
                "title": "Cleanup",
                "bead_type": "task",
                "priority": 2,
                "category": "cleanup",
                "phase_names": ["Phase 2"],
                "task_ids": ["T002"],
            },
        ]
        created_map = {"Foundation": "bead-f", "Cleanup": "bead-c"}

        result = await wire_dependencies(
            work_definitions=defs,
            created_map=created_map,
            tasks_content="",
            extracted_deps="[]",
            dry_run=True,
            cwd=Path("/tmp"),
        )

        dep_pairs = [(d["blocker_id"], d["blocked_id"]) for d in result.dependencies]
        assert ("bead-f", "bead-c") in dep_pairs


class TestSelectNextBead:
    """Tests for select_next_bead action."""

    @pytest.mark.asyncio
    async def test_found_bead(self) -> None:
        from maverick.beads.models import ReadyBead
        from maverick.library.actions.beads import select_next_bead

        mock_client = AsyncMock()
        mock_client.ready.return_value = [
            ReadyBead(id="b-1", title="Fix lint", priority=5, description="Fix all lint")
        ]

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("epic-1", cwd=Path("/tmp"))

        assert result.found is True
        assert result.bead_id == "b-1"
        assert result.title == "Fix lint"
        assert result.epic_id == "epic-1"
        assert result.done is False

    @pytest.mark.asyncio
    async def test_no_beads_found(self) -> None:
        from maverick.library.actions.beads import select_next_bead

        mock_client = AsyncMock()
        mock_client.ready.return_value = []

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("epic-1", cwd=Path("/tmp"))

        assert result.found is False
        assert result.done is True
        assert result.bead_id == ""
        assert result.epic_id == "epic-1"

    @pytest.mark.asyncio
    async def test_empty_epic_queries_all_ready(self) -> None:
        """When epic_id is empty, select_next_bead queries all ready beads."""
        from maverick.beads.models import ReadyBead
        from maverick.library.actions.beads import select_next_bead

        mock_client = AsyncMock()
        mock_client.ready.return_value = [
            ReadyBead(
                id="b-2",
                title="Global task",
                priority=3,
                description="A task",
                parent_id="auto-epic-99",
            )
        ]

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("", cwd=Path("/tmp"))

        # Should pass None to client.ready (no parent filter)
        mock_client.ready.assert_called_once_with(None, limit=10)
        assert result.found is True
        assert result.bead_id == "b-2"
        assert result.epic_id == "auto-epic-99"

    @pytest.mark.asyncio
    async def test_empty_epic_fetches_description_when_missing(self) -> None:
        """When epic_id is empty and bead has no description, show() is called."""
        from maverick.beads.models import ReadyBead
        from maverick.library.actions.beads import select_next_bead

        mock_client = AsyncMock()
        mock_client.ready.return_value = [
            ReadyBead(
                id="b-3",
                title="No desc",
                priority=1,
                description="",
                parent_id="ep-1",
            )
        ]

        class _BeadShowResult:
            description = "Fetched from show"
            state: dict[str, str] = {}

        class _EpicShowResult:
            description = "Epic description"
            state = {"flight_plan_name": "my-plan"}

        async def _show_side_effect(bead_id: str) -> object:
            if bead_id == "b-3":
                return _BeadShowResult()
            return _EpicShowResult()

        mock_client.show.side_effect = _show_side_effect

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("", cwd=Path("/tmp"))

        # show() called for: label check, bead description, epic flight_plan_name
        assert mock_client.show.call_count == 3
        assert result.description == "Fetched from show"
        assert result.flight_plan_name == "my-plan"

    @pytest.mark.asyncio
    async def test_empty_epic_no_beads_returns_done(self) -> None:
        """When epic_id is empty and no beads found, result is done."""
        from maverick.library.actions.beads import select_next_bead

        mock_client = AsyncMock()
        mock_client.ready.return_value = []

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("", cwd=Path("/tmp"))

        mock_client.ready.assert_called_once_with(None, limit=10)
        assert result.found is False
        assert result.done is True
        assert result.epic_id == ""

    @pytest.mark.asyncio
    async def test_flight_plan_name_resolved_from_epic(self) -> None:
        """flight_plan_name is resolved from epic state metadata."""
        from maverick.beads.models import BeadDetails, ReadyBead
        from maverick.library.actions.beads import select_next_bead

        mock_client = AsyncMock()
        mock_client.ready.return_value = [
            ReadyBead(
                id="b-1",
                title="Task 1",
                priority=1,
                description="A task",
                parent_id="epic-42",
            )
        ]
        mock_client.show.return_value = BeadDetails(
            id="epic-42",
            title="add-user-auth",
            state={"flight_plan_name": "add-user-auth"},
        )

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("epic-42", cwd=Path("/tmp"))

        assert result.flight_plan_name == "add-user-auth"

    @pytest.mark.asyncio
    async def test_flight_plan_name_empty_when_no_state(self) -> None:
        """flight_plan_name defaults to empty when epic has no state."""
        from maverick.beads.models import BeadDetails, ReadyBead
        from maverick.library.actions.beads import select_next_bead

        mock_client = AsyncMock()
        mock_client.ready.return_value = [
            ReadyBead(
                id="b-1",
                title="Task 1",
                priority=1,
                description="A task",
                parent_id="epic-42",
            )
        ]
        mock_client.show.return_value = BeadDetails(
            id="epic-42",
            title="some-epic",
            state={},
        )

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("epic-42", cwd=Path("/tmp"))

        assert result.flight_plan_name == ""


class TestMarkBeadComplete:
    """Tests for mark_bead_complete action."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from maverick.beads.models import ClosedBead
        from maverick.library.actions.beads import mark_bead_complete

        mock_client = AsyncMock()
        mock_client.close.return_value = ClosedBead(
            id="b-1", status="closed", closed_at="2025-01-01T00:00:00Z"
        )

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await mark_bead_complete("b-1", reason="done", cwd=Path("/tmp"))

        assert result.success is True
        assert result.bead_id == "b-1"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_failure(self) -> None:
        from maverick.library.actions.beads import mark_bead_complete

        mock_client = AsyncMock()
        mock_client.close.side_effect = RuntimeError("close failed")

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await mark_bead_complete("b-1", cwd=Path("/tmp"))

        assert result.success is False
        assert "close failed" in result.error
