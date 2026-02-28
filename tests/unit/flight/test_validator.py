"""Tests for maverick.flight.validator module.

T008: Write tests for validate_flight_plan_file() (TDD - written before implementation).
Tests must FAIL before T010 implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from maverick.flight.validator import ValidationIssue, validate_flight_plan_file

from .conftest import VALID_FLIGHT_PLAN_CONTENT

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestValidateFlightPlanFileValid:
    """Valid files produce no issues."""

    def test_valid_file_returns_empty_list(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """A fully valid flight plan returns an empty issue list."""
        path = write_flight_plan(VALID_FLIGHT_PLAN_CONTENT)
        issues = validate_flight_plan_file(path)
        assert issues == []


# ---------------------------------------------------------------------------
# Frontmatter blocking rules (V1-V3)
# ---------------------------------------------------------------------------


class TestFrontmatterBlockingRules:
    """V1-V3 are blocking -- section checks are skipped when frontmatter fails."""

    def test_empty_file_triggers_v1(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Empty file (0 bytes) triggers V1 -- missing opening delimiter."""
        path = write_flight_plan("")
        issues = validate_flight_plan_file(path)
        assert len(issues) == 1
        locations = [i.location for i in issues]
        assert any("frontmatter" in loc.lower() or "V1" in loc for loc in locations)

    def test_missing_opening_delimiter_triggers_v1(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Document not starting with --- triggers V1."""
        content = "name: my-plan\nversion: '1.0'\n---\n\n## Objective\n\nHello.\n"
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        locations = [i.location for i in issues]
        assert any("frontmatter" in loc.lower() or "V1" in loc for loc in locations)

    def test_missing_closing_delimiter_triggers_v2(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Document with opening --- but no closing --- triggers V2."""
        content = "---\nname: my-plan\nversion: '1.0'\n\n## Objective\n\nText.\n"
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        locations = [i.location for i in issues]
        assert any("frontmatter" in loc.lower() or "V2" in loc for loc in locations)

    def test_malformed_yaml_triggers_v3(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Invalid YAML in frontmatter triggers V3."""
        content = "---\nname: [unclosed bracket\n---\n\n## Objective\n\nText.\n"
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        locations = [i.location for i in issues]
        assert any("frontmatter" in loc.lower() or "V3" in loc for loc in locations)

    def test_v1_is_blocking_section_checks_skipped(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """When V1 fails, section rules are not checked (early return)."""
        # No frontmatter at all -- sections also "missing" but that should not add V7-V9
        content = "Just some plain text without any frontmatter or sections."
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        # Only frontmatter issues expected; V7/V8/V9 messages must not appear
        messages = " ".join(i.message.lower() for i in issues)
        assert "objective" not in messages
        assert "success criteria" not in messages
        assert "scope" not in messages


# ---------------------------------------------------------------------------
# Frontmatter field rules (V4-V6)
# ---------------------------------------------------------------------------


class TestFrontmatterFieldRules:
    """V4, V5, V6 check required frontmatter fields."""

    def _content_without(self, field: str) -> str:
        """Return valid content with *field* removed from frontmatter."""
        lines = VALID_FLIGHT_PLAN_CONTENT.splitlines(keepends=True)
        return "".join(line for line in lines if not line.startswith(f"{field}:"))

    def test_missing_name_triggers_v4(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Frontmatter without 'name' field triggers V4."""
        path = write_flight_plan(self._content_without("name"))
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        locations = [i.location for i in issues]
        assert any("name" in loc.lower() or "V4" in loc for loc in locations)

    def test_empty_name_triggers_v4(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Frontmatter with name: '' (empty string) triggers V4."""
        content = VALID_FLIGHT_PLAN_CONTENT.replace("name: test-plan", "name: ''")
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        locations = [i.location for i in issues]
        assert any("name" in loc.lower() or "V4" in loc for loc in locations)

    def test_missing_version_triggers_v5(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Frontmatter without 'version' field triggers V5."""
        path = write_flight_plan(self._content_without("version"))
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        locations = [i.location for i in issues]
        assert any("version" in loc.lower() or "V5" in loc for loc in locations)

    def test_empty_version_triggers_v5(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Frontmatter with version: '' triggers V5."""
        content = VALID_FLIGHT_PLAN_CONTENT.replace('version: "1.0"', "version: ''")
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        locations = [i.location for i in issues]
        assert any("version" in loc.lower() or "V5" in loc for loc in locations)

    def test_missing_created_triggers_v6(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Frontmatter without 'created' field triggers V6."""
        path = write_flight_plan(self._content_without("created"))
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        locations = [i.location for i in issues]
        assert any("created" in loc.lower() or "V6" in loc for loc in locations)

    def test_multiple_missing_fields_generates_multiple_issues(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Multiple missing frontmatter fields each generate their own issue."""
        content = self._content_without("name")
        # Also remove version
        content = "\n".join(
            line for line in content.splitlines() if not line.startswith("version:")
        )
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 2


# ---------------------------------------------------------------------------
# Section rules (V7-V9)
# ---------------------------------------------------------------------------


class TestSectionRules:
    """V7, V8, V9 check required body sections."""

    def test_missing_objective_section_triggers_v7(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Missing ## Objective section triggers V7."""
        old = "## Objective\n\nThis is the objective text.\n"
        content = VALID_FLIGHT_PLAN_CONTENT.replace(old, "")
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        messages = [i.message.lower() for i in issues]
        assert any("objective" in m for m in messages)

    def test_empty_objective_triggers_v7(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """## Objective section present but empty triggers V7."""
        content = VALID_FLIGHT_PLAN_CONTENT.replace(
            "## Objective\n\nThis is the objective text.\n",
            "## Objective\n\n",
        )
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        messages = [i.message.lower() for i in issues]
        assert any("objective" in m for m in messages)

    def test_wrong_heading_level_for_objective_triggers_v7(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """### Objective (H3 not H2) is not recognised -- triggers V7."""
        content = VALID_FLIGHT_PLAN_CONTENT.replace(
            "## Objective\n\nThis is the objective text.\n",
            "### Objective\n\nThis is the objective text.\n",
        )
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        messages = [i.message.lower() for i in issues]
        assert any("objective" in m for m in messages)

    def test_missing_success_criteria_section_triggers_v8(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Missing ## Success Criteria section triggers V8."""
        content = VALID_FLIGHT_PLAN_CONTENT.replace(
            "## Success Criteria\n\n- [ ] First criterion\n- [ ] Second criterion\n",
            "",
        )
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        messages = [i.message.lower() for i in issues]
        assert any("success criteria" in m or "success_criteria" in m for m in messages)

    def test_empty_success_criteria_triggers_v8(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """## Success Criteria section present but no checkbox items triggers V8."""
        content = VALID_FLIGHT_PLAN_CONTENT.replace(
            "## Success Criteria\n\n- [ ] First criterion\n- [ ] Second criterion\n",
            "## Success Criteria\n\nNo checkbox items here, just prose.\n",
        )
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        messages = [i.message.lower() for i in issues]
        assert any("success criteria" in m or "success_criteria" in m for m in messages)

    def test_missing_scope_section_triggers_v9(
        self, write_flight_plan: Callable[..., Path]
    ) -> None:
        """Missing ## Scope section triggers V9."""
        # Remove from ## Scope to end (everything after success criteria)
        content = VALID_FLIGHT_PLAN_CONTENT.split("## Scope")[0]
        # Re-add the frontmatter and objective/criteria sections
        path = write_flight_plan(content)
        issues = validate_flight_plan_file(path)
        assert len(issues) >= 1
        messages = [i.message.lower() for i in issues]
        assert any("scope" in m for m in messages)


# ---------------------------------------------------------------------------
# FileNotFoundError propagation
# ---------------------------------------------------------------------------


class TestFileNotFoundPropagation:
    """FileNotFoundError must be re-raised as-is."""

    def test_missing_file_raises_file_not_found_error(self, tmp_path: Path) -> None:
        """validate_flight_plan_file raises FileNotFoundError for non-existent path."""
        missing = tmp_path / "does-not-exist.md"
        with pytest.raises(FileNotFoundError):
            validate_flight_plan_file(missing)


# ---------------------------------------------------------------------------
# ValidationIssue dataclass structure
# ---------------------------------------------------------------------------


class TestValidationIssueDataclass:
    """ValidationIssue is a frozen dataclass with location and message fields."""

    def test_validation_issue_has_location_and_message(self) -> None:
        """ValidationIssue can be constructed with location and message."""
        issue = ValidationIssue(location="frontmatter.name", message="Field is missing")
        assert issue.location == "frontmatter.name"
        assert issue.message == "Field is missing"

    def test_validation_issue_is_frozen(self) -> None:
        """ValidationIssue is immutable (frozen dataclass)."""
        issue = ValidationIssue(location="frontmatter.name", message="Field is missing")
        with pytest.raises((AttributeError, TypeError)):
            issue.location = "other"  # type: ignore[misc]

    def test_validation_issue_equality(self) -> None:
        """Two ValidationIssue instances with same fields are equal."""
        a = ValidationIssue(location="frontmatter.name", message="Missing")
        b = ValidationIssue(location="frontmatter.name", message="Missing")
        assert a == b
