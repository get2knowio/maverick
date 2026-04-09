"""Tests for maverick.flight.parser module.

T005: Write tests for core parser functions.
Tests must FAIL before T006 implementation.
"""

from __future__ import annotations

import pytest

from maverick.flight.errors import FlightPlanParseError

# ---------------------------------------------------------------------------
# T005: parse_frontmatter tests
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    """Tests for parse_frontmatter()."""

    def test_valid_frontmatter_returns_dict_and_body(self) -> None:
        """Valid frontmatter is parsed into a dict, body is the rest."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\nname: my-plan\nversion: '1.0'\n---\n\n## Objective\n\nHello.\n"
        fm, body = parse_frontmatter(content)
        assert fm == {"name": "my-plan", "version": "1.0"}
        assert "## Objective" in body

    def test_frontmatter_with_list_fields(self) -> None:
        """Frontmatter with list-valued fields is parsed correctly."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\ntags:\n  - auth\n  - security\n---\n\nBody here.\n"
        fm, body = parse_frontmatter(content)
        assert fm["tags"] == ["auth", "security"]
        assert "Body here." in body

    def test_missing_opening_delimiter_raises(self) -> None:
        """Content without opening --- raises FlightPlanParseError."""
        from maverick.flight.parser import parse_frontmatter

        content = "name: my-plan\nversion: '1.0'\n---\n\n## Objective\n"
        with pytest.raises(FlightPlanParseError):
            parse_frontmatter(content)

    def test_missing_closing_delimiter_raises(self) -> None:
        """Content with opening --- but no closing --- raises FlightPlanParseError."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\nname: my-plan\nversion: '1.0'\n\n## Objective\n"
        with pytest.raises(FlightPlanParseError):
            parse_frontmatter(content)

    def test_empty_content_raises(self) -> None:
        """Empty content (no delimiters) raises FlightPlanParseError."""
        from maverick.flight.parser import parse_frontmatter

        with pytest.raises(FlightPlanParseError):
            parse_frontmatter("")

    def test_invalid_yaml_raises(self) -> None:
        """Invalid YAML inside frontmatter block raises FlightPlanParseError."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\nname: [unclosed bracket\n---\n\n## Body\n"
        with pytest.raises(FlightPlanParseError):
            parse_frontmatter(content)

    def test_body_content_with_yaml_like_syntax(self) -> None:
        """Body can contain YAML-like text without interfering with frontmatter."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\nname: my-plan\n---\n\n## Section\n\nkey: value\nlist:\n  - item\n"
        fm, body = parse_frontmatter(content)
        assert fm == {"name": "my-plan"}
        assert "key: value" in body

    def test_empty_frontmatter_block_returns_empty_dict(self) -> None:
        """Empty frontmatter block returns empty dict."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\n---\n\nBody content here.\n"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert "Body content here." in body

    def test_body_stripped_of_leading_whitespace(self) -> None:
        """The body is returned with leading blank lines stripped."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\nname: x\n---\n\n\n## Objective\n"
        _, body = parse_frontmatter(content)
        # Body should not be empty
        assert "## Objective" in body

    def test_yaml_value_containing_triple_dash_not_treated_as_delimiter(self) -> None:
        """YAML value with '---' is not the closing delimiter."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\nname: my-plan\nseparator: '---'\n---\n\n## Objective\n\nHello.\n"
        fm, body = parse_frontmatter(content)
        assert fm["name"] == "my-plan"
        assert fm["separator"] == "---"
        assert "## Objective" in body

    def test_returns_tuple(self) -> None:
        """Return type is a two-element tuple."""
        from maverick.flight.parser import parse_frontmatter

        content = "---\nname: test\n---\n\nBody.\n"
        result = parse_frontmatter(content)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# T005: parse_checkbox_list tests
# ---------------------------------------------------------------------------


