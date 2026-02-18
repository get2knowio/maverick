"""Unit tests for bead generation actions."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.beads.models import BeadDefinition
from maverick.library.actions.beads import (
    create_beads,
    parse_speckit,
    wire_dependencies,
)

# =============================================================================
# Action registration
# =============================================================================


class TestBeadActionRegistration:
    """Tests for bead action registration metadata."""

    def test_create_beads_requires_bd(self) -> None:
        """create_beads is registered with requires=('bd',) via register_all_actions."""
        from maverick.dsl.serialization.registry import ComponentRegistry
        from maverick.library.actions import register_all_actions

        registry = ComponentRegistry()
        register_all_actions(registry)

        requires = registry.actions.get_requires("create_beads")
        assert "bd" in requires

    def test_wire_dependencies_requires_bd(self) -> None:
        """wire_dependencies is registered with requires=('bd',)."""
        from maverick.dsl.serialization.registry import ComponentRegistry
        from maverick.library.actions import register_all_actions

        registry = ComponentRegistry()
        register_all_actions(registry)

        requires = registry.actions.get_requires("wire_dependencies")
        assert "bd" in requires

    def test_parse_speckit_has_no_requires(self) -> None:
        """parse_speckit should not require bd."""
        from maverick.dsl.serialization.registry import ComponentRegistry
        from maverick.library.actions import register_all_actions

        registry = ComponentRegistry()
        register_all_actions(registry)

        requires = registry.actions.get_requires("parse_speckit")
        assert "bd" not in requires


# =============================================================================
# parse_speckit
# =============================================================================


class TestParseSpeckit:
    """Tests for parse_speckit action."""

    @pytest.mark.asyncio
    async def test_raises_on_nonexistent_dir(self, temp_dir: Path) -> None:
        nonexistent = temp_dir / "does-not-exist"
        with pytest.raises(RuntimeError, match="does not exist"):
            await parse_speckit(str(nonexistent))

    @pytest.mark.asyncio
    async def test_raises_on_missing_tasks_md(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "spec"
        spec_dir.mkdir()
        with pytest.raises(RuntimeError, match="tasks.md not found"):
            await parse_speckit(str(spec_dir))

    @pytest.mark.asyncio
    async def test_raises_on_no_phases(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "spec"
        spec_dir.mkdir()
        (spec_dir / "tasks.md").write_text("no phases here\n")
        with pytest.raises(RuntimeError, match="No phases found"):
            await parse_speckit(str(spec_dir))

    @pytest.mark.asyncio
    async def test_parses_simple_spec(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "001-test"
        spec_dir.mkdir()
        (spec_dir / "tasks.md").write_text(
            "## Phase 1: Setup\n\n"
            "- [ ] T001 Initialize project\n\n"
            "## Phase 2: User Story 1 - Greeting\n\n"
            "- [ ] T002 Add greeting CLI\n\n"
            "## Phase 3: Polish\n\n"
            "- [ ] T003 Add tests\n\n"
            "## User Story Dependencies\n\n"
            "US1 has no inter-story dependencies.\n"
        )

        result = await parse_speckit(str(spec_dir))

        assert result.epic_definition["title"] == "001-test"
        assert result.epic_definition["bead_type"] == "epic"
        assert len(result.work_definitions) >= 1
        assert "T001" in result.tasks_content or (
            "Initialize project" in result.tasks_content
        )

    @pytest.mark.asyncio
    async def test_extracts_dependency_section(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "spec"
        spec_dir.mkdir()
        (spec_dir / "tasks.md").write_text(
            "## Phase 1: User Story 1 - Foo\n\n"
            "- [ ] T001 Foo task\n\n"
            "## Dependencies\n\n"
            "US3 depends on US1 for the data model.\n"
        )

        result = await parse_speckit(str(spec_dir))

        assert "US3 depends on US1" in result.dependency_section

    @pytest.mark.asyncio
    async def test_empty_dependency_section(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "spec"
        spec_dir.mkdir()
        (spec_dir / "tasks.md").write_text(
            "## Phase 1: User Story 1 - Foo\n\n- [ ] T001 Foo task\n"
        )

        result = await parse_speckit(str(spec_dir))

        assert result.dependency_section == ""


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
        )

        assert result.epic is not None
        assert result.epic["bd_id"] == "dry-run-epic"
        assert len(result.work_beads) == 1
        assert result.work_beads[0]["bd_id"] == "dry-run-0"
        assert result.created_map["Foundation"] == "dry-run-0"
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_creates_beads_via_client(self) -> None:
        from maverick.beads.models import BeadDefinition, CreatedBead

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
            )

        assert result.epic is None
        assert len(result.errors) == 1
        assert "Epic creation failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_handles_work_bead_creation_failure(self) -> None:
        from maverick.beads.models import BeadDefinition, CreatedBead

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
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_wires_via_client(self) -> None:
        mock_client = AsyncMock()
        mock_client.add_dependency.return_value = None
        mock_client.sync.return_value = None

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await wire_dependencies(
                work_definitions=self._make_definitions(),
                created_map=self._make_created_map(),
                tasks_content="",
                extracted_deps="[]",
                dry_run=False,
            )

        assert result.success is True
        assert mock_client.add_dependency.call_count == 2
        mock_client.sync.assert_called_once()

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
            ReadyBead(
                id="b-1", title="Fix lint", priority=5, description="Fix all lint"
            )
        ]

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("epic-1")

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
            result = await select_next_bead("epic-1")

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
            result = await select_next_bead("")

        # Should pass None to client.ready (no parent filter)
        mock_client.ready.assert_called_once_with(None, limit=1)
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

        class _ShowResult:
            description = "Fetched from show"

        mock_client.show.return_value = _ShowResult()

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("")

        mock_client.show.assert_called_once_with("b-3")
        assert result.description == "Fetched from show"

    @pytest.mark.asyncio
    async def test_empty_epic_no_beads_returns_done(self) -> None:
        """When epic_id is empty and no beads found, result is done."""
        from maverick.library.actions.beads import select_next_bead

        mock_client = AsyncMock()
        mock_client.ready.return_value = []

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await select_next_bead("")

        mock_client.ready.assert_called_once_with(None, limit=1)
        assert result.found is False
        assert result.done is True
        assert result.epic_id == ""


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
            result = await mark_bead_complete("b-1", reason="done")

        assert result.success is True
        assert result.bead_id == "b-1"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_failure(self) -> None:
        from maverick.library.actions.beads import mark_bead_complete

        mock_client = AsyncMock()
        mock_client.close.side_effect = RuntimeError("close failed")

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await mark_bead_complete("b-1")

        assert result.success is False
        assert "close failed" in result.error


class TestCheckEpicDone:
    """Tests for check_epic_done action."""

    @pytest.mark.asyncio
    async def test_done(self) -> None:
        from maverick.library.actions.beads import check_epic_done

        mock_client = AsyncMock()
        mock_client.ready.return_value = []

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await check_epic_done("epic-1")

        assert result.done is True
        assert result.remaining_count == 0

    @pytest.mark.asyncio
    async def test_not_done(self) -> None:
        from maverick.beads.models import ReadyBead
        from maverick.library.actions.beads import check_epic_done

        mock_client = AsyncMock()
        mock_client.ready.return_value = [
            ReadyBead(id="b-1", title="T1", priority=1),
            ReadyBead(id="b-2", title="T2", priority=2),
        ]

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await check_epic_done("epic-1")

        assert result.done is False
        assert result.remaining_count == 2

    @pytest.mark.asyncio
    async def test_empty_epic_queries_all(self) -> None:
        """When epic_id is empty, check_epic_done queries all ready beads."""
        from maverick.library.actions.beads import check_epic_done

        mock_client = AsyncMock()
        mock_client.ready.return_value = []

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await check_epic_done("")

        # Should pass None to client.ready (no parent filter)
        mock_client.ready.assert_called_once_with(None, limit=10)
        assert result.done is True

    @pytest.mark.asyncio
    async def test_empty_epic_not_done(self) -> None:
        """When epic_id is empty and beads exist globally, not done."""
        from maverick.beads.models import ReadyBead
        from maverick.library.actions.beads import check_epic_done

        mock_client = AsyncMock()
        mock_client.ready.return_value = [
            ReadyBead(id="b-5", title="Remaining", priority=1),
        ]

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await check_epic_done("")

        mock_client.ready.assert_called_once_with(None, limit=10)
        assert result.done is False
        assert result.remaining_count == 1


class TestCreateBeadsFromFailures:
    """Tests for create_beads_from_failures action."""

    @pytest.mark.asyncio
    async def test_all_passed(self) -> None:
        from maverick.library.actions.beads import create_beads_from_failures

        result = await create_beads_from_failures(
            epic_id="epic-1",
            validation_result={"passed": True, "stages": []},
        )
        assert result.created_count == 0

    @pytest.mark.asyncio
    async def test_creates_beads_dry_run(self) -> None:
        from maverick.library.actions.beads import create_beads_from_failures

        result = await create_beads_from_failures(
            epic_id="epic-1",
            validation_result={
                "passed": False,
                "stages": ["test", "lint", "format"],
                "stage_results": {
                    "test": {"passed": False, "errors": ["test failed"]},
                    "lint": {"passed": False, "errors": ["lint error"]},
                    "format": {"passed": True, "errors": []},
                },
            },
            dry_run=True,
        )
        assert result.created_count == 2
        assert len(result.bead_ids) == 2
        assert result.bead_ids[0].startswith("dry-run-fix-")

    @pytest.mark.asyncio
    async def test_creates_beads_real(self) -> None:
        from maverick.beads.models import CreatedBead
        from maverick.library.actions.beads import create_beads_from_failures

        mock_client = AsyncMock()
        mock_client.create_bead.return_value = CreatedBead(
            bd_id="fix-1",
            definition=BeadDefinition(
                title="Fix: test validation failures",
                bead_type="task",
                priority=1,
                category="validation",
            ),
        )

        with patch("maverick.beads.client.BeadClient", return_value=mock_client):
            result = await create_beads_from_failures(
                epic_id="epic-1",
                validation_result={
                    "passed": False,
                    "stages": ["test"],
                    "stage_results": {
                        "test": {
                            "passed": False,
                            "errors": ["test failed"],
                        },
                    },
                },
            )
        assert result.created_count == 1
        assert mock_client.create_bead.called


class TestCreateBeadsFromFindings:
    """Tests for create_beads_from_findings action."""

    @pytest.mark.asyncio
    async def test_approved(self) -> None:
        from maverick.library.actions.beads import create_beads_from_findings

        result = await create_beads_from_findings(
            epic_id="epic-1",
            review_result={"recommendation": "approve", "issues": []},
        )
        assert result.created_count == 0

    @pytest.mark.asyncio
    async def test_no_issues(self) -> None:
        from maverick.library.actions.beads import create_beads_from_findings

        result = await create_beads_from_findings(
            epic_id="epic-1",
            review_result={"recommendation": "request_changes", "issues": []},
        )
        assert result.created_count == 0

    @pytest.mark.asyncio
    async def test_creates_beads_dry_run(self) -> None:
        from maverick.library.actions.beads import create_beads_from_findings

        result = await create_beads_from_findings(
            epic_id="epic-1",
            review_result={
                "recommendation": "request_changes",
                "issues": [
                    {
                        "file_path": "src/main.py",
                        "severity": "critical",
                        "description": "SQL injection",
                    },
                    {
                        "file_path": "src/main.py",
                        "severity": "minor",
                        "description": "Unused import",
                    },
                    {
                        "file_path": "src/utils.py",
                        "severity": "major",
                        "description": "Missing error handling",
                    },
                ],
            },
            dry_run=True,
        )
        # Groups by file: src/main.py (2 issues), src/utils.py (1 issue)
        assert result.created_count == 2
        assert len(result.bead_ids) == 2
