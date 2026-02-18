"""Unit tests for enrich_bead_descriptions action."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.beads import enrich_bead_descriptions


class TestEnrichBeadDescriptions:
    """Tests for enrich_bead_descriptions action."""

    @pytest.mark.asyncio
    async def test_enriches_multiple_definitions(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "specs" / "test"
        spec_dir.mkdir(parents=True)
        (spec_dir / "spec.md").write_text("# Test Spec")
        (spec_dir / "plan.md").write_text("# Test Plan")

        work_defs = [
            {"title": "Bead 1", "category": "FOUNDATION", "tasks": "- task1"},
            {"title": "Bead 2", "category": "USER_STORY", "tasks": "- task2"},
        ]

        mock_enricher = AsyncMock()
        mock_enricher.generate.side_effect = [
            "## Objective\nBead 1 enriched",
            "## Objective\nBead 2 enriched",
        ]

        with patch(
            "maverick.agents.generators.bead_enricher.BeadEnricherGenerator",
            return_value=mock_enricher,
        ):
            result = await enrich_bead_descriptions(
                work_definitions=work_defs,
                spec_dir=str(spec_dir),
            )

        assert len(result) == 2
        assert result[0]["description"] == "## Objective\nBead 1 enriched"
        assert result[1]["description"] == "## Objective\nBead 2 enriched"
        # Original fields preserved
        assert result[0]["title"] == "Bead 1"
        assert result[1]["category"] == "USER_STORY"

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_failure(self, temp_dir: Path) -> None:
        """On generator failure, original description is kept."""
        spec_dir = temp_dir / "specs" / "test"
        spec_dir.mkdir(parents=True)

        work_defs = [
            {"title": "Good", "description": "original good", "tasks": "- t"},
            {"title": "Bad", "description": "original bad", "tasks": "- t"},
            {"title": "Good2", "description": "original good2", "tasks": "- t"},
        ]

        mock_enricher = AsyncMock()
        mock_enricher.generate.side_effect = [
            "enriched good",
            RuntimeError("LLM error"),
            "enriched good2",
        ]

        with patch(
            "maverick.agents.generators.bead_enricher.BeadEnricherGenerator",
            return_value=mock_enricher,
        ):
            result = await enrich_bead_descriptions(
                work_definitions=work_defs,
                spec_dir=str(spec_dir),
            )

        assert len(result) == 3
        assert result[0]["description"] == "enriched good"
        assert result[1]["description"] == "original bad"  # kept original
        assert result[2]["description"] == "enriched good2"

    @pytest.mark.asyncio
    async def test_empty_generator_result_keeps_original(self, temp_dir: Path) -> None:
        """Empty string from generator keeps original description."""
        spec_dir = temp_dir / "specs" / "test"
        spec_dir.mkdir(parents=True)

        work_defs = [{"title": "Test", "description": "original", "tasks": "- t"}]

        mock_enricher = AsyncMock()
        mock_enricher.generate.return_value = ""

        with patch(
            "maverick.agents.generators.bead_enricher.BeadEnricherGenerator",
            return_value=mock_enricher,
        ):
            result = await enrich_bead_descriptions(
                work_definitions=work_defs,
                spec_dir=str(spec_dir),
            )

        assert result[0]["description"] == "original"

    @pytest.mark.asyncio
    async def test_missing_spec_files(self, temp_dir: Path) -> None:
        """Missing spec/plan files should not crash."""
        spec_dir = temp_dir / "specs" / "nonexistent"
        spec_dir.mkdir(parents=True)
        # No spec.md or plan.md

        work_defs = [{"title": "Test", "tasks": "- t"}]

        mock_enricher = AsyncMock()
        mock_enricher.generate.return_value = "enriched"

        with patch(
            "maverick.agents.generators.bead_enricher.BeadEnricherGenerator",
            return_value=mock_enricher,
        ):
            result = await enrich_bead_descriptions(
                work_definitions=work_defs,
                spec_dir=str(spec_dir),
            )

        assert result[0]["description"] == "enriched"

    @pytest.mark.asyncio
    async def test_passes_dependency_section_to_generator(self, temp_dir: Path) -> None:
        spec_dir = temp_dir / "specs" / "test"
        spec_dir.mkdir(parents=True)

        work_defs = [{"title": "Test", "tasks": "- t"}]

        mock_enricher = AsyncMock()
        mock_enricher.generate.return_value = "enriched"

        with patch(
            "maverick.agents.generators.bead_enricher.BeadEnricherGenerator",
            return_value=mock_enricher,
        ):
            await enrich_bead_descriptions(
                work_definitions=work_defs,
                spec_dir=str(spec_dir),
                dependency_section="US3 depends on US1",
            )

        # Check the context passed to generate
        call_context = mock_enricher.generate.call_args[0][0]
        assert call_context["dependency_context"] == "US3 depends on US1"

    @pytest.mark.asyncio
    async def test_does_not_mutate_original(self, temp_dir: Path) -> None:
        """Original work_definitions should not be mutated."""
        spec_dir = temp_dir / "specs" / "test"
        spec_dir.mkdir(parents=True)

        original = {"title": "Test", "description": "original", "tasks": "- t"}
        work_defs = [original]

        mock_enricher = AsyncMock()
        mock_enricher.generate.return_value = "enriched"

        with patch(
            "maverick.agents.generators.bead_enricher.BeadEnricherGenerator",
            return_value=mock_enricher,
        ):
            result = await enrich_bead_descriptions(
                work_definitions=work_defs,
                spec_dir=str(spec_dir),
            )

        assert original["description"] == "original"  # not mutated
        assert result[0]["description"] == "enriched"