class TestParseCheckboxList:
    """Tests for parse_checkbox_list()."""

    def test_lowercase_x_is_checked(self) -> None:
        """[x] items are parsed as checked=True."""
        from maverick.flight.parser import parse_checkbox_list

        content = "- [x] First item\n"
        result = parse_checkbox_list(content)
        assert result == [(True, "First item")]

    def test_uppercase_x_is_checked(self) -> None:
        """[X] items are parsed as checked=True."""
        from maverick.flight.parser import parse_checkbox_list

        content = "- [X] Second item\n"
        result = parse_checkbox_list(content)
        assert result == [(True, "Second item")]

    def test_space_is_unchecked(self) -> None:
        """[ ] items are parsed as checked=False."""
        from maverick.flight.parser import parse_checkbox_list

        content = "- [ ] Third item\n"
        result = parse_checkbox_list(content)
        assert result == [(False, "Third item")]

    def test_mixed_checked_and_unchecked(self) -> None:
        """Mixed checked/unchecked items are all parsed correctly."""
        from maverick.flight.parser import parse_checkbox_list

        content = (
            "- [x] Users can register with email and password\n"
            "- [ ] Users can log in and receive a JWT\n"
            "- [ ] Protected routes reject unauthenticated requests\n"
        )
        result = parse_checkbox_list(content)
        assert result == [
            (True, "Users can register with email and password"),
            (False, "Users can log in and receive a JWT"),
            (False, "Protected routes reject unauthenticated requests"),
        ]

    def test_empty_content_returns_empty_list(self) -> None:
        """Empty string returns empty list."""
        from maverick.flight.parser import parse_checkbox_list

        result = parse_checkbox_list("")
        assert result == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        """Whitespace-only string returns empty list."""
        from maverick.flight.parser import parse_checkbox_list

        result = parse_checkbox_list("   \n  \n")
        assert result == []

    def test_content_with_yaml_like_lines_ignored(self) -> None:
        """Non-checkbox lines (e.g. YAML-like) are ignored."""
        from maverick.flight.parser import parse_checkbox_list

        content = "key: value\n- [x] Real item\nname: foo\n"
        result = parse_checkbox_list(content)
        assert result == [(True, "Real item")]

    def test_text_is_stripped(self) -> None:
        """Item text is stripped of surrounding whitespace."""
        from maverick.flight.parser import parse_checkbox_list

        content = "- [x]   Item with extra spaces   \n"
        result = parse_checkbox_list(content)
        assert result == [(True, "Item with extra spaces")]

    def test_returns_list_of_tuples(self) -> None:
        """Return type is list of (bool, str) tuples."""
        from maverick.flight.parser import parse_checkbox_list

        content = "- [x] Item\n"
        result = parse_checkbox_list(content)
        assert isinstance(result, list)
        assert isinstance(result[0], tuple)
        checked, text = result[0]
        assert isinstance(checked, bool)
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# T005: parse_bullet_list tests
# ---------------------------------------------------------------------------


class TestParseBulletList:
    """Tests for parse_bullet_list()."""

    def test_single_bullet(self) -> None:
        """Single bullet line is parsed into a list with one element."""
        from maverick.flight.parser import parse_bullet_list

        content = "- Registration endpoint\n"
        result = parse_bullet_list(content)
        assert result == ["Registration endpoint"]

    def test_multiple_bullets(self) -> None:
        """Multiple bullet lines are all parsed."""
        from maverick.flight.parser import parse_bullet_list

        content = "- Registration endpoint\n- Login endpoint\n- JWT middleware\n"
        result = parse_bullet_list(content)
        assert result == ["Registration endpoint", "Login endpoint", "JWT middleware"]

    def test_empty_content_returns_empty_list(self) -> None:
        """Empty content returns empty list."""
        from maverick.flight.parser import parse_bullet_list

        result = parse_bullet_list("")
        assert result == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        """Whitespace-only content returns empty list."""
        from maverick.flight.parser import parse_bullet_list

        result = parse_bullet_list("  \n  \n")
        assert result == []

    def test_text_is_stripped(self) -> None:
        """Bullet text is stripped of surrounding whitespace."""
        from maverick.flight.parser import parse_bullet_list

        content = "-   Extra spaces around text   \n"
        result = parse_bullet_list(content)
        assert result == ["Extra spaces around text"]

    def test_non_bullet_lines_ignored(self) -> None:
        """Non-bullet lines are ignored."""
        from maverick.flight.parser import parse_bullet_list

        content = "Some plain text\n- Bullet item\nAnother plain line\n"
        result = parse_bullet_list(content)
        assert result == ["Bullet item"]

    def test_returns_list_of_strings(self) -> None:
        """Return type is list of strings."""
        from maverick.flight.parser import parse_bullet_list

        content = "- item\n"
        result = parse_bullet_list(content)
        assert isinstance(result, list)
        assert all(isinstance(x, str) for x in result)


