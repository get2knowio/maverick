"""Unit tests for PRDescriptionGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maverick.agents.generators.base import DEFAULT_MODEL, DEFAULT_PR_SECTIONS
from maverick.agents.generators.pr_description import PRDescriptionGenerator
from maverick.exceptions import GeneratorError


class TestPRDescriptionGeneratorConstruction:
    """Tests for PRDescriptionGenerator construction."""

    def test_construction_with_defaults(self) -> None:
        """Test successful construction with default parameters."""
        generator = PRDescriptionGenerator()

        assert generator.name == "pr-description-generator"
        assert generator.model == DEFAULT_MODEL
        assert "Summary" in generator.system_prompt
        assert "Changes" in generator.system_prompt
        assert "Testing" in generator.system_prompt

    def test_construction_with_custom_sections(self) -> None:
        """Test construction with custom sections list."""
        custom_sections = ("Overview", "Implementation", "Validation", "Notes")
        generator = PRDescriptionGenerator(sections=custom_sections)

        assert "Overview" in generator.system_prompt
        assert "Implementation" in generator.system_prompt
        assert "Validation" in generator.system_prompt
        assert "Notes" in generator.system_prompt

    def test_construction_with_custom_model(self) -> None:
        """Test construction with custom model."""
        generator = PRDescriptionGenerator(model="claude-opus-4-5-20250929")

        assert generator.model == "claude-opus-4-5-20250929"

    def test_default_sections_match_base_constant(self) -> None:
        """Test that default sections match the base class constant."""
        generator = PRDescriptionGenerator()

        # Verify default sections from base are used
        for section in DEFAULT_PR_SECTIONS:
            assert section in generator.system_prompt

    def test_generator_has_no_tools(self) -> None:
        """Test PRDescriptionGenerator has no tools per US5 contract.

        US5 Contract: PRDescriptionGenerator must have allowed_tools=[].
        Pure text generation, no tools needed.
        """
        generator = PRDescriptionGenerator()

        # Generators inherit from GeneratorAgent which sets allowed_tools=[]
        # We need to access the internal _options to verify
        assert hasattr(generator, "_options")
        assert generator._options.allowed_tools == []


class TestPRDescriptionGeneratorGenerate:
    """Tests for the generate method."""

    @pytest.mark.asyncio
    async def test_generate_returns_markdown_with_required_sections(self) -> None:
        """Test generate returns markdown with Summary, Changes, Testing."""
        generator = PRDescriptionGenerator()

        # Mock context
        context = {
            "commits": ["feat: add user authentication", "fix: resolve login bug"],
            "diff_stats": {"files_changed": 5, "insertions": 120, "deletions": 30},
            "task_summary": "Implement user authentication feature",
            "validation_results": {"passed": True, "failures": []},
        }

        # Mock the _query method to return markdown with sections
        expected_output = """## Summary
Implement user authentication feature

## Changes
- Added authentication endpoints
- Fixed login bug

## Testing
All validation checks passed
"""

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = expected_output

            result = await generator.generate(context)

            assert "## Summary" in result
            assert "## Changes" in result
            assert "## Testing" in result
            mock_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_reflects_failing_validation_in_testing_section(
        self,
    ) -> None:
        """Test that failing validation results are reflected in Testing section."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "diff_stats": {"files_changed": 1, "insertions": 10, "deletions": 0},
            "task_summary": "Add new feature",
            "validation_results": {
                "passed": False,
                "failures": ["test_auth.py::test_login FAILED"],
            },
        }

        expected_output = """## Summary
Add new feature

## Changes
- Added feature implementation

## Testing
Validation failures detected:
- test_auth.py::test_login FAILED
"""

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = expected_output

            result = await generator.generate(context)

            # Verify the prompt includes validation failures
            call_args = mock_query.call_args[0][0]
            assert "failures" in call_args or "FAILED" in call_args

            assert "## Testing" in result

    @pytest.mark.asyncio
    async def test_generate_incorporates_task_summary_in_summary_section(self) -> None:
        """Test that task_summary is incorporated in Summary section."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: implement password reset"],
            "diff_stats": {"files_changed": 3, "insertions": 80, "deletions": 10},
            "task_summary": "Add password reset functionality with email verification",
            "validation_results": {"passed": True, "failures": []},
        }

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = "## Summary\n..."

            await generator.generate(context)

            # Verify the prompt includes the task summary
            call_args = mock_query.call_args[0][0]
            assert "password reset functionality" in call_args

    @pytest.mark.asyncio
    async def test_generate_with_custom_sections_list(self) -> None:
        """Test that custom sections list works correctly."""
        custom_sections = ("Overview", "Implementation", "Testing", "Notes")
        generator = PRDescriptionGenerator(sections=custom_sections)

        context = {
            "commits": ["feat: add feature"],
            "diff_stats": {"files_changed": 2, "insertions": 50, "deletions": 5},
            "task_summary": "Add new feature",
            "validation_results": {"passed": True, "failures": []},
        }

        expected_output = """## Overview
Feature overview

## Implementation
Implementation details

## Testing
All tests pass

