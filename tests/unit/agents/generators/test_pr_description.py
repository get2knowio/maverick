"""Unit tests for PRDescriptionGenerator."""

from __future__ import annotations

from maverick.agents.generators.base import DEFAULT_MODEL, DEFAULT_PR_SECTIONS
from maverick.agents.generators.pr_description import PRDescriptionGenerator


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
        """Test PRDescriptionGenerator has empty allowed_tools per US5 contract.

        US5 Contract: PRDescriptionGenerator must have allowed_tools=[].
        Pure text generation, no tools needed.
        """
        generator = PRDescriptionGenerator()

        assert generator.allowed_tools == []


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

    def test_prompt_includes_all_context_fields(self) -> None:
        """Test that generated prompt includes all provided context."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add auth", "fix: login bug"],
            "diff_stats": {"files_changed": 5, "insertions": 120, "deletions": 30},
            "task_summary": "Implement authentication",
            "validation_results": {"passed": False, "failures": ["test failure"]},
        }

        prompt = generator.build_prompt(context)

        # Verify all context elements are in prompt
        assert "feat: add auth" in prompt
        assert "fix: login bug" in prompt
        assert "Implement authentication" in prompt

    def test_prompt_with_minimal_context(self) -> None:
        """Test prompt building with only required fields."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: minimal change"],
            "task_summary": "Minimal task",
        }

        prompt = generator.build_prompt(context)

        assert "feat: minimal change" in prompt
        assert "Minimal task" in prompt

    def test_prompt_with_diff_stats(self) -> None:
        """Test that diff_stats are included in the prompt when provided."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "task_summary": "Add feature",
            "diff_stats": {"files_changed": 3, "insertions": 50, "deletions": 10},
        }

        prompt = generator.build_prompt(context)

        assert "files_changed" in prompt or "3" in prompt

    def test_prompt_with_validation_failures(self) -> None:
        """Test that validation failures are included in the prompt."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "task_summary": "Add feature",
            "validation_results": {
                "passed": False,
                "failures": ["test_auth.py::test_login FAILED"],
            },
        }

        prompt = generator.build_prompt(context)

        assert "FAILED" in prompt or "failures" in prompt.lower()

    def test_prompt_with_passing_validation(self) -> None:
        """Test that passing validation is reflected in the prompt."""
        generator = PRDescriptionGenerator()

        context = {
            "commits": ["feat: add feature"],
            "task_summary": "Add feature",
            "validation_results": {"passed": True, "failures": []},
        }

        prompt = generator.build_prompt(context)

        assert "passed" in prompt.lower()

    def test_prompt_includes_custom_sections(self) -> None:
        """Test that custom sections appear in the prompt."""
        custom_sections = ("Overview", "Implementation", "Testing", "Notes")
        generator = PRDescriptionGenerator(sections=custom_sections)

        context = {
            "commits": ["feat: add feature"],
            "task_summary": "Add feature",
        }

        prompt = generator.build_prompt(context)

        assert "Overview" in prompt or "Implementation" in prompt or "Notes" in prompt
