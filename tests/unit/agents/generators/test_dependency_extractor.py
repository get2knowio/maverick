"""Unit tests for DependencyExtractor generator."""

from __future__ import annotations

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


class TestDependencyExtractorPromptBuilding:
    """Tests for DependencyExtractor.build_prompt() method."""

    def test_empty_section_produces_prompt(self) -> None:
        """Empty dependency_section still produces a prompt without crashing."""
        extractor = DependencyExtractor()

        prompt = extractor.build_prompt({"dependency_section": ""})

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_missing_section_produces_prompt(self) -> None:
        """Missing dependency_section key still produces a prompt."""
        extractor = DependencyExtractor()

        prompt = extractor.build_prompt({})

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_includes_dependency_section(self) -> None:
        """The dependency section text is included in the prompt."""
        extractor = DependencyExtractor()

        section = "US5 requires US2's API."
        prompt = extractor.build_prompt({"dependency_section": section})

        assert section in prompt

    def test_prompt_includes_multi_dependency_text(self) -> None:
        """Complex dependency text is included verbatim in the prompt."""
        extractor = DependencyExtractor()

        section = "US3 depends on US1 for the data model. US7 needs US1 and US3."
        prompt = extractor.build_prompt({"dependency_section": section})

        assert "US3" in prompt
        assert "US1" in prompt
        assert "US7" in prompt

    def test_prompt_instructs_json_output(self) -> None:
        """The prompt instructs the model to output JSON pairs."""
        extractor = DependencyExtractor()

        prompt = extractor.build_prompt({"dependency_section": "US1 needs US2."})

        # The prompt should mention JSON or pair format
        assert "JSON" in prompt or "json" in prompt.lower()

    def test_whitespace_only_section_produces_prompt(self) -> None:
        """Whitespace-only dependency section does not crash build_prompt."""
        extractor = DependencyExtractor()

        prompt = extractor.build_prompt({"dependency_section": "  \n  "})

        assert isinstance(prompt, str)
