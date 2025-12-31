"""Unit tests for CommitMessageGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from maverick.agents.generators.base import MAX_DIFF_SIZE
from maverick.agents.generators.commit_message import CommitMessageGenerator
from maverick.exceptions import GeneratorError


class TestCommitMessageGeneratorConstruction:
    """Tests for CommitMessageGenerator construction."""

    def test_construction_with_defaults(self) -> None:
        """Test successful construction with default model."""
        generator = CommitMessageGenerator()

        assert generator.name == "commit-message-generator"
        assert "conventional commit" in generator.system_prompt.lower()
        assert generator.model == "claude-sonnet-4-5-20250929"

    def test_construction_with_custom_model(self) -> None:
        """Test construction with custom model."""
        generator = CommitMessageGenerator(model="claude-opus-4-5-20250929")

        assert generator.model == "claude-opus-4-5-20250929"

    def test_generator_has_no_tools(self) -> None:
        """Test CommitMessageGenerator has no tools per US5 contract.

        US5 Contract: CommitMessageGenerator must have allowed_tools=[].
        Pure text generation, no tools needed.
        """
        generator = CommitMessageGenerator()

        # Generators inherit from GeneratorAgent which sets allowed_tools=[]
        # We need to access the internal _options to verify
        assert hasattr(generator, "_options")
        assert generator._options.allowed_tools == []


class TestCommitMessageGeneratorGenerate:
    """Tests for CommitMessageGenerator.generate()."""

    @pytest.mark.asyncio
    async def test_generate_returns_conventional_commit_format(self) -> None:
        """Test that generate returns conventional commit format."""
        import re

        generator = CommitMessageGenerator()

        # Mock _query to return a conventional commit message
        with patch.object(
            generator,
            "_query",
            new_callable=AsyncMock,
            return_value="feat(auth): add password reset functionality",
        ):
            context = {
                "diff": (
                    "diff --git a/auth.py b/auth.py\n+def reset_password():\n+    pass"
                ),
                "file_stats": {"auth.py": {"additions": 2, "deletions": 0}},
            }

            result = await generator.generate(context)

            # Strict regex validation for conventional commit format
            pattern = (
                r"^(feat|fix|docs|style|refactor|test|build|ci|chore)(\([^)]+\))?:\s+.+"
            )
            assert re.match(pattern, result), (
                f"Invalid conventional commit format: {result}"
            )

    @pytest.mark.asyncio
    async def test_scope_hint_override_works(self) -> None:
        """Test that scope_hint is passed through to the prompt."""
        generator = CommitMessageGenerator()

        # Mock _query
        with patch.object(
            generator,
            "_query",
            new_callable=AsyncMock,
            return_value="feat(database): add user migration",
        ) as mock_query:
            context = {
                "diff": (
                    "diff --git a/migrations/001.sql b/migrations/001.sql\n"
                    "+CREATE TABLE users;"
                ),
                "file_stats": {"migrations/001.sql": {"additions": 1, "deletions": 0}},
                "scope_hint": "database",
            }

            await generator.generate(context)

            # Verify scope_hint was included in the prompt
            assert mock_query.called
            prompt = mock_query.call_args[0][0]
            assert "database" in prompt.lower()

    @pytest.mark.asyncio
    async def test_bug_fix_diff_produces_fix_type(self) -> None:
        """Test that bug fix diffs produce 'fix' type commits."""
        generator = CommitMessageGenerator()

        with patch.object(
            generator,
            "_query",
            new_callable=AsyncMock,
            return_value="fix(auth): handle null user in login",
        ):
            context = {
                "diff": (
                    "diff --git a/auth.py b/auth.py\n-if user:\n+if user is not None:"
                ),
                "file_stats": {"auth.py": {"additions": 1, "deletions": 1}},
            }

            result = await generator.generate(context)

            assert result.startswith("fix")

    @pytest.mark.asyncio
    async def test_empty_diff_raises_generator_error(self) -> None:
        """Test that empty diff raises GeneratorError per FR-015."""
        generator = CommitMessageGenerator()

        context = {
            "diff": "",
            "file_stats": {},
        }

        with pytest.raises(GeneratorError) as exc_info:
            await generator.generate(context)

        assert "diff" in exc_info.value.message.lower()
        assert exc_info.value.generator_name == "commit-message-generator"

    @pytest.mark.asyncio
    async def test_missing_diff_raises_generator_error(self) -> None:
        """Test that missing diff key raises GeneratorError."""
        generator = CommitMessageGenerator()

        context = {
            "file_stats": {},
        }

        with pytest.raises(GeneratorError) as exc_info:
            await generator.generate(context)

        assert "diff" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_diff_truncation_at_100kb_with_warning(self) -> None:
        """Test that large diffs are truncated at 100KB with WARNING per FR-017."""
        generator = CommitMessageGenerator()

        # Create a diff larger than 100KB
        large_diff = (
            "diff --git a/file.py b/file.py\n" + ("+" + "x" * 1000 + "\n") * 200
        )

        assert len(large_diff) > MAX_DIFF_SIZE

        with (
            patch.object(
                generator,
                "_query",
                new_callable=AsyncMock,
                return_value="feat(core): add large feature",
            ),
            patch("maverick.agents.generators.base.logger") as mock_logger,
        ):
            context = {
                "diff": large_diff,
                "file_stats": {"file.py": {"additions": 200, "deletions": 0}},
            }

            await generator.generate(context)

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args
            assert "diff" in str(warning_call).lower()
            assert str(MAX_DIFF_SIZE) in str(warning_call)

    @pytest.mark.asyncio
    async def test_file_stats_included_in_prompt(self) -> None:
        """Test that file_stats are included in the generated prompt."""
        generator = CommitMessageGenerator()

        with patch.object(
            generator,
            "_query",
            new_callable=AsyncMock,
            return_value="feat(api): add endpoints",
        ) as mock_query:
            context = {
                "diff": "diff --git a/api.py b/api.py\n+def endpoint():\n+    pass",
                "file_stats": {
                    "api.py": {"additions": 2, "deletions": 0},
                    "api_test.py": {"additions": 5, "deletions": 0},
                },
            }

            await generator.generate(context)

            # Verify file_stats were included in prompt
            prompt = mock_query.call_args[0][0]
            assert "api.py" in prompt
            assert "api_test.py" in prompt

    @pytest.mark.asyncio
    async def test_optional_scope_hint_not_required(self) -> None:
        """Test that scope_hint is optional and can be omitted."""
        generator = CommitMessageGenerator()

        with patch.object(
            generator,
            "_query",
            new_callable=AsyncMock,
            return_value="feat(core): add feature",
        ):
            context = {
                "diff": "diff --git a/core.py b/core.py\n+def feature():\n+    pass",
                "file_stats": {"core.py": {"additions": 2, "deletions": 0}},
                # No scope_hint
            }

            result = await generator.generate(context)

            assert result.startswith("feat")


class TestCommitMessageGeneratorEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_whitespace_only_diff_raises_error(self) -> None:
        """Test that whitespace-only diff raises GeneratorError."""
        generator = CommitMessageGenerator()

        context = {
            "diff": "   \n  \t\n   ",
            "file_stats": {},
        }

        with pytest.raises(GeneratorError) as exc_info:
            await generator.generate(context)

        assert "diff" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_api_error_wrapped_in_generator_error(self) -> None:
        """Test that API errors are wrapped in GeneratorError."""
        generator = CommitMessageGenerator()

        with patch.object(
            generator,
            "_query",
            side_effect=GeneratorError(
                "API connection failed",
                generator_name="commit-message-generator",
            ),
        ):
            context = {
                "diff": "diff --git a/file.py b/file.py\n+new line",
                "file_stats": {"file.py": {"additions": 1, "deletions": 0}},
            }

            with pytest.raises(GeneratorError) as exc_info:
                await generator.generate(context)

            assert "API connection failed" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_none_file_stats_handled_gracefully(self) -> None:
        """Test that None file_stats doesn't crash."""
        generator = CommitMessageGenerator()

        with patch.object(
            generator,
            "_query",
            new_callable=AsyncMock,
            return_value="feat: add feature",
        ):
            context = {
                "diff": "diff --git a/file.py b/file.py\n+new line",
                "file_stats": None,
            }

            # Should handle gracefully and still generate
            result = await generator.generate(context)

            assert result == "feat: add feature"