# ---------------------------------------------------------------------------
# T005: parse_flight_plan_sections tests (integration with sample data)
# ---------------------------------------------------------------------------


class TestParseFlightPlanSections:
    """Tests for parse_flight_plan_sections()."""

    def test_objective_extracted(self, sample_flight_plan_md: str) -> None:
        """## Objective section is extracted as plain text."""
        from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter

        _, body = parse_frontmatter(sample_flight_plan_md)
        sections = parse_flight_plan_sections(body)
        assert "JWT tokens" in sections["objective"]

    def test_success_criteria_extracted(self, sample_flight_plan_md: str) -> None:
        """## Success Criteria is a list of (checked, text) tuples."""
        from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter

        _, body = parse_frontmatter(sample_flight_plan_md)
        sections = parse_flight_plan_sections(body)
        criteria = sections["success_criteria"]
        assert len(criteria) == 3
        assert criteria[0][0] is True  # [x]
        assert criteria[1][0] is False  # [ ]
        assert criteria[2][0] is False  # [ ]

    def test_scope_in_scope_extracted(self, sample_flight_plan_md: str) -> None:
        """## Scope ### In subsection is extracted."""
        from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter

        _, body = parse_frontmatter(sample_flight_plan_md)
        sections = parse_flight_plan_sections(body)
        assert "Registration endpoint" in sections["scope"]["in_scope"]

    def test_scope_out_of_scope_extracted(self, sample_flight_plan_md: str) -> None:
        """## Scope ### Out subsection is extracted."""
        from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter

        _, body = parse_frontmatter(sample_flight_plan_md)
        sections = parse_flight_plan_sections(body)
        assert "OAuth providers" in sections["scope"]["out_of_scope"]

    def test_scope_boundaries_extracted(self, sample_flight_plan_md: str) -> None:
        """## Scope ### Boundaries subsection is extracted."""
        from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter

        _, body = parse_frontmatter(sample_flight_plan_md)
        sections = parse_flight_plan_sections(body)
        assert len(sections["scope"]["boundaries"]) >= 1

    def test_context_extracted(self, sample_flight_plan_md: str) -> None:
        """## Context section is extracted as plain text."""
        from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter

        _, body = parse_frontmatter(sample_flight_plan_md)
        sections = parse_flight_plan_sections(body)
        assert "Express.js" in sections["context"]

    def test_constraints_extracted(self, sample_flight_plan_md: str) -> None:
        """## Constraints section is extracted as bullet list."""
        from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter

        _, body = parse_frontmatter(sample_flight_plan_md)
        sections = parse_flight_plan_sections(body)
        assert len(sections["constraints"]) == 2

    def test_notes_extracted(self, sample_flight_plan_md: str) -> None:
        """## Notes section is extracted as plain text."""
        from maverick.flight.parser import parse_flight_plan_sections, parse_frontmatter

        _, body = parse_frontmatter(sample_flight_plan_md)
        sections = parse_flight_plan_sections(body)
        assert "refresh tokens" in sections["notes"]

    def test_missing_optional_sections_default(self) -> None:
        """Missing optional sections (context, constraints, notes) are empty."""
        from maverick.flight.parser import parse_flight_plan_sections

        body = (
            "## Objective\n\nDo something.\n\n"
            "## Success Criteria\n\n- [x] Done\n\n"
            "## Scope\n\n### In\n\n- item\n\n### Out\n\n### Boundaries\n\n"
        )
        sections = parse_flight_plan_sections(body)
        assert sections["context"] == ""
        assert sections["constraints"] == []
        assert sections["notes"] == ""