## Notes
Additional notes
"""

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = expected_output

            result = await generator.generate(context)

            assert "## Overview" in result
            assert "## Implementation" in result
            assert "## Notes" in result

    @pytest.mark.asyncio
    async def test_empty_commits_raises_generator_error(self) -> None:
        """Test that empty commits list raises GeneratorError (per FR-015)."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": [],
            "diff_stats": {"files_changed": 0, "insertions": 0, "deletions": 0},
            "task_summary": "Some task",
            "validation_results": {"passed": True, "failures": []},
        }

        with pytest.raises(GeneratorError) as exc_info:
            await generator.generate(context)

        assert "commits" in exc_info.value.message.lower()
        assert exc_info.value.generator_name == "pr-description-generator"

    @pytest.mark.asyncio
    async def test_empty_task_summary_raises_generator_error(self) -> None:
        """Test that empty task_summary raises GeneratorError (per FR-015)."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "diff_stats": {"files_changed": 1, "insertions": 10, "deletions": 0},
            "task_summary": "",
            "validation_results": {"passed": True, "failures": []},
        }

        with pytest.raises(GeneratorError) as exc_info:
            await generator.generate(context)

        assert "task_summary" in exc_info.value.message.lower()
        assert exc_info.value.generator_name == "pr-description-generator"

    @pytest.mark.asyncio
    async def test_missing_commits_raises_generator_error(self) -> None:
        """Test that missing commits key raises GeneratorError."""
        generator = PRDescriptionGenerator()

        context = {
            "diff_stats": {"files_changed": 1, "insertions": 10, "deletions": 0},
            "task_summary": "Some task",
            "validation_results": {"passed": True, "failures": []},
        }

        with pytest.raises(GeneratorError) as exc_info:
            await generator.generate(context)

        assert "commits" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_missing_task_summary_raises_generator_error(self) -> None:
        """Test that missing task_summary key raises GeneratorError."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "diff_stats": {"files_changed": 1, "insertions": 10, "deletions": 0},
            "validation_results": {"passed": True, "failures": []},
        }

        with pytest.raises(GeneratorError) as exc_info:
            await generator.generate(context)

        assert "task_summary" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_generate_with_optional_diff_stats(self) -> None:
        """Test that diff_stats is optional (can be None or missing)."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "task_summary": "Add new feature",
            "validation_results": {"passed": True, "failures": []},
        }

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = "## Summary\n..."

            result = await generator.generate(context)

            assert result is not None
            mock_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_with_optional_validation_results(self) -> None:
        """Test that validation_results is optional (can be None or missing)."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "diff_stats": {"files_changed": 1, "insertions": 10, "deletions": 0},
            "task_summary": "Add new feature",
        }

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = "## Summary\n..."

            result = await generator.generate(context)

            assert result is not None
            mock_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_error_raises_generator_error(self) -> None:
        """Test that API errors are wrapped in GeneratorError."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "diff_stats": {"files_changed": 1, "insertions": 10, "deletions": 0},
            "task_summary": "Add new feature",
            "validation_results": {"passed": True, "failures": []},
        }

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.side_effect = GeneratorError(
                "API error",
                generator_name="pr-description-generator",
            )

            with pytest.raises(GeneratorError) as exc_info:
                await generator.generate(context)

            assert "API error" in exc_info.value.message


class TestPRDescriptionGeneratorSystemPrompt:
    """Tests for system prompt construction."""

    def test_system_prompt_enforces_markdown_format(self) -> None:
        """Test that system prompt enforces markdown section format."""
        generator = PRDescriptionGenerator()

        assert "markdown" in generator.system_prompt.lower()
        assert "##" in generator.system_prompt

    def test_system_prompt_includes_default_sections(self) -> None:
        """Test that system prompt includes Summary, Changes, Testing sections."""
        generator = PRDescriptionGenerator()

        assert "Summary" in generator.system_prompt
        assert "Changes" in generator.system_prompt
        assert "Testing" in generator.system_prompt

    def test_system_prompt_with_custom_sections(self) -> None:
        """Test that system prompt reflects custom sections."""
        custom_sections = ("Context", "Details", "Verification", "Notes")
        generator = PRDescriptionGenerator(sections=custom_sections)

        assert "Context" in generator.system_prompt
        assert "Details" in generator.system_prompt
        assert "Verification" in generator.system_prompt
        assert "Notes" in generator.system_prompt


class TestPRDescriptionGeneratorPromptBuilding:
    """Tests for prompt construction from context."""

    @pytest.mark.asyncio
    async def test_prompt_includes_all_context_fields(self) -> None:
        """Test that generated prompt includes all provided context."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add auth", "fix: login bug"],
            "diff_stats": {"files_changed": 5, "insertions": 120, "deletions": 30},
            "task_summary": "Implement authentication",
            "validation_results": {"passed": False, "failures": ["test failure"]},
        }

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = "## Summary\n..."

            await generator.generate(context)

            call_args = mock_query.call_args[0][0]

            # Verify all context elements are in prompt
            assert "feat: add auth" in call_args
            assert "fix: login bug" in call_args
            assert "files_changed" in call_args or "5" in call_args
            assert "Implement authentication" in call_args

    @pytest.mark.asyncio
    async def test_prompt_with_minimal_context(self) -> None:
        """Test prompt building with only required fields."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: minimal change"],
            "task_summary": "Minimal task",
        }

        with patch.object(generator, "_query", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = "## Summary\n..."

            await generator.generate(context)

            call_args = mock_query.call_args[0][0]

            assert "feat: minimal change" in call_args
            assert "Minimal task" in call_args
