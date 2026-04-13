"""Unit tests for BeadEnricherGenerator."""

from __future__ import annotations

from maverick.agents.generators.bead_enricher import BeadEnricherGenerator


class TestBeadEnricherConstruction:
    """Tests for BeadEnricherGenerator construction."""

    def test_construction_with_defaults(self) -> None:
        enricher = BeadEnricherGenerator()

        assert enricher.name == "bead-enricher"
        assert "enricher" in enricher.system_prompt.lower()
        assert enricher.model == "sonnet"

    def test_construction_with_custom_model(self) -> None:
        enricher = BeadEnricherGenerator(model="claude-opus-4-5-20250929")

        assert enricher.model == "claude-opus-4-5-20250929"


class TestBeadEnricherPromptBuilding:
    """Tests for BeadEnricherGenerator.build_prompt() method."""

    def test_empty_context_produces_minimal_prompt(self) -> None:
        """Empty context produces a prompt with default values (no crash)."""
        enricher = BeadEnricherGenerator()

        prompt = enricher.build_prompt({})

        # Should still produce a prompt without crashing
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_includes_title(self) -> None:
        """Title is included in the prompt."""
        enricher = BeadEnricherGenerator()

        prompt = enricher.build_prompt({"title": "Implement greeting CLI"})

        assert "Implement greeting CLI" in prompt

    def test_prompt_includes_category(self) -> None:
        """Category is included in the prompt."""
        enricher = BeadEnricherGenerator()

        prompt = enricher.build_prompt(
            {
                "title": "Add user auth",
                "category": "USER_STORY",
                "tasks": "- Implement login",
            }
        )

        assert "USER_STORY" in prompt

    def test_prompt_includes_tasks(self) -> None:
        """Task descriptions are included in the prompt."""
        enricher = BeadEnricherGenerator()

        prompt = enricher.build_prompt(
            {
                "title": "Add user auth",
                "tasks": "- Implement login",
            }
        )

        assert "Implement login" in prompt

    def test_prompt_includes_spec_and_plan(self) -> None:
        """Spec and plan content appear in the prompt when provided."""
        enricher = BeadEnricherGenerator()

        prompt = enricher.build_prompt(
            {
                "title": "Test bead",
                "tasks": "- something",
                "spec_content": "The spec content here",
                "plan_content": "The plan content here",
            }
        )

        assert "The spec content here" in prompt
        assert "The plan content here" in prompt

    def test_prompt_includes_checkpoints(self) -> None:
        """Checkpoints are included in the prompt when provided."""
        enricher = BeadEnricherGenerator()

        prompt = enricher.build_prompt(
            {
                "title": "Implement greeting CLI",
                "category": "USER_STORY",
                "tasks": "- Add click command",
                "checkpoints": "- greet command exists",
            }
        )

        assert "greet command exists" in prompt

    def test_prompt_omits_empty_optional_fields(self) -> None:
        """Empty optional fields do not appear as empty sections in the prompt."""
        enricher = BeadEnricherGenerator()

        prompt = enricher.build_prompt(
            {
                "title": "Minimal bead",
            }
        )

        # spec_content and plan_content should not appear since they are empty
        assert "Spec Excerpt" not in prompt
        assert "Plan Excerpt" not in prompt

    def test_prompt_includes_dependency_context(self) -> None:
        """Dependency context appears in the prompt when provided."""
        enricher = BeadEnricherGenerator()

        prompt = enricher.build_prompt(
            {
                "title": "Some bead",
                "dependency_context": "US1 provides the auth module",
            }
        )

        assert "US1 provides the auth module" in prompt