class TestCommitMessageGeneratorSystemPrompt:
    """Tests for system prompt validation."""

    def test_system_prompt_mentions_conventional_commits(self) -> None:
        """Test that system prompt enforces conventional commit format."""
        generator = CommitMessageGenerator()

        prompt = generator.system_prompt.lower()

        # Should mention conventional commits or commit format
        assert any(
            term in prompt
            for term in ["conventional commit", "commit format", "type(scope)"]
        )

    def test_system_prompt_lists_commit_types(self) -> None:
        """Test that system prompt lists valid commit types."""
        generator = CommitMessageGenerator()

        prompt = generator.system_prompt.lower()

        # Should mention common types
        common_types = ["feat", "fix", "docs", "refactor", "test"]
        mentioned_count = sum(1 for t in common_types if t in prompt)

        # At least some common types should be mentioned
        assert mentioned_count >= 3

    def test_system_prompt_enforces_format_rules(self) -> None:
        """Test that system prompt enforces formatting rules."""
        generator = CommitMessageGenerator()

        prompt = generator.system_prompt.lower()

        # Should mention format constraints
        format_keywords = ["imperative", "lowercase", "72", "description"]
        mentioned = sum(1 for keyword in format_keywords if keyword in prompt)

        # Should mention at least some format rules
        assert mentioned >= 2
