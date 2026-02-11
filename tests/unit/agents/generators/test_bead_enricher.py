"""Unit tests for BeadEnricherGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maverick.agents.generators.bead_enricher import BeadEnricherGenerator


class TestBeadEnricherConstruction:
    """Tests for BeadEnricherGenerator construction."""

    def test_construction_with_defaults(self) -> None:
        enricher = BeadEnricherGenerator()

        assert enricher.name == "bead-enricher"
        assert "enricher" in enricher.system_prompt.lower()
        assert enricher.model == "claude-sonnet-4-5-20250929"

    def test_construction_with_custom_model(self) -> None:
        enricher = BeadEnricherGenerator(model="claude-opus-4-5-20250929")

        assert enricher.model == "claude-opus-4-5-20250929"


class TestBeadEnricherGenerate:
    """Tests for BeadEnricherGenerator.generate()."""

    @pytest.mark.asyncio
    async def test_empty_context_returns_empty_string(self) -> None:
        enricher = BeadEnricherGenerator()

        result = await enricher.generate({})

        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_context_with_usage(self) -> None:
        enricher = BeadEnricherGenerator()

        result, usage = await enricher.generate(  # type: ignore[misc]
            {}, return_usage=True
        )

        assert result == ""
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    @pytest.mark.asyncio
    async def test_generates_enriched_description(self) -> None:
        enricher = BeadEnricherGenerator()

        mock_response = (
            "## Objective\nImplement the greeting CLI.\n\n"
            "## Acceptance Criteria\n- [ ] greet command exists\n"
        )
        with patch.object(
            enricher,
            "_query",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await enricher.generate(
                {
                    "title": "Implement greeting CLI",
                    "category": "USER_STORY",
                    "tasks": "- Add click command",
                    "checkpoints": "- greet command exists",
                }
            )

        assert "Objective" in result
        assert "Acceptance Criteria" in result

    @pytest.mark.asyncio
    async def test_generates_with_usage(self) -> None:
        from maverick.agents.result import AgentUsage

        enricher = BeadEnricherGenerator()

        mock_response = "## Objective\nSetup project."
        mock_usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=None, duration_ms=0
        )

        with patch.object(
            enricher,
            "_query_with_usage",
            new_callable=AsyncMock,
            return_value=(mock_response, mock_usage),
        ):
            result, usage = await enricher.generate(  # type: ignore[misc]
                {
                    "title": "Setup project",
                    "category": "FOUNDATION",
                    "tasks": "- Initialize repo",
                },
                return_usage=True,
            )

        assert result == mock_response
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50

    @pytest.mark.asyncio
    async def test_prompt_includes_title_and_category(self) -> None:
        enricher = BeadEnricherGenerator()

        with patch.object(
            enricher,
            "_query",
            new_callable=AsyncMock,
            return_value="enriched",
        ) as mock_query:
            await enricher.generate(
                {
                    "title": "Add user auth",
                    "category": "USER_STORY",
                    "tasks": "- Implement login",
                }
            )

        prompt = mock_query.call_args[0][0]
        assert "Add user auth" in prompt
        assert "USER_STORY" in prompt
        assert "Implement login" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_spec_and_plan(self) -> None:
        enricher = BeadEnricherGenerator()

        with patch.object(
            enricher,
            "_query",
            new_callable=AsyncMock,
            return_value="enriched",
        ) as mock_query:
            await enricher.generate(
                {
                    "title": "Test bead",
                    "tasks": "- something",
                    "spec_content": "The spec content here",
                    "plan_content": "The plan content here",
                }
            )

        prompt = mock_query.call_args[0][0]
        assert "The spec content here" in prompt
        assert "The plan content here" in prompt

    @pytest.mark.asyncio
    async def test_handles_only_title(self) -> None:
        """Title alone should be enough to trigger generation."""
        enricher = BeadEnricherGenerator()

        with patch.object(
            enricher,
            "_query",
            new_callable=AsyncMock,
            return_value="enriched",
        ):
            result = await enricher.generate({"title": "Just a title"})

        assert result == "enriched"

    @pytest.mark.asyncio
    async def test_handles_only_checkpoints(self) -> None:
        """Checkpoints alone should trigger generation."""
        enricher = BeadEnricherGenerator()

        with patch.object(
            enricher,
            "_query",
            new_callable=AsyncMock,
            return_value="enriched",
        ):
            result = await enricher.generate(
                {
                    "checkpoints": "- tests pass",
                }
            )

        assert result == "enriched"
