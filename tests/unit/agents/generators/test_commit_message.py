"""Unit tests for CommitMessageGenerator."""

from __future__ import annotations

from unittest.mock import patch

from maverick.agents.generators.base import MAX_DIFF_SIZE
from maverick.agents.generators.commit_message import CommitMessageGenerator


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
        """Test CommitMessageGenerator has empty allowed_tools per US5 contract.

        US5 Contract: CommitMessageGenerator must have allowed_tools=[].
        Pure text generation, no tools needed.
        """
        generator = CommitMessageGenerator()

        assert generator.allowed_tools == []


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


class TestCommitMessageGeneratorPromptBuilding:
    """Tests for prompt construction from context."""

    def test_prompt_includes_diff(self) -> None:
        """Test that the diff is included in the prompt."""
        generator = CommitMessageGenerator()

        diff = "diff --git a/auth.py b/auth.py\n+def reset_password():\n+    pass"
        context = {
            "diff": diff,
            "file_stats": {"auth.py": {"additions": 2, "deletions": 0}},
        }

        prompt = generator.build_prompt(context)

        assert "reset_password" in prompt

    def test_prompt_includes_scope_hint(self) -> None:
        """Test that scope_hint is included in the prompt when provided."""
        generator = CommitMessageGenerator()

        context = {
            "diff": (
                "diff --git a/migrations/001.sql b/migrations/001.sql"
                "\n+CREATE TABLE users;"
            ),
            "file_stats": {"migrations/001.sql": {"additions": 1, "deletions": 0}},
            "scope_hint": "database",
        }

        prompt = generator.build_prompt(context)

        assert "database" in prompt.lower()

    def test_prompt_includes_file_stats(self) -> None:
        """Test that file_stats are included in the generated prompt."""
        generator = CommitMessageGenerator()

        context = {
            "diff": "diff --git a/api.py b/api.py\n+def endpoint():\n+    pass",
            "file_stats": {
                "api.py": {"additions": 2, "deletions": 0},
                "api_test.py": {"additions": 5, "deletions": 0},
            },
        }

        prompt = generator.build_prompt(context)

        assert "api.py" in prompt
        assert "api_test.py" in prompt

    def test_prompt_without_scope_hint(self) -> None:
        """Test prompt building without optional scope_hint."""
        generator = CommitMessageGenerator()

        context = {
            "diff": "diff --git a/core.py b/core.py\n+def feature():\n+    pass",
            "file_stats": {"core.py": {"additions": 2, "deletions": 0}},
        }

        # Should not raise
        prompt = generator.build_prompt(context)

        assert "core.py" in prompt

    def test_diff_truncation_at_100kb_with_warning(self) -> None:
        """Test that large diffs are truncated at 100KB with WARNING per FR-017."""
        generator = CommitMessageGenerator()

        # Create a diff larger than 100KB
        large_diff = (
            "diff --git a/file.py b/file.py\n" + ("+" + "x" * 1000 + "\n") * 200
        )

        assert len(large_diff) > MAX_DIFF_SIZE

        with patch("maverick.agents.generators.base.logger") as mock_logger:
            context = {
                "diff": large_diff,
                "file_stats": {"file.py": {"additions": 200, "deletions": 0}},
            }

            prompt = generator.build_prompt(context)

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args
            assert "diff" in str(warning_call).lower()
            assert str(MAX_DIFF_SIZE) in str(warning_call)

        # The prompt should be built (truncated)
        assert len(prompt) > 0

    def test_prompt_with_empty_diff_still_builds(self) -> None:
        """Test that build_prompt works even with empty diff (caller validates)."""
        generator = CommitMessageGenerator()

        context = {
            "diff": "",
            "file_stats": {},
        }

        # build_prompt should not raise; validation is the executor's responsibility
        prompt = generator.build_prompt(context)
        assert isinstance(prompt, str)

    def test_prompt_with_none_file_stats(self) -> None:
        """Test that None file_stats doesn't crash build_prompt."""
        generator = CommitMessageGenerator()

        context = {
            "diff": "diff --git a/file.py b/file.py\n+new line",
            "file_stats": None,
        }

        # Should handle gracefully
        prompt = generator.build_prompt(context)
        assert isinstance(prompt, str)
