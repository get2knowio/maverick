"""Integration tests for the full speckit bead generation pipeline.

Uses mocked BeadClient to test the end-to-end orchestration without
requiring the ``bd`` CLI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import BeadCategory, CreatedBead
from maverick.beads.speckit import generate_beads_from_speckit
from maverick.exceptions.beads import SpecKitParseError


def _make_create_side_effect(
    counter: list[int],
) -> AsyncMock:
    """Create a side effect returning incrementing bead IDs."""

    async def _create(
        definition,  # noqa: ANN001
        parent_id=None,  # noqa: ANN001
    ) -> CreatedBead:
        counter[0] += 1
        return CreatedBead(
            bd_id=f"bead-{counter[0]:03d}",
            definition=definition,
        )

    return AsyncMock(side_effect=_create)


class TestGenerateBeadsFromSpeckit:
    """Tests for generate_beads_from_speckit()."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, spec_dir_with_tasks: Path) -> None:
        counter = [0]
        client = AsyncMock(spec=BeadClient)
        client.create_bead = _make_create_side_effect(counter)
        client.add_dependency = AsyncMock()
        client.sync = AsyncMock()

        result = await generate_beads_from_speckit(spec_dir_with_tasks, client)

        assert result.success
        assert result.epic is not None
        assert result.epic.bd_id == "bead-001"
        assert len(result.work_beads) > 0
        assert len(result.dependencies) > 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_dir_raises(self, temp_dir: Path) -> None:
        client = AsyncMock(spec=BeadClient)
        with pytest.raises(SpecKitParseError, match="does not exist"):
            await generate_beads_from_speckit(temp_dir / "nonexistent", client)

    @pytest.mark.asyncio
    async def test_missing_tasks_md_raises(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "empty-spec"
        spec_dir.mkdir()
        client = AsyncMock(spec=BeadClient)
        with pytest.raises(SpecKitParseError, match="tasks.md not found"):
            await generate_beads_from_speckit(spec_dir, client)

    @pytest.mark.asyncio
    async def test_empty_phases_raises(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "no-phases"
        spec_dir.mkdir()
        (spec_dir / "tasks.md").write_text("# Tasks\n\nNo phases here.\n")
        client = AsyncMock(spec=BeadClient)
        with pytest.raises(SpecKitParseError, match="No phases found"):
            await generate_beads_from_speckit(spec_dir, client)

    @pytest.mark.asyncio
    async def test_dry_run(self, spec_dir_with_tasks: Path) -> None:
        client = AsyncMock(spec=BeadClient)

        result = await generate_beads_from_speckit(
            spec_dir_with_tasks, client, dry_run=True
        )

        assert result.success
        assert result.epic is not None
        assert result.epic.bd_id == "dry-run-epic"
        assert all(b.bd_id.startswith("dry-run-") for b in result.work_beads)
        client.create_bead.assert_not_called()
        client.add_dependency.assert_not_called()
        client.sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_epic_creation_failure(self, spec_dir_with_tasks: Path) -> None:
        client = AsyncMock(spec=BeadClient)
        client.create_bead = AsyncMock(side_effect=Exception("bd not initialized"))

        result = await generate_beads_from_speckit(spec_dir_with_tasks, client)

        assert not result.success
        assert result.epic is None
        assert "Epic creation failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_partial_bead_creation_failure(
        self, spec_dir_with_tasks: Path
    ) -> None:
        call_count = [0]

        async def _create_with_failures(
            definition,  # noqa: ANN001
            parent_id=None,  # noqa: ANN001
        ) -> CreatedBead:
            call_count[0] += 1
            if call_count[0] == 1:
                return CreatedBead(bd_id="epic-001", definition=definition)
            if call_count[0] == 3:
                raise Exception("Network error")  # noqa: TRY002
            return CreatedBead(
                bd_id=f"bead-{call_count[0]:03d}",
                definition=definition,
            )

        client = AsyncMock(spec=BeadClient)
        client.create_bead = AsyncMock(side_effect=_create_with_failures)
        client.add_dependency = AsyncMock()
        client.sync = AsyncMock()

        result = await generate_beads_from_speckit(spec_dir_with_tasks, client)

        assert not result.success
        assert result.epic is not None
        assert len(result.errors) > 0
        assert "Network error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_dependency_wiring(self, spec_dir_with_deps: Path) -> None:
        counter = [0]
        client = AsyncMock(spec=BeadClient)
        client.create_bead = _make_create_side_effect(counter)
        client.add_dependency = AsyncMock()
        client.sync = AsyncMock()

        result = await generate_beads_from_speckit(spec_dir_with_deps, client)

        assert result.success
        assert len(result.dependencies) > 0

        # Foundation should block story beads
        foundation_deps = [d for d in result.dependencies if d.from_id == "bead-002"]
        assert len(foundation_deps) > 0

    @pytest.mark.asyncio
    async def test_sync_failure_captured(self, spec_dir_with_tasks: Path) -> None:
        counter = [0]
        client = AsyncMock(spec=BeadClient)
        client.create_bead = _make_create_side_effect(counter)
        client.add_dependency = AsyncMock()
        client.sync = AsyncMock(side_effect=Exception("Sync failed"))

        result = await generate_beads_from_speckit(spec_dir_with_tasks, client)

        assert result.epic is not None
        assert len(result.work_beads) > 0
        assert any("sync" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_bead_categories(self, spec_dir_with_tasks: Path) -> None:
        counter = [0]
        client = AsyncMock(spec=BeadClient)
        client.create_bead = _make_create_side_effect(counter)
        client.add_dependency = AsyncMock()
        client.sync = AsyncMock()

        result = await generate_beads_from_speckit(spec_dir_with_tasks, client)

        categories = [b.definition.category for b in result.work_beads]
        assert BeadCategory.FOUNDATION in categories
        assert BeadCategory.USER_STORY in categories
        assert BeadCategory.CLEANUP in categories
