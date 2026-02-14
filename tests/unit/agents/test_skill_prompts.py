"""Unit tests for skill_prompts module.

Tests project conventions loading and render_prompt() convention injection.
"""

from __future__ import annotations

from pathlib import Path

from maverick.agents.skill_prompts import (
    get_project_conventions,
    render_prompt,
)

# =============================================================================
# get_project_conventions Tests
# =============================================================================


class TestGetProjectConventions:
    """Tests for get_project_conventions()."""

    def test_returns_empty_when_no_config(self, tmp_path: Path) -> None:
        """Test returns empty string when maverick.yaml does not exist."""
        config_path = tmp_path / "maverick.yaml"
        result = get_project_conventions(config_path)
        assert result == ""

    def test_returns_empty_when_key_missing(self, tmp_path: Path) -> None:
        """Test returns empty string when project_conventions key is absent."""
        config_path = tmp_path / "maverick.yaml"
        config_path.write_text("project_type: python\n")
        result = get_project_conventions(config_path)
        assert result == ""

    def test_reads_from_yaml(self, tmp_path: Path) -> None:
        """Test reads project_conventions from maverick.yaml."""
        config_path = tmp_path / "maverick.yaml"
        config_path.write_text(
            "project_conventions: |\n"
            "  Use structlog for logging.\n"
            "  Use tenacity for retries.\n"
        )
        result = get_project_conventions(config_path)
        assert "structlog" in result
        assert "tenacity" in result

    def test_returns_empty_for_non_dict_config(self, tmp_path: Path) -> None:
        """Test returns empty string when YAML content is not a dict."""
        config_path = tmp_path / "maverick.yaml"
        config_path.write_text("- item1\n- item2\n")
        result = get_project_conventions(config_path)
        assert result == ""

    def test_returns_empty_for_invalid_yaml(self, tmp_path: Path) -> None:
        """Test returns empty string for invalid YAML content."""
        config_path = tmp_path / "maverick.yaml"
        config_path.write_text(": : invalid yaml {{{\n")
        result = get_project_conventions(config_path)
        assert result == ""


# =============================================================================
# render_prompt with project_conventions Tests
# =============================================================================


class TestRenderPromptWithConventions:
    """Tests for render_prompt() project_conventions substitution."""

    def test_substitutes_project_conventions(self, tmp_path: Path) -> None:
        """Test render_prompt substitutes $project_conventions from config."""
        config_path = tmp_path / "maverick.yaml"
        config_path.write_text(
            "project_type: python\n"
            "project_conventions: |\n"
            "  Use structlog for logging.\n"
        )
        base = "Hello. $project_conventions Goodbye."
        result = render_prompt(base, project_type="python", config_path=config_path)
        assert "structlog" in result
        assert "Project-Specific Conventions" in result

    def test_handles_empty_conventions(self, tmp_path: Path) -> None:
        """Test render_prompt handles empty project_conventions gracefully."""
        config_path = tmp_path / "maverick.yaml"
        config_path.write_text("project_type: python\n")
        base = "Hello. $project_conventions Goodbye."
        result = render_prompt(base, project_type="python", config_path=config_path)
        # $project_conventions should be replaced with empty string
        assert "$project_conventions" not in result
        assert "Hello." in result
        assert "Goodbye." in result

    def test_conventions_not_injected_when_no_config(self, tmp_path: Path) -> None:
        """Test $project_conventions becomes empty when no config exists."""
        config_path = tmp_path / "nonexistent.yaml"
        base = "Start. $project_conventions End."
        result = render_prompt(base, project_type="unknown", config_path=config_path)
        assert "$project_conventions" not in result
        assert "Start." in result
        assert "End." in result

    def test_conventions_coexists_with_skill_guidance(self, tmp_path: Path) -> None:
        """Test both $skill_guidance and $project_conventions are substituted."""
        config_path = tmp_path / "maverick.yaml"
        config_path.write_text(
            "project_type: python\nproject_conventions: |\n  Custom convention here.\n"
        )
        base = "$skill_guidance\n$project_conventions"
        result = render_prompt(base, project_type="python", config_path=config_path)
        assert "$skill_guidance" not in result
        assert "$project_conventions" not in result
        assert "Custom convention here." in result
        # Skill guidance should mention Python
        assert "Python" in result
