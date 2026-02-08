"""Unit tests for DependencyExtractor generator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maverick.agents.generators.dependency_extractor import DependencyExtractor


class TestDependencyExtractorConstruction:
    """Tests for DependencyExtractor construction."""

    def test_construction_with_defaults(self) -> None:
        extractor = DependencyExtractor()

        assert extractor.name == "dependency-extractor"
        assert "dependency" in extractor.system_prompt.lower()
        assert extractor.model == "claude-sonnet-4-5-20250929"

    def test_construction_with_custom_model(self) -> None:
        extractor = DependencyExtractor(model="claude-opus-4-5-20250929")

        assert extractor.model == "claude-opus-4-5-20250929"


class TestDependencyExtractorGenerate:
    """Tests for DependencyExtractor.generate()."""

    @pytest.mark.asyncio
    async def test_empty_section_returns_empty_array(self) -> None:
        extractor = DependencyExtractor()

        result = await extractor.generate({"dependency_section": ""})

        assert result == "[]"

    @pytest.mark.asyncio
    async def test_missing_section_returns_empty_array(self) -> None:
        extractor = DependencyExtractor()

        result = await extractor.generate({})

        assert result == "[]"

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty_array(self) -> None:
        extractor = DependencyExtractor()

        result = await extractor.generate({"dependency_section": "  \n  "})

        assert result == "[]"

    @pytest.mark.asyncio
    async def test_empty_section_with_usage(self) -> None:
        extractor = DependencyExtractor()

        result, usage = await extractor.generate(  # type: ignore[misc]
            {"dependency_section": ""}, return_usage=True
        )

        assert result == "[]"
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    @pytest.mark.asyncio
    async def test_generates_dependency_pairs(self) -> None:
        extractor = DependencyExtractor()

        mock_response = '[["US3","US1"],["US7","US1"],["US7","US3"]]'
        with patch.object(
            extractor,
            "_query",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await extractor.generate(
                {"dependency_section": "US3 depends on US1. US7 needs US1 and US3."}
            )

        assert result == mock_response

    @pytest.mark.asyncio
    async def test_generates_with_usage(self) -> None:
        from maverick.agents.result import AgentUsage

        extractor = DependencyExtractor()

        mock_response = '[["US3","US1"]]'
        mock_usage = AgentUsage(
            input_tokens=100, output_tokens=20, total_cost_usd=None, duration_ms=0
        )

        with patch.object(
            extractor,
            "_query_with_usage",
            new_callable=AsyncMock,
            return_value=(mock_response, mock_usage),
        ):
            result, usage = await extractor.generate(  # type: ignore[misc]
                {"dependency_section": "US3 depends on US1."},
                return_usage=True,
            )

        assert result == mock_response
        assert usage.input_tokens == 100
        assert usage.output_tokens == 20

    @pytest.mark.asyncio
    async def test_query_receives_prompt_with_section(self) -> None:
        extractor = DependencyExtractor()

        section = "US5 requires US2's API."
        with patch.object(
            extractor,
            "_query",
            new_callable=AsyncMock,
            return_value="[]",
        ) as mock_query:
            await extractor.generate({"dependency_section": section})

        # Verify the prompt includes the section text
        call_args = mock_query.call_args[0][0]
        assert section in call_args