# ---------------------------------------------------------------------------
# T005: parse_work_unit_sections tests (integration with sample data)
# ---------------------------------------------------------------------------


class TestParseWorkUnitSections:
    """Tests for parse_work_unit_sections()."""

    def test_task_extracted(self, sample_work_unit_md: str) -> None:
        """## Task section is extracted as plain text."""
        from maverick.flight.parser import parse_frontmatter, parse_work_unit_sections

        _, body = parse_frontmatter(sample_work_unit_md)
        sections = parse_work_unit_sections(body)
        assert "users table" in sections["task"]

    def test_acceptance_criteria_with_trace_ref(self, sample_work_unit_md: str) -> None:
        """Acceptance criteria with [SC-###] trace refs are parsed."""
        from maverick.flight.parser import parse_frontmatter, parse_work_unit_sections

        _, body = parse_frontmatter(sample_work_unit_md)
        sections = parse_work_unit_sections(body)
        criteria = sections["acceptance_criteria"]
        # First criterion has SC-001 trace ref
        assert any(ref == "SC-001" for _, ref in criteria)
        # Second criterion has no trace ref
        assert any(ref is None for _, ref in criteria)

    def test_file_scope_create_extracted(self, sample_work_unit_md: str) -> None:
        """## File Scope ### Create subsection is extracted."""
        from maverick.flight.parser import parse_frontmatter, parse_work_unit_sections

        _, body = parse_frontmatter(sample_work_unit_md)
        sections = parse_work_unit_sections(body)
        assert "src/db/connection.py" in sections["file_scope"]["create"]

    def test_file_scope_modify_extracted(self, sample_work_unit_md: str) -> None:
        """## File Scope ### Modify subsection is extracted."""
        from maverick.flight.parser import parse_frontmatter, parse_work_unit_sections

        _, body = parse_frontmatter(sample_work_unit_md)
        sections = parse_work_unit_sections(body)
        assert "src/config.py" in sections["file_scope"]["modify"]

    def test_file_scope_protect_extracted(self, sample_work_unit_md: str) -> None:
        """## File Scope ### Protect subsection is extracted."""
        from maverick.flight.parser import parse_frontmatter, parse_work_unit_sections

        _, body = parse_frontmatter(sample_work_unit_md)
        sections = parse_work_unit_sections(body)
        assert "src/main.py" in sections["file_scope"]["protect"]

    def test_instructions_extracted(self, sample_work_unit_md: str) -> None:
        """## Instructions section is extracted as plain text."""
        from maverick.flight.parser import parse_frontmatter, parse_work_unit_sections

        _, body = parse_frontmatter(sample_work_unit_md)
        sections = parse_work_unit_sections(body)
        assert "SQLAlchemy" in sections["instructions"]

    def test_verification_extracted(self, sample_work_unit_md: str) -> None:
        """## Verification section is extracted as list of command strings."""
        from maverick.flight.parser import parse_frontmatter, parse_work_unit_sections

        _, body = parse_frontmatter(sample_work_unit_md)
        sections = parse_work_unit_sections(body)
        assert "make test-fast" in sections["verification"]

    def test_provider_hints_missing_is_none(self, sample_work_unit_md: str) -> None:
        """Missing ## Provider Hints section returns None."""
        from maverick.flight.parser import parse_frontmatter, parse_work_unit_sections

        _, body = parse_frontmatter(sample_work_unit_md)
        sections = parse_work_unit_sections(body)
        assert sections["provider_hints"] is None
