"""Unit tests for ``maverick.flight.template.generate_skeleton``."""

from __future__ import annotations

from datetime import date

import yaml

from maverick.flight.template import generate_skeleton

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _get_body(result: str) -> str:
    """Extract the Markdown body after the frontmatter."""
    parts = result.split("---", 2)
    assert len(parts) == 3, "Expected exactly two '---' delimiters"
    return parts[2]


class TestGenerateSkeletonFrontmatter:
    """Tests for YAML frontmatter fields in the generated skeleton."""

    def test_frontmatter_name_field(self) -> None:
        """Frontmatter 'name' field matches the provided name."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        # Extract frontmatter between --- delimiters
        parts = result.split("---")
        assert len(parts) >= 3, "Expected YAML frontmatter delimiters"
        fm = yaml.safe_load(parts[1])
        assert fm["name"] == "my-feature"

    def test_frontmatter_version_is_string_one(self) -> None:
        """Frontmatter 'version' field is the string '1' (not integer)."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        parts = result.split("---")
        fm = yaml.safe_load(parts[1])
        assert fm["version"] == "1"
        assert isinstance(fm["version"], str)

    def test_frontmatter_created_is_iso_date_string(self) -> None:
        """Frontmatter 'created' field is an ISO date string (YYYY-MM-DD)."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        parts = result.split("---")
        fm_text = parts[1]
        # The raw YAML text should have the date as-is (not wrapped in quotes)
        assert "2026-02-28" in fm_text

        # Parsed value should be a date object (PyYAML parses bare YYYY-MM-DD as date)
        fm = yaml.safe_load(fm_text)
        created = fm["created"]
        # Allow either a date object or the string representation
        assert created == date(2026, 2, 28) or str(created) == "2026-02-28"

    def test_frontmatter_tags_is_empty_list(self) -> None:
        """Frontmatter 'tags' field is an empty list."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        parts = result.split("---")
        fm = yaml.safe_load(parts[1])
        assert fm["tags"] == []

    def test_frontmatter_starts_at_beginning(self) -> None:
        """Document starts with the YAML frontmatter delimiter '---'."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        assert result.startswith("---\n")

    def test_different_names_reflected_in_frontmatter(self) -> None:
        """Different name values appear correctly in the frontmatter."""
        result = generate_skeleton("api-gateway-setup", date(2026, 1, 15))

        parts = result.split("---")
        fm = yaml.safe_load(parts[1])
        assert fm["name"] == "api-gateway-setup"

    def test_different_dates_reflected_in_frontmatter(self) -> None:
        """Different date values appear correctly in the frontmatter."""
        result = generate_skeleton("some-plan", date(2025, 12, 1))

        parts = result.split("---")
        fm_text = parts[1]
        assert "2025-12-01" in fm_text


class TestGenerateSkeletonSections:
    """Tests for required Markdown sections in the generated skeleton."""

    def test_objective_section_present(self) -> None:
        """Generated skeleton contains '## Objective' section."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "## Objective" in body

    def test_success_criteria_section_present(self) -> None:
        """Generated skeleton contains '## Success Criteria' section."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "## Success Criteria" in body

    def test_scope_section_present(self) -> None:
        """Generated skeleton contains '## Scope' section."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "## Scope" in body

    def test_scope_in_subsection_present(self) -> None:
        """Generated skeleton contains '### In' subsection under Scope."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "### In" in body

    def test_scope_out_subsection_present(self) -> None:
        """Generated skeleton contains '### Out' subsection under Scope."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "### Out" in body

    def test_scope_boundaries_subsection_present(self) -> None:
        """Generated skeleton contains '### Boundaries' subsection under Scope."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "### Boundaries" in body

    def test_context_section_present(self) -> None:
        """Generated skeleton contains '## Context' section."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "## Context" in body

    def test_constraints_section_present(self) -> None:
        """Generated skeleton contains '## Constraints' section."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "## Constraints" in body

    def test_notes_section_present(self) -> None:
        """Generated skeleton contains '## Notes' section."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "## Notes" in body


class TestGenerateSkeletonHtmlComments:
    """Tests for HTML comment editing instructions in each section."""

    def test_objective_has_html_comment(self) -> None:
        """Objective section contains an HTML comment with editing instructions."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        # Find the Objective section
        assert "## Objective" in body
        assert "<!--" in body
        # Verify there's a comment in the body overall
        assert "-->" in body

    def test_success_criteria_has_html_comment(self) -> None:
        """Success Criteria section contains an HTML comment."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        assert "## Success Criteria" in body
        # Check a comment exists near this section
        assert "<!--" in body

    def test_multiple_html_comments_present(self) -> None:
        """Multiple HTML comments are present (one per section/subsection)."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))
        body = _get_body(result)

        comment_count = body.count("<!--")
        assert comment_count >= 6, (
            f"Expected at least 6 HTML comments, got {comment_count}"
        )


class TestGenerateSkeletonCheckboxItems:
    """Tests for placeholder checkbox items in Success Criteria."""

    def test_success_criteria_has_checkbox_item(self) -> None:
        """Success Criteria section contains a '- [ ]' checkbox placeholder."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        assert "- [ ]" in result

    def test_success_criteria_checkbox_has_comment_placeholder(self) -> None:
        """The checkbox item in Success Criteria has an HTML comment placeholder."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        # The checkbox line should contain an HTML comment for instructions
        lines = result.splitlines()
        checkbox_lines = [line for line in lines if line.strip().startswith("- [ ]")]
        assert len(checkbox_lines) >= 1, "Expected at least one checkbox line"
        # At least one checkbox line should have a comment
        has_comment = any("<!--" in line for line in checkbox_lines)
        assert has_comment, (
            "Expected at least one checkbox line to contain an HTML comment"
        )


class TestGenerateSkeletonReturnType:
    """Tests for return type and basic structure."""

    def test_returns_string(self) -> None:
        """generate_skeleton returns a str."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        assert isinstance(result, str)

    def test_non_empty_result(self) -> None:
        """generate_skeleton returns a non-empty string."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        assert len(result) > 100

    def test_result_ends_with_newline(self) -> None:
        """generate_skeleton result ends with a newline."""
        result = generate_skeleton("my-feature", date(2026, 2, 28))

        assert result.endswith("\n")
